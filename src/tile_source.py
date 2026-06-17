"""Map tile and manual patch loading for the localization playground."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
from PIL import Image

from .matchers.base import CandidateImage


class TileSource:
    def __init__(self, map_dir: Path, zoom: int = 15):
        self.map_dir = map_dir
        self.database_path = map_dir / "tile_database.json"
        self.database = self._load_database()
        self.tile_size = int(self.database.get("tile_size", 256))
        self.zoom = zoom
        self._stitched_cache = None
        self._tile_lookup = {}
        self._bounds_cache = None

    def _load_database(self) -> dict:
        with open(self.database_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def zooms(self) -> list[int]:
        return sorted(int(z) for z in self.database["zoom_levels"].keys())

    def set_zoom(self, zoom: int) -> None:
        if zoom != self.zoom:
            self.zoom = zoom
            self._stitched_cache = None
            self._tile_lookup = {}
            self._bounds_cache = None

    def tiles(self) -> list[dict]:
        return self.database["zoom_levels"][str(self.zoom)]["tiles"]

    def overlays(self) -> list[dict]:
        return self.database.get("overlays", [])

    def overlays_for_tile(self, tile_x: int, tile_y: int) -> list[dict]:
        key = f"tile_bounds_{self.zoom}"
        result = []
        for ov in self.overlays():
            tb = ov.get(key)
            if tb is None:
                continue
            if tb["min_x"] <= tile_x <= tb["max_x"] and tb["min_y"] <= tile_y <= tb["max_y"]:
                result.append(ov)
        return result

    def tile_lookup(self) -> dict[tuple[int, int], dict]:
        if not self._tile_lookup:
            self._tile_lookup = {(tile["x"], tile["y"]): tile for tile in self.tiles()}
        return self._tile_lookup

    def bounds(self) -> tuple[int, int, int, int]:
        if self._bounds_cache is not None:
            return self._bounds_cache
        tiles = self.tiles()
        xs = [t["x"] for t in tiles]
        ys = [t["y"] for t in tiles]
        self._bounds_cache = (min(xs), max(xs), min(ys), max(ys))
        return self._bounds_cache

    def stitched_path(self) -> Path:
        return self.map_dir / "stitched" / f"map_zoom_{self.zoom}.jpg"

    def load_stitched(self):
        if self._stitched_cache is None:
            self._stitched_cache = cv2.imread(str(self.stitched_path()), cv2.IMREAD_COLOR)
        return self._stitched_cache

    def tile_candidates(self, max_tiles: int | None = None) -> list[CandidateImage]:
        candidates = []
        for idx, tile in enumerate(self.tiles()):
            if max_tiles is not None and idx >= max_tiles:
                break
            path = self.map_dir / tile["path"]
            if not path.exists():
                continue
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                continue
            candidates.append(
                CandidateImage(
                    tile_x=tile["x"],
                    tile_y=tile["y"],
                    image=image,
                    path=path,
                    label=f"tile {tile['x']},{tile['y']}",
                    metadata={"zoom": self.zoom, "kind": "tile"},
                )
            )
        return candidates

    def tile_candidate(self, tile_x: int, tile_y: int) -> CandidateImage:
        tile = self.tile_lookup().get((tile_x, tile_y))
        if tile is None:
            raise FileNotFoundError(f"No tile metadata for {tile_x},{tile_y} at zoom {self.zoom}")
        path = self.map_dir / tile["path"]
        if not path.exists():
            raise FileNotFoundError(f"Tile image not found: {path}")
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"Could not read tile image: {path}")
        return CandidateImage(
            tile_x=tile_x,
            tile_y=tile_y,
            image=image,
            path=path,
            label=f"clicked tile {tile_x},{tile_y}",
            metadata={"zoom": self.zoom, "kind": "clicked_tile"},
        )

    def tile_box_candidates(
        self,
        center_tile_x: int,
        center_tile_y: int,
        box_size: int = 8,
    ) -> tuple[list[CandidateImage], tuple[int, int, int, int], tuple[int, int, int, int]]:
        """Return available tiles in an NxN box plus world/tile bounds.

        Tile Y follows viewer.html: larger Y is higher on screen, while world
        image Y increases downward.
        """

        min_x, max_x, min_y, max_y = self.bounds()
        before = box_size // 2 - 1
        after = box_size - before - 1

        start_x = center_tile_x - before
        end_x = center_tile_x + after
        if start_x < min_x:
            end_x += min_x - start_x
            start_x = min_x
        if end_x > max_x:
            start_x -= end_x - max_x
            end_x = max_x
        start_x = max(min_x, start_x)

        start_y = center_tile_y - before
        end_y = center_tile_y + after
        if start_y < min_y:
            end_y += min_y - start_y
            start_y = min_y
        if end_y > max_y:
            start_y -= end_y - max_y
            end_y = max_y
        start_y = max(min_y, start_y)

        candidates = []
        for ty in range(end_y, start_y - 1, -1):
            for tx in range(start_x, end_x + 1):
                try:
                    candidate = self.tile_candidate(tx, ty)
                except FileNotFoundError:
                    continue
                candidate.label = f"box tile {tx},{ty}"
                candidate.metadata = {
                    **candidate.metadata,
                    "kind": "box_tile",
                    "box_center": (center_tile_x, center_tile_y),
                    "box_tile_bounds": (start_x, start_y, end_x, end_y),
                }
                candidates.append(candidate)

        world_bounds = (
            (start_x - min_x) * self.tile_size,
            (max_y - end_y) * self.tile_size,
            (end_x - min_x + 1) * self.tile_size,
            (max_y - start_y + 1) * self.tile_size,
        )
        return candidates, world_bounds, (start_x, start_y, end_x, end_y)

    def patch_candidate(self, world_x: int, world_y: int, patch_size: int = 512) -> CandidateImage:
        min_x, max_x, min_y, max_y = self.bounds()
        w = (max_x - min_x + 1) * self.tile_size
        h = (max_y - min_y + 1) * self.tile_size
        half = patch_size // 2
        x1 = max(0, min(world_x - half, w - patch_size))
        y1 = max(0, min(world_y - half, h - patch_size))
        x2 = min(w, x1 + patch_size)
        y2 = min(h, y1 + patch_size)
        patch = self._patch_from_tiles(x1, y1, x2, y2, min_x, min_y)
        if patch is None:
            stitched = self.load_stitched()
            if stitched is None:
                raise FileNotFoundError(self.stitched_path())
            patch = stitched[y1:y2, x1:x2].copy()

        tile_x = min_x + world_x // self.tile_size
        tile_y = max_y - world_y // self.tile_size
        return CandidateImage(
            tile_x=tile_x,
            tile_y=tile_y,
            image=patch,
            path=self.stitched_path(),
            label=f"manual patch near {tile_x},{tile_y}",
            metadata={
                "zoom": self.zoom,
                "kind": "manual_patch",
                "world_x": world_x,
                "world_y": world_y,
                "patch_bounds": (x1, y1, x2, y2),
            },
        )

    def _patch_from_tiles(self, x1: int, y1: int, x2: int, y2: int, min_x: int, min_y: int):
        import numpy as np

        lookup = self.tile_lookup()
        patch = np.zeros((y2 - y1, x2 - x1, 3), dtype=np.uint8)
        found_any = False

        _, _, _, max_y = self.bounds()
        start_tx = x1 // self.tile_size
        end_tx = (x2 - 1) // self.tile_size
        start_ty = y1 // self.tile_size
        end_ty = (y2 - 1) // self.tile_size

        for tile_ix in range(start_tx, end_tx + 1):
            for tile_iy in range(start_ty, end_ty + 1):
                tile_x = min_x + tile_ix
                tile_y = max_y - tile_iy
                tile = lookup.get((tile_x, tile_y))
                if not tile:
                    continue
                path = self.map_dir / tile["path"]
                if not path.exists():
                    continue
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is None:
                    continue

                tile_px1 = tile_ix * self.tile_size
                tile_py1 = tile_iy * self.tile_size
                src_x1 = max(0, x1 - tile_px1)
                src_y1 = max(0, y1 - tile_py1)
                src_x2 = min(self.tile_size, x2 - tile_px1)
                src_y2 = min(self.tile_size, y2 - tile_py1)
                dst_x1 = tile_px1 + src_x1 - x1
                dst_y1 = tile_py1 + src_y1 - y1
                dst_x2 = dst_x1 + (src_x2 - src_x1)
                dst_y2 = dst_y1 + (src_y2 - src_y1)
                patch[dst_y1:dst_y2, dst_x1:dst_x2] = image[src_y1:src_y2, src_x1:src_x2]
                found_any = True

        return patch if found_any else None

    def render_preview(self, max_size: tuple[int, int]):
        min_x, max_x, min_y, max_y = self.bounds()
        map_w = (max_x - min_x + 1) * self.tile_size
        map_h = (max_y - min_y + 1) * self.tile_size
        scale = min(max_size[0] / map_w, max_size[1] / map_h)
        preview_w = max(1, int(map_w * scale))
        preview_h = max(1, int(map_h * scale))

        cache_path = self.map_dir / "stitched" / f"viewer_preview_zoom_{self.zoom}_{preview_w}x{preview_h}.jpg"
        if cache_path.exists():
            return Image.open(cache_path).convert("RGB"), scale

        preview = Image.new("RGB", (preview_w, preview_h), (0, 0, 0))

        thumb_size = max(1, int(self.tile_size * scale))
        for tile in self.tiles():
            path = self.map_dir / tile["path"]
            if not path.exists():
                continue
            try:
                tile_img = Image.open(path).convert("RGB")
            except OSError:
                continue
            tile_img = tile_img.resize((thumb_size, thumb_size), Image.Resampling.BILINEAR)
            px = int((tile["x"] - min_x) * self.tile_size * scale)
            py = int((max_y - tile["y"]) * self.tile_size * scale)
            preview.paste(tile_img, (px, py))

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        preview.save(cache_path, quality=90)
        return preview, scale
