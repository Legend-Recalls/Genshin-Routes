"""Sensor-fusion path builder for guide-route plotting.

Given route.json (per-frame AKAZE localizations + optical-flow displacement),
produce a single continuous, smooth path suitable for plotting a treasure-
collection guide on a map.

Inputs (per frame):
* AKAZE localization: ``best`` (tile), ``map_x``/``map_y`` (world px),
  ``confidence``, ``tracking_mode``.
* Optical flow: ``flow_dx``/``flow_dy`` (minimap px, accumulated since the
  previous 1-FPS sample).

Fusion logic
------------
1. **Anchors**: frames with AKAZE confidence >= FUSION_ANCHOR_CONFIDENCE and a
   valid minimap are treated as absolute truth.
2. **Dead-reckoning**: between two anchors, intermediate frames are positioned
   by integrating flow: ``pos = anchor_a.world + Σ(FUSION_FLOW_SCALE * flow)``.
   This recovers AKAZE-fail frames that are the *same location slightly
   shifted* (e.g. idx 40, 41).
3. **Segmentation**: a cutscene (invalid minimap, or huge flow) ends the
   current segment. The path never interpolates across a cutscene — instead a
   new segment begins at the next anchor.
4. **Interpolation fallback**: if flow is absent between two anchors, linearly
   interpolate. If the dead-reckoned position strays beyond
   FUSION_MAX_DEADRECKON_TILES from the straight line between anchors, fall
   back to interpolation (guard against flow drift).
5. **Smoothing**: a moving-average pass on each segment removes per-frame
   jitter while preserving the path shape.

The cold-start region (before the first anchor) is discarded — it is
intro/cutscene content with no reliable position.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .constants import (
    FUSION_ANCHOR_CONFIDENCE,
    FUSION_FLOW_SCALE_X,
    FUSION_FLOW_SCALE_Y,
    FUSION_MAX_DEADRECKON_TILES,
)
from .localizer import is_valid_minimap

logger = logging.getLogger(__name__)

# Cutscene detection: a frame whose flow magnitude exceeds this (minimap px) is
# a scene cut — never dead-reckon across it. (idx 61 measured ~1700px, idx 166
# ~550px; clean motion is <15px.)
CUTSCENE_FLOW_MAGNITUDE_PX = 100.0
# Moving-average window (frames) for final smoothing. ~5 frames = 5s at 1 FPS.
SMOOTH_WINDOW = 5


@dataclass
class PathPoint:
    index: int
    frame: int
    timestamp: float
    world_x: float
    world_y: float
    tile_x: int
    tile_y: int
    source: str  # "anchor" | "flow" | "interp"


def _flow_magnitude(entry: dict) -> float | None:
    dx, dy = entry.get("flow_dx"), entry.get("flow_dy")
    if dx is None or dy is None:
        return None
    return math.hypot(dx, dy)


def _is_cutscene(entry: dict, minimap_valid_cache: dict) -> bool:
    """A cutscene: invalid minimap, or a teleport-scale flow spike."""
    idx = entry["index"]
    if idx not in minimap_valid_cache:
        # We precompute validity once; if missing, treat conservatively.
        return False
    if not minimap_valid_cache[idx]:
        return True
    mag = _flow_magnitude(entry)
    if mag is not None and mag > CUTSCENE_FLOW_MAGNITUDE_PX:
        return True
    return False


def _is_anchor(entry: dict, minimap_valid_cache: dict) -> bool:
    """A reliable absolute-position anchor."""
    if _is_cutscene(entry, minimap_valid_cache):
        return False
    conf = float(entry.get("confidence") or 0.0)
    if conf < FUSION_ANCHOR_CONFIDENCE:
        return False
    mx, my = entry.get("map_x"), entry.get("map_y")
    if mx is None or my is None:
        return False
    return True


def _world_to_tile(world_x: float, world_y: float, tile_size: int,
                   min_x: int, max_y: int) -> tuple[int, int]:
    return (int(min_x + world_x // tile_size), int(max_y - world_y // tile_size))


def _dead_reckon(anchor_world: tuple[float, float],
                 entries: list[dict], start_idx: int, end_idx: int) -> list[tuple[float, float]]:
    """Integrate flow from anchor through entries[start_idx+1 .. end_idx].

    Returns the cumulative world position at each intermediate frame
    (length = end_idx - start_idx). Stops early (returns None-style) if flow
    is missing; caller falls back to interpolation.
    """
    wx, wy = anchor_world
    positions = []
    for i in range(start_idx + 1, end_idx + 1):
        e = entries[i]
        dx, dy = e.get("flow_dx"), e.get("flow_dy")
        if dx is None or dy is None:
            # Flow gap: signal fallback by returning what we have so far,
            # padded with None; caller will interpolate the rest.
            positions.append(None)
            continue
        wx += FUSION_FLOW_SCALE_X * dx
        wy += FUSION_FLOW_SCALE_Y * dy
        positions.append((wx, wy))
    return positions


def _interpolate(a_world: tuple[float, float], b_world: tuple[float, float],
                 steps: int) -> list[tuple[float, float]]:
    """Linear interpolation between two world positions over `steps` frames."""
    out = []
    for k in range(1, steps + 1):
        t = k / steps
        out.append((a_world[0] + (b_world[0] - a_world[0]) * t,
                    a_world[1] + (b_world[1] - a_world[1]) * t))
    return out


def _smooth_segment(points: list[PathPoint], window: int = SMOOTH_WINDOW) -> None:
    """In-place moving-average smoothing of world_x/world_y within a segment."""
    if len(points) < 3:
        return
    xs = np.array([p.world_x for p in points], dtype=float)
    ys = np.array([p.world_y for p in points], dtype=float)
    # Centered moving average with edge clamping.
    k = window // 2
    sx = np.empty_like(xs)
    sy = np.empty_like(ys)
    for i in range(len(xs)):
        lo = max(0, i - k)
        hi = min(len(xs), i + k + 1)
        sx[i] = xs[lo:hi].mean()
        sy[i] = ys[lo:hi].mean()
    for p, x, y in zip(points, sx, sy):
        p.world_x = float(x)
        p.world_y = float(y)


def build_path(entries: list[dict], route_dir: Path,
               tile_size: int = 256, min_x: int = -64, max_y: int = 58) -> list[PathPoint]:
    """Fuse AKAZE anchors + optical flow into a continuous path.

    Pre-scans minimap validity once (reads the PNGs), then segments the route
    at cutscenes and fills each segment via dead-reckoning or interpolation.
    """
    minimaps_dir = route_dir / "minimaps"
    validity: dict[int, bool] = {}
    for e in entries:
        idx = e["index"]
        name = Path(str(e.get("minimap", ""))).name
        mp = minimaps_dir / name
        if not mp.exists():
            validity[idx] = False
            continue
        import cv2
        img = cv2.imread(str(mp))
        validity[idx] = False if img is None else is_valid_minimap(img)

    # Classify every frame.
    anchor_idxs = [i for i, e in enumerate(entries) if _is_anchor(e, validity)]
    if not anchor_idxs:
        logger.warning("No AKAZE anchors found; cannot build path.")
        return []

    first_anchor = anchor_idxs[0]
    logger.info(f"Path fusion: first anchor at idx {first_anchor} "
                f"({len(anchor_idxs)} anchors total, route starts here).")

    points: list[PathPoint] = []

    def make_point(entry: dict, wx: float, wy: float, source: str) -> PathPoint:
        tx, ty = _world_to_tile(wx, wy, tile_size, min_x, max_y)
        return PathPoint(
            index=entry["index"], frame=entry.get("frame", entry["index"]),
            timestamp=entry.get("timestamp", 0.0),
            world_x=float(wx), world_y=float(wy), tile_x=tx, tile_y=ty,
            source=source,
        )

    # Walk forward from the first anchor, segment by segment.
    cur_anchor_pos = anchor_pos = (float(entries[first_anchor]["map_x"]),
                                   float(entries[first_anchor]["map_y"]))
    points.append(make_point(entries[first_anchor], *anchor_pos, "anchor"))

    i = first_anchor + 1
    while i < len(entries):
        e = entries[i]
        # Cutscene ends the current segment; skip until the next anchor.
        if _is_cutscene(e, validity):
            # Find next anchor after this cutscene.
            next_anchor = next((j for j in anchor_idxs if j > i), None)
            if next_anchor is None:
                break  # rest of route is post-cutscene junk
            # Start fresh segment at next anchor.
            anchor_pos = (float(entries[next_anchor]["map_x"]),
                          float(entries[next_anchor]["map_y"]))
            points.append(make_point(entries[next_anchor], *anchor_pos, "anchor"))
            i = next_anchor + 1
            continue

        if i in anchor_idxs:
            # Confirmed anchor: adopt its absolute position.
            anchor_pos = (float(e["map_x"]), float(e["map_y"]))
            points.append(make_point(e, *anchor_pos, "anchor"))
            i += 1
            continue

        # Non-anchor, non-cutscene frame: dead-reckon or interpolate.
        # Find the next anchor (or end of segment) ahead.
        next_anchor = next((j for j in anchor_idxs if j >= i), None)
        seg_end = next_anchor if next_anchor is not None else len(entries)
        # Dead-reckon from current anchor through this run of frames.
        reckoned = _dead_reckon(anchor_pos, entries, i - 1, seg_end - 1)
        # Check for flow gaps or drift; fall back to interpolation where needed.
        a_world = anchor_pos
        b_world = (float(entries[seg_end]["map_x"]),
                   float(entries[seg_end]["map_y"])) if next_anchor else None
        # Distance guard: if dead-reckoning strays far from the straight line,
        # interpolate instead. Compute per-frame.
        run_len = seg_end - i
        for k, pos in enumerate(reckoned):
            entry = entries[i + k]
            if pos is None or b_world is None:
                # No flow / no end anchor: hold the last reckoned position.
                if pos is None and reckoned:
                    # use previous reckoned if available else anchor
                    pos = reckoned[k - 1] if k > 0 and reckoned[k - 1] else a_world
                if pos is None:
                    pos = a_world
                points.append(make_point(entry, *pos, "interp"))
                continue
            # Drift guard: distance from straight line a->b at this t.
            if b_world is not None:
                t = (k + 1) / run_len if run_len else 1.0
                line_x = a_world[0] + (b_world[0] - a_world[0]) * t
                line_y = a_world[1] + (b_world[1] - a_world[1]) * t
                drift = math.hypot(pos[0] - line_x, pos[1] - line_y)
                if drift > FUSION_MAX_DEADRECKON_TILES * tile_size:
                    pos = (line_x, line_y)
                    points.append(make_point(entry, *pos, "interp"))
                    continue
            points.append(make_point(entry, *pos, "flow"))
        # Advance past this run.
        i = seg_end

    # Smooth each segment (split at "anchor" markers that follow a cutscene).
    _smooth_segment(points)
    return points


def build_path_file(route_dir: Path, **kwargs) -> Path:
    """Read route.json, build the fused path, write path.json + path.geojson."""
    route_path = route_dir / "route.json"
    with open(route_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    points = build_path(entries, route_dir, **kwargs)

    # path.json — one entry per frame in the fused path.
    path_json = [
        {
            "index": p.index, "frame": p.frame, "timestamp": p.timestamp,
            "world_x": round(p.world_x, 1), "world_y": round(p.world_y, 1),
            "tile_x": p.tile_x, "tile_y": p.tile_y, "source": p.source,
        }
        for p in points
    ]
    out_path = route_dir / "path.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(path_json, f, indent=2)

    # path.geojson — a LineString for map overlay.
    coords = [[p.world_x, p.world_y] for p in points]
    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"name": "guide route", "points": len(points)},
            "geometry": {"type": "LineString", "coordinates": coords},
        }],
    }
    geo_path = route_dir / "path.geojson"
    with open(geo_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)

    # Summary diagnostics.
    from collections import Counter
    sources = Counter(p.source for p in points)
    logger.info(f"Path built: {len(points)} points, sources={dict(sources)}")
    print(f"  Path points: {len(points)}  sources: {dict(sources)}")
    print(f"  Written: {out_path.name}, {geo_path.name}")
    return out_path
