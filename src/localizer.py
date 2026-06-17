"""Route localization engine using AKAZE matching and state machine tracking."""

import json
import logging
import math
import time
from enum import Enum
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import deque, OrderedDict

import cv2
import numpy as np
from tqdm import tqdm

from .tile_source import TileSource
from .matchers.base import to_gray
from .preprocessing import prepare_minimap, create_circular_mask
from .map_dataset import MapDataset
from .constants import (
    AKAZE_DISTANCE_THRESHOLD, CONFIDENCE_THRESHOLD, MIN_EXPECTED_MATCHES,
    LOST_FRAMES_BEFORE_GLOBAL, LOST_FRAMES_BEFORE_EXPANDING,
    TELEPORT_DISTANCE_PX, CACHE_CAPACITY, TOP_K_COARSE, TOP_K_OUTPUT_JSON,
    MIN_MATCHES_FOR_HOMOGRAPHY, RANSAC_REPROJECTION_THRESHOLD,
    MIN_HOMOGRAPHY_INLIERS, OFF_PATCH_INLIER_PENALTY, DEFAULT_SCALES,
    MAX_WORKERS_PRECOMPUTE,
)

def tile_to_latlng(tx: float, ty: float, zoom: int) -> tuple[float, float]:
    half = 2 ** (zoom - 1)
    total = 2 ** zoom
    google_x = tx + half
    google_y = half - ty - 1
    lng = google_x / total * 360 - 180
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * google_y / total)))
    lat = lat_rad * 180 / math.pi
    return lat, lng

logger = logging.getLogger(__name__)

class TrackingState(Enum):
    UNINITIALIZED = "uninitialized"
    TRACKING = "tracking"
    EXPANDING = "expanding"
    LOST = "lost"

class LRUPatchCache:
    def __init__(self, capacity: int = 50):
        self.cache = OrderedDict()
        self.capacity = capacity

    def get(self, key):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)


class LRUDescriptorCache:
    """LRU cache for AKAZE keypoints and descriptors keyed by (tile_x, tile_y, zoom)."""

    def __init__(self, capacity: int = 200):
        self.cache: OrderedDict[tuple, tuple[list, object | None]] = OrderedDict()
        self.capacity = capacity

    def get(self, key: tuple) -> tuple[list, object | None] | None:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: tuple, value: tuple[list, object | None]) -> None:
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def clear(self) -> None:
        self.cache.clear()


def is_valid_minimap(image: np.ndarray, min_laplacian_var: float = 50.0) -> bool:
    """Check if an image has enough sharp features for AKAZE matching.

    Blurry/foggy scenes and frames without a minimap HUD have low Laplacian
    variance, meaning there are no sharp edges for feature detection.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    return laplacian_var >= min_laplacian_var


class Localizer:
    def __init__(
        self,
        map_dataset: MapDataset,
        coarse_zoom: int | None = None,
        fine_zoom: int | None = None,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
        min_expected_matches: float = MIN_EXPECTED_MATCHES,
    ):
        if not isinstance(map_dataset, MapDataset):
            raise TypeError(f"map_dataset must be a MapDataset, got {type(map_dataset).__name__}")
        if confidence_threshold < 0 or confidence_threshold > 1:
            raise ValueError(f"confidence_threshold must be in [0, 1], got {confidence_threshold}")
        if min_expected_matches <= 0:
            raise ValueError(f"min_expected_matches must be positive, got {min_expected_matches}")

        self.map_dataset = map_dataset
        self.coarse_zoom = coarse_zoom or map_dataset.coarse_zoom
        self.fine_zoom = fine_zoom or map_dataset.fine_zoom

        self.coarse_source = TileSource(self.map_dataset.map_dir, zoom=self.coarse_zoom)
        self.fine_source = TileSource(self.map_dataset.map_dir, zoom=self.fine_zoom)
        
        self.confidence_threshold = confidence_threshold
        self.min_expected_matches = min_expected_matches

        self.detector = cv2.AKAZE_create()
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

        self.state = TrackingState.UNINITIALIZED
        self.last_tile = None
        self.last_world_pos = None
        self.frames_since_good_match = 0
        self.segment_id = 0
        
        self.patch_cache = LRUPatchCache(capacity=CACHE_CAPACITY)
        self.desc_cache = LRUDescriptorCache(capacity=200)

        self.coarse_data = {}
        self._precompute_descriptors()

    def _precompute_descriptors(self) -> None:
        """Precompute AKAZE descriptors for coarse search (zoom 12) only."""
        logger.info(f"Initializing Localizer: Precomputing coarse descriptors at zoom {self.coarse_zoom}...")
        start_time = time.perf_counter()

        tiles = self.coarse_source.tiles()
        logger.info(f"Found {len(tiles)} tiles in coarse database.")

        def process_tile_entry(tile_entry):
            tx, ty = tile_entry["x"], tile_entry["y"]
            path = self.coarse_source.map_dir / tile_entry["path"]
            if not path.exists():
                return None
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                return None
            gray = to_gray(image)
            kp, desc = self.detector.detectAndCompute(gray, None)
            return (tx, ty), kp, desc, image.shape[:2]

        processed_count = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS_PRECOMPUTE) as executor:
            results = list(executor.map(process_tile_entry, tiles))

        for res in results:
            if res is not None:
                (tx, ty), kp, desc, shape = res
                if desc is not None and len(kp) > 0:
                    self.coarse_data[(tx, ty)] = (kp, desc, shape)
                    processed_count += 1

        elapsed = time.perf_counter() - start_time
        logger.info(f"Precomputed {processed_count}/{len(tiles)} coarse tiles in {elapsed:.2f}s.")

    def _coarse_search(self, mini_desc) -> list[tuple[int, int]]:
        if mini_desc is None or len(mini_desc) == 0:
            return []

        if not self.coarse_data:
            logger.warning("Coarse data is empty — no tiles precomputed. Global search will fail.")
            return []
            
        scored = []
        for (tx, ty), (cand_kp, cand_desc, shape) in self.coarse_data.items():
            if cand_desc is not None and len(cand_desc) > 0:
                raw_matches = self.matcher.match(mini_desc, cand_desc)
                good = [m for m in raw_matches if m.distance < AKAZE_DISTANCE_THRESHOLD]
                scored.append(((tx, ty), len(good)))
                
        scored.sort(key=lambda x: x[1], reverse=True)
        return [t[0] for t in scored[:TOP_K_COARSE]]

    def _coarse_to_fine_coords(self, coarse_tx: int, coarse_ty: int) -> tuple[int, int]:
        factor = 2 ** (self.fine_zoom - self.coarse_zoom)
        return coarse_tx * factor + factor // 2, coarse_ty * factor + factor // 2

    def _build_patch(self, center_tx: int, center_ty: int, radius: int = 1):
        min_x, max_x, min_y, max_y = self.fine_source.bounds()
        tile_size = self.fine_source.tile_size
        
        start_tx = center_tx - radius
        end_tx = center_tx + radius
        start_ty = center_ty - radius
        end_ty = center_ty + radius
        
        x1 = (start_tx - min_x) * tile_size
        y1 = (max_y - end_ty) * tile_size
        x2 = (end_tx - min_x + 1) * tile_size
        y2 = (max_y - start_ty + 1) * tile_size
        
        cache_key = (center_tx, center_ty, radius)
        cached = self.patch_cache.get(cache_key)
        if cached is not None:
            return cached
            
        patch = self.fine_source._patch_from_tiles(x1, y1, x2, y2, min_x, min_y)
        if patch is None:
            patch = np.zeros((y2 - y1, x2 - x1, 3), dtype=np.uint8)

        desc_key = (center_tx, center_ty, self.fine_zoom, radius)
        cached_desc = self.desc_cache.get(desc_key)
        if cached_desc is not None:
            kp, desc = cached_desc
        else:
            gray = to_gray(patch)
            kp, desc = self.detector.detectAndCompute(gray, None)
            self.desc_cache.put(desc_key, (kp, desc))
            
        self.patch_cache.put(cache_key, (patch, x1, y1, kp, desc))
        return patch, x1, y1, kp, desc

    def _match_patch(self, patch: np.ndarray, patch_origin_x: int, patch_origin_y: int, center_tx: int, center_ty: int, mini_kp, mini_desc, minimap_shape, cand_kp=None, cand_desc=None) -> dict:
        if cand_kp is None or cand_desc is None:
            gray = to_gray(patch)
            cand_kp, cand_desc = self.detector.detectAndCompute(gray, None)
        
        if mini_desc is None or cand_desc is None or len(mini_kp) == 0 or len(cand_desc) == 0:
            return None
            
        matches = self.matcher.match(mini_desc, cand_desc)
        good = [m for m in matches if m.distance < AKAZE_DISTANCE_THRESHOLD]
        match_count = len(good)
        
        inlier_ratio = 0.0
        world_x = float(patch_origin_x + patch.shape[1] / 2)
        world_y = float(patch_origin_y + patch.shape[0] / 2)
        
        if match_count >= MIN_MATCHES_FOR_HOMOGRAPHY:
            src_pts = np.float32([mini_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = np.float32([cand_kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, RANSAC_REPROJECTION_THRESHOLD)
            
            if H is not None and H.shape == (3, 3) and mask is not None:
                inliers = int(np.sum(mask))
                if inliers >= MIN_HOMOGRAPHY_INLIERS:
                    h_mini, w_mini = minimap_shape[:2]
                    center_mini = np.array([[[w_mini / 2.0, h_mini / 2.0]]], dtype=np.float32)
                    center_patch = cv2.perspectiveTransform(center_mini, H)
                    px = float(center_patch[0, 0, 0])
                    py = float(center_patch[0, 0, 1])
                    
                    # Sanity check: the minimap center MUST be within the patch.
                    # If the homography shoots it off to infinity, it's a garbage transform.
                    if 0 <= px <= patch.shape[1] and 0 <= py <= patch.shape[0]:
                        world_x = patch_origin_x + px
                        world_y = patch_origin_y + py
                        inlier_ratio = inliers / match_count
                    else:
                        # Garbage homography, use center of patch but penalize confidence
                        inlier_ratio = (inliers / match_count) * OFF_PATCH_INLIER_PENALTY
                else:
                    inlier_ratio = 0.0
                    
        normalized_match_count = min(1.0, match_count / self.min_expected_matches)
        confidence = normalized_match_count * inlier_ratio
        
        tile_size = self.fine_source.tile_size
        min_x, _, _, max_y = self.fine_source.bounds()
        frac_tx = min_x + world_x / tile_size
        frac_ty = max_y - world_y / tile_size
        lat, lng = tile_to_latlng(frac_tx, frac_ty, self.fine_source.zoom)
        
        return {
            "tile": (center_tx, center_ty),
            "score": match_count,
            "confidence": confidence,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "map_x": round(world_x, 1),
            "map_y": round(world_y, 1),
        }

    def _search_centers(self, centers_to_search, radius, variants) -> list[dict]:
        all_candidates = []
        for scale, scaled_mini, mask in variants:
            gray = to_gray(scaled_mini)
            mini_kp, mini_desc = self.detector.detectAndCompute(gray, mask)
            if mini_desc is None or len(mini_kp) == 0:
                continue
                
            for tx, ty in centers_to_search:
                patch, ox, oy, cand_kp, cand_desc = self._build_patch(tx, ty, radius=radius)
                cand = self._match_patch(patch, ox, oy, tx, ty, mini_kp, mini_desc, scaled_mini.shape, cand_kp, cand_desc)
                if cand:
                    # Avoid duplicate candidates for the same tile from different scales
                    existing = [c for c in all_candidates if c["tile"] == cand["tile"]]
                    if not existing:
                        all_candidates.append(cand)
                    elif cand["confidence"] > existing[0]["confidence"]:
                        existing[0].update(cand)
                        
        all_candidates.sort(key=lambda c: c["confidence"], reverse=True)
        return all_candidates

    def localize_frame(self, minimap: np.ndarray) -> dict:
        variants = prepare_minimap(minimap, scales=DEFAULT_SCALES)
        
        candidates = []
        search_radius = 0
        current_mode = "tracking"

        if self.state in (TrackingState.UNINITIALIZED, TrackingState.LOST) or self.last_tile is None:
            current_mode = "global_search"
            search_radius = 1
            _, base_mini, base_mask = variants[1] if len(variants) >= 2 else variants[0]
            gray = to_gray(base_mini)
            _, mini_desc = self.detector.detectAndCompute(gray, base_mask)
            coarse_tiles = self._coarse_search(mini_desc)
            
            centers_to_search = [self._coarse_to_fine_coords(ctx, cty) for ctx, cty in coarse_tiles]
            candidates = self._search_centers(centers_to_search, search_radius, variants)
            
        else:
            if self.state == TrackingState.TRACKING:
                current_mode = "tracking"
                search_radius = 1
            else:
                current_mode = "expanding"
                search_radius = 2
                
            candidates = self._search_centers([self.last_tile], search_radius, variants)
            
            if not candidates or candidates[0]["confidence"] < self.confidence_threshold:
                if search_radius == 1:
                    if self.frames_since_good_match == 0:
                        logger.debug(f"Confidence dropped, expanding to 5x5 around {self.last_tile}")
                    current_mode = "expanding"
                    search_radius = 2
                    candidates = self._search_centers([self.last_tile], search_radius, variants)
                    
                if not candidates or candidates[0]["confidence"] < self.confidence_threshold:
                    if self.frames_since_good_match <= LOST_FRAMES_BEFORE_GLOBAL:
                        logger.debug("All local searches failed, global search")
                    current_mode = "global_search"
                    search_radius = 1
                    _, base_mini, base_mask = variants[1] if len(variants) >= 2 else variants[0]
                    gray = to_gray(base_mini)
                    _, mini_desc = self.detector.detectAndCompute(gray, base_mask)
                    coarse_tiles = self._coarse_search(mini_desc)
                    centers_to_search = [self._coarse_to_fine_coords(ctx, cty) for ctx, cty in coarse_tiles]
                    candidates = self._search_centers(centers_to_search, search_radius, variants)

        best_candidate = candidates[0] if candidates else None

        event_type = "normal"
        if best_candidate and best_candidate["confidence"] >= self.confidence_threshold:
            if self.state in (TrackingState.LOST, TrackingState.UNINITIALIZED) and self.last_world_pos is not None:
                dx = best_candidate["map_x"] - self.last_world_pos[0]
                dy = best_candidate["map_y"] - self.last_world_pos[1]
                dist = (dx**2 + dy**2)**0.5
                if dist > TELEPORT_DISTANCE_PX: # teleport threshold (~6 tiles)
                    self.segment_id += 1
                    event_type = "teleport"
                    
            self.state = TrackingState.TRACKING
            self.last_tile = best_candidate["tile"]
            self.last_world_pos = (best_candidate["map_x"], best_candidate["map_y"])
            self.frames_since_good_match = 0
            best_tracking_mode = "relocalized" if event_type == "teleport" else "tracking"
        else:
            self.frames_since_good_match += 1
            if self.frames_since_good_match > LOST_FRAMES_BEFORE_EXPANDING:
                self.state = TrackingState.LOST
            else:
                self.state = TrackingState.EXPANDING
            best_tracking_mode = "lost" if self.state == TrackingState.LOST else "expanding"
            event_type = "lost"

        json_candidates = []
        for cand in candidates[:TOP_K_OUTPUT_JSON]:
            json_candidates.append({
                "tile": list(cand["tile"]),
                "score": cand["score"],
                "confidence": round(cand["confidence"], 4),
                "lat": cand["lat"],
                "lng": cand["lng"],
                "map_x": cand["map_x"],
                "map_y": cand["map_y"],
            })

        return {
            "map_name": self.map_dataset.name,
            "tile_x": best_candidate["tile"][0] if best_candidate else None,
            "tile_y": best_candidate["tile"][1] if best_candidate else None,
            "confidence": round(best_candidate["confidence"], 4) if best_candidate else 0.0,
            "match_score": best_candidate["score"] if best_candidate else 0,
            "tracking_mode": best_tracking_mode,
            "event_type": event_type,
            "segment_id": self.segment_id,
            "best": list(best_candidate["tile"]) if best_candidate else None,
            "candidates": json_candidates,
            "lat": best_candidate["lat"] if best_candidate else None,
            "lng": best_candidate["lng"] if best_candidate else None,
            "map_x": best_candidate["map_x"] if best_candidate else None,
            "map_y": best_candidate["map_y"] if best_candidate else None,
            "search_radius": search_radius,
        }

    def switch_map(self, new_dataset: MapDataset) -> None:
        """Switch active dataset and rebuild any per-map caches."""
        if new_dataset.name == self.map_dataset.name:
            return

        self.map_dataset = new_dataset
        self.coarse_source = TileSource(self.map_dataset.map_dir, zoom=self.coarse_zoom)
        self.fine_source = TileSource(self.map_dataset.map_dir, zoom=self.fine_zoom)

        self.patch_cache = LRUPatchCache(capacity=CACHE_CAPACITY)
        self.desc_cache.clear()
        self.coarse_data = {}
        self._precompute_descriptors()

    def localize_route(self, route_dir: Path, benchmark=None) -> Path:
        from .benchmark import BenchmarkReport  # local import to avoid hard dependency at import time
        if benchmark is not None and not isinstance(benchmark, BenchmarkReport):
            raise TypeError("benchmark must be a BenchmarkReport or None")

        route_path = route_dir / "route.json"
        if not route_path.exists():
            raise FileNotFoundError(f"route.json not found: {route_path}")

        with open(route_path, "r", encoding="utf-8") as f:
            entries = json.load(f)

        logger.info(f"Localizing {len(entries)} frames in route {route_dir.name}...")
        self.state = TrackingState.UNINITIALIZED
        self.last_tile = None
        self.frames_since_good_match = 0

        localized_count = 0
        t0 = time.perf_counter()

        progress = tqdm(total=len(entries), desc="Localizing", unit="frame")
        for idx, entry in enumerate(entries):
            minimap_rel = str(entry.get("minimap", "")).strip()
            # Normalize path fragments to avoid CR/LF artifacts and Windows separator issues.
            minimap_rel = minimap_rel.replace("\\", "/")
            minimap_name = Path(minimap_rel).name
            minimap_path = route_dir / "minimaps" / minimap_name

            if not minimap_path.exists():
                progress.update(1)
                continue

            minimap = cv2.imread(str(minimap_path))
            if minimap is None:
                progress.update(1)
                continue

            if not is_valid_minimap(minimap):
                entry["tracking_mode"] = "no_minimap"
                entry["event_type"] = "no_minimap"
                entry["confidence"] = 0.0
                entry["match_score"] = 0
                progress.update(1)
                continue

            t_frame0 = time.perf_counter()
            result = self.localize_frame(minimap)
            elapsed_ms = (time.perf_counter() - t_frame0) * 1000.0

            entry.update(result)
            localized_count += 1

            if benchmark is not None and result is not None:
                benchmark.record_frame(
                    index=idx,
                    elapsed_ms=elapsed_ms,
                    confidence=float(result.get("confidence") or 0.0),
                    tracking_mode=result.get("tracking_mode"),
                    event_type=result.get("event_type"),
                )

            conf = result.get("confidence", 0.0) if result else 0.0
            progress.set_postfix_str(f"tile={self.last_tile} conf={conf:.2f} {self.state.value}")
            progress.update(1)

        progress.close()

        with open(route_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)

        if benchmark is not None:
            benchmark.generate(route_dir)

        elapsed = time.perf_counter() - t0
        logger.info(
            f"Localized {localized_count} frames in {elapsed:.2f}s "
            f"({elapsed / max(1, localized_count) * 1000:.1f}ms/frame)."
        )
        return route_path
