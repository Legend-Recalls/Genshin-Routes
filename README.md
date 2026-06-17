# Route Explorer

Converts Genshin Impact guide videos into interactive routes by extracting minimap sequences, localizing them against the in-game map, and optimizing the trajectory.

## Quick Start

```bash
python main.py
```

## Pipeline

```
Video (YouTube/local)
    │
    ▼
[1] Extract Minimaps
    │  Calibrate → Verify → Extract
    │  Output: output/<video>/minimaps/*.png + route.json
    │
    ▼
[2] Localize Route
    │  AKAZE feature matching against tile database
    │  Adds tile_x, tile_y, lat/lng, confidence to route.json
    │
    ▼
[3] Optimize Route
    │  Viterbi smoothing over candidates
    │  Output: optimized_route.json
    │
    ▼
[4] View Route
    Web viewer at http://127.0.0.1:9090
```

## Directory Structure

```
route_explorer/
├── main.py                          # CLI entry point, menu
├── config.py                        # Paths, loads parent config
├── test_run.py                      # Quick localize+optimize test
├── src/
│   ├── __init__.py
│   ├── calibrate.py                 # Interactive minimap region selection
│   ├── extractor.py                 # Frame extraction + filmstrip generation
│   ├── localizer.py                 # AKAZE matching + state machine tracking
│   ├── optimizer.py                 # Viterbi trajectory optimization
│   ├── tile_source.py               # Tile database loader + patch builder
│   ├── preprocessing.py             # Multi-scale + circular mask generation
│   ├── viewer.py                    # HTTP server for web viewer
│   ├── viewer.html                  # Web viewer UI (Canvas + Google Maps)
│   ├── detector.py                  # Puzzle detection + minimap cropping
│   ├── ocr.py                       # EasyOCR text detection on title crops
│   ├── profile_manager.py           # Calibration profile CRUD
│   ├── downloader.py                # YouTube video download via yt-dlp
│   └── matchers/
│       ├── __init__.py
│       ├── base.py                  # CandidateImage, Candidate, BaseMatcher
│       └── akaze.py                 # AKAZE feature matcher plugin
├── reverse appsample/               # Downloaded map data
│   ├── download.py                  # CDN downloader (self-contained)
│   ├── overlay_metadata.json        # 256 overlay entries with bounds
│   ├── overlays/                    # 256 underground overlay PNGs
│   └── tiles/
│       ├── 13/                      # 482 tiles (zoom 13)
│       ├── 15/                      # 6515 tiles (zoom 15)
│       └── underground/             # 7 maps × 1024 tiles each
│           ├── chasm/
│           ├── enkanomiya/
│           ├── isles/
│           ├── veluriyam-mirage/
│           ├── sea-of-bygone-eras/
│           ├── simulanka/
│           └── temple-of-space/
└── output/                          # Per-video extraction results
    └── <video_name>/
        ├── minimaps/
        │   ├── 000000.png
        │   └── ...
        ├── route.json               # Raw extraction + localized positions
        ├── optimized_route.json     # Viterbi-smoothed trajectory
        ├── overview.jpg             # Filmstrip at 30s intervals
        └── verification_preview.jpg
```

## File Details

### `main.py`

CLI entry point. Menu options:

| Option | Function | Description |
|--------|----------|-------------|
| 1 | `handle_extract()` | Full extraction pipeline: calibrate → verify → extract, with optional auto-localize/optimize |
| 2 | `handle_localize()` | Run AKAZE matching on an existing route, with optional auto-optimize |
| 3 | `handle_optimize()` | Re-run Viterbi optimization on a localized route |
| 4 | `handle_view()` | Launch web viewer server |

### `config.py`

Extends the parent project's config. Loads parent `config.py` via `importlib` to avoid circular imports. Copies all parent constants (FPS, OCR thresholds, crop ratios, etc.) and defines route_explorer-specific paths:

- `REPO_ROOT` — parent project root
- `PROJECT_ROOT` — route_explorer root
- `OUTPUT_DIR` — `route_explorer/output/`
- `DATA_DIR` — `route_explorer/data/`

### `src/calibrate.py`

Interactive OpenCV-based minimap region selection.

| Class/Function | Purpose |
|----------------|---------|
| `ROI` | Dataclass: x, y, width, height. Methods: `to_dict()`, `to_ratio(w, h)` |
| `Circle` | Dataclass: center_x, center_y, radius. Method: `to_dict()` |
| `ROICreator` | Drag-to-select rectangle on a frame. Arrow keys nudge, +/- adjust step size |
| `CircleCreator` | Click center then edge to define minimap circle. +/- adjust radius, R resets |
| `seek_frame(video_path)` | Trackbar-based frame scrubber to find a HUD-visible frame |
| `calibrate_video(video_path)` | Full workflow: seek → ROI → circle → returns profile dict |

Profile dict structure:
```json
{
  "video_resolution": [1920, 1080],
  "minimap_region": {"x": 10, "y": 20, "width": 180, "height": 180},
  "minimap_region_ratio": {"x": 0.0052, "y": 0.0185, "width": 0.0938, "height": 0.1667},
  "minimap_circle": {"center_x": 90, "center_y": 90, "radius": 80}
}
```

### `src/extractor.py`

Frame extraction from video using calibration profiles.

| Function | Purpose |
|----------|---------|
| `verify_minimap_region(video_path, profile, num_frames=8, cols=4)` | Generates contact sheet showing crop regions on sampled frames |
| `verify_and_confirm(video_path, profile, output_dir)` | Shows preview in OpenCV window, asks terminal Y/n confirmation |
| `extract_minimaps(video_path, video_name, profile, fps=1, output_base)` | Streams video frame-by-frame, crops minimap region, saves PNGs. Returns path to route.json |
| `generate_filmstrip(route_entries, minimaps_dir, output_dir, interval_seconds=30)` | Vertical filmstrip overview image with timestamp labels |

### `src/localizer.py`

AKAZE feature matching with state machine tracking.

| Class/Function | Purpose |
|----------------|---------|
| `tile_to_latlng(tx, ty, zoom)` | Converts game tile coordinates to lat/lng via Mercator projection |
| `TrackingState` | Enum: UNINITIALIZED → TRACKING → EXPANDING → LOST |
| `LRUPatchCache(capacity=50)` | LRU cache for stitched tile patches |
| `Localizer.__init__(map_dir, coarse_zoom=13, fine_zoom=15, confidence_threshold=0.12)` | Initializes AKAZE detector, BFMatcher, precomputes coarse descriptors |
| `Localizer._precompute_descriptors()` | Loads all coarse zoom tiles, computes AKAZE keypoints+descriptors in parallel |
| `Localizer._coarse_search(mini_desc)` | Matches minimap against coarse tiles, returns top 20 candidates |
| `Localizer._coarse_to_fine_coords(coarse_tx, coarse_ty)` | Converts coarse tile coords to fine tile center |
| `Localizer._build_patch(center_tx, center_ty, radius=1)` | Stitches NxN tile grid around center into a single image |
| `Localizer._match_patch(patch, origin, center, mini_kp, mini_desc, shape)` | AKAZE match + RANSAC homography for sub-pixel localization |
| `Localizer._search_centers(centers, radius, variants)` | Multi-scale search across multiple center tiles |
| `Localizer.localize_frame(minimap)` | Full single-frame pipeline: coarse→fine→tracking state machine |
| `Localizer.localize_route(route_dir)` | Iterates all frames in route.json, writes localized positions back |

State machine behavior:
- **UNINITIALIZED/LOST**: Global search across all coarse tiles
- **TRACKING**: Search 3x3 around last known tile
- **EXPANDING**: Search 5x5 around last known tile (confidence dropped)
- Teleport detection: >1500px jump increments `segment_id`

### `src/optimizer.py`

Viterbi-based offline trajectory optimization.

| Class/Function | Purpose |
|----------------|---------|
| `RouteOptimizer.__init__(lost_emission_cost=2.0, lost_transition_penalty=1.0, max_speed_tiles_per_sec=1.5)` | Configures Viterbi cost parameters |
| `RouteOptimizer._calc_transition_cost(state_a, state_b)` | Velocity-based cost: normal if ≤1.5 tiles/s, heavy penalty for teleport (unless marked) |
| `RouteOptimizer.optimize_route(route_dir)` | Full Viterbi: forward pass + backtracking → writes optimized_route.json |

Viterbi states per frame: all candidates + a dummy "lost" state. Emission cost = `1.0 - confidence`. Transitions penalize impossible speeds.

### `src/tile_source.py`

Tile database loader and image composition.

| Class/Function | Purpose |
|----------------|---------|
| `TileSource.__init__(map_dir, zoom=15)` | Loads tile_database.json, sets active zoom level |
| `TileSource.tiles()` | Returns tile list for current zoom |
| `TileSource.bounds()` | Returns (min_x, max_x, min_y, max_y) |
| `TileSource.tile_lookup()` | Dict keyed by (x, y) for O(1) access |
| `TileSource.tile_candidate(tx, ty)` | Returns single tile as CandidateImage |
| `TileSource.tile_box_candidates(center_tx, center_ty, box_size=8)` | Returns NxN neighborhood + world/tile bounds |
| `TileSource.patch_candidate(world_x, world_y, patch_size=512)` | Stitches arbitrary patch from tiles |
| `TileSource._patch_from_tiles(x1, y1, x2, y2)` | Low-level tile stitching |
| `TileSource.overlays()` | Returns overlay metadata list |
| `TileSource.overlays_for_tile(tx, ty)` | Overlays that intersect a given tile |
| `TileSource.render_preview(max_size)` | Generates scaled-down map preview |

### `src/preprocessing.py`

Image preprocessing for matching.

| Function | Purpose |
|----------|---------|
| `create_circular_mask(h, w, radius_scale=0.90)` | Circular binary mask for AKAZE (ignores corners) |
| `multi_scale(image, scales=(0.9, 1.0, 1.1))` | Returns scaled variants with masks |
| `edge_version(image)` | Canny edge fallback for textureless minimaps |
| `prepare_minimap(image, scales)` | Pipeline: multi_scale → returns list of (scale, image, mask) |

### `src/matchers/base.py`

Shared types and base class for matcher plugins.

| Class/Function | Purpose |
|----------------|---------|
| `CandidateImage` | Dataclass: tile_x, tile_y, image, path, label, metadata |
| `Candidate` | Dataclass: scored result with debug_image |
| `Matcher` (Protocol) | Interface: `match(minimap) → list[Candidate]` |
| `BaseMatcher` | Base class with `_top(results)` sorting |
| `to_gray(image)` | BGR/BGRA/gray → grayscale |
| `resize_to_fit(template, target)` | Scale down if larger than target |
| `normalized_bgr(image, size)` | Normalize to 3-channel BGR |

### `src/matchers/akaze.py`

AKAZE feature matcher plugin.

| Class | Purpose |
|-------|---------|
| `AKAZEMatcher` | BFMatcher with NORM_HAMMING, distance threshold 80, returns top-k matches with debug images |

### `src/detector.py`

Puzzle detection from video frames (parent project module, copied in).

| Class | Purpose |
|-------|---------|
| `PuzzleDetection` | Dataclass: puzzle_id, type, timestamp, frame, crops, ocr_result |
| `PuzzleDetector` | Stateful detector: tracks puzzle numbers, triggers on new detection |

### `src/ocr.py`

EasyOCR text detection on title crops (parent project module, copied in).

| Class/Function | Purpose |
|----------------|---------|
| `OCRResult` | Dataclass: raw_text, parsed_name, parsed_number, valid |
| `get_reader()` | Lazy-init EasyOCR Reader with GPU auto-detect |
| `crop_title_region(frame, profile)` | Crops title area using profile ratios |
| `parse_ocr_text(text)` | Regex parser: "Spirit Carp#75" → name="Spirit Carp", number=75 |

### `src/profile_manager.py`

Calibration profile persistence (parent project module, copied in).

| Function | Purpose |
|----------|---------|
| `list_profiles()` | Returns sorted list of profile names |
| `load_profile(name)` | Loads profile JSON from `profiles/` |
| `save_profile(name, profile)` | Saves profile with timestamp |
| `get_default_profile()` | Returns built-in default ratios |
| `delete_profile(name)` | Removes profile file |

### `src/downloader.py`

YouTube video download via yt-dlp (parent project module, copied in).

| Function | Purpose |
|----------|---------|
| `is_local_file(path)` | Checks if path is a local video file |
| `download_video(url)` | Downloads from YouTube or returns local path |

### `src/viewer.py`

HTTP server for the web-based map viewer.

| Class/Function | Purpose |
|----------------|---------|
| `preload()` | Caches overlays + minimaps in memory, tiles served from disk |
| `TileHandler.do_GET()` | Routes: `/` (HTML), `/tiles/<zoom>/<name>`, `/overlays/<name>`, `/routes`, `/route/<name>/...` |
| `ThreadedHTTPServer` | Multi-threaded HTTP server |

Endpoints:
- `GET /` — viewer.html
- `GET /tiles/<zoom>/tile-<x>_<y>.jpg` — map tiles (disk-cached)
- `GET /overlays/overlay_<id>.png` — underground overlays (memory-cached)
- `GET /routes` — JSON list of available routes
- `GET /route/<name>/route.json` — localized route data
- `GET /route/<name>/optimized_route.json` — optimized route data
- `GET /route/<name>/minimaps/<file>` — minimap images (memory-cached)

### `src/viewer.html`

Single-page web viewer built on Canvas + Google Maps API. Features:
- Tile-based map rendering with zoom levels 13-15
- Underground overlay toggle ("Show Layered Maps")
- Route path visualization with lat/lng coordinates
- Frame-by-frame playback with minimap preview
- Stats panel showing confidence, tracking mode, tile position

### `reverse appsample/download.py`

Self-contained CDN downloader. Rerunnable (skips existing files).

| Function | Purpose |
|----------|---------|
| `fetch(url)` | HTTP GET with retries and 404 handling |
| `download_file(url, dest)` | Downloads single file, skips if exists |
| `load_black_tiles()` | Fetches black-tile.json for skip list |
| `download_teyvat_tiles(zooms=[13,15])` | Downloads overworld tiles, skipping black tiles |
| `download_underground_tiles()` | Downloads 7 underground maps at zoom 13 |
| `download_overlays()` | Downloads overlay PNGs (extracts URLs from live website JS) |
| `save_overlay_metadata()` | Saves overlay_metadata.json with bounds + tile bounds |
| `fetch_overlays_from_website()` | Playwright-based JS extraction from live site |

CDN structure:
- Teyvat: `https://game-cdn.appsample.com/gim/map-teyvat/v65-rc1/{z}/tile-{x}_{y}.jpg`
- Underground: `https://game-cdn.appsample.com/gim/map-{name}/{version}/13/tile-{x}_{y}.jpg`
- Overlays: `https://game-cdn.appsample.com/gim/overlays/{hash}.png`

### `test_run.py`

Quick test script — localizes and optimizes a hardcoded test route.

## Data Formats

### route.json (raw extraction)

```json
[{
  "index": 0,
  "timestamp": 0.0,
  "frame": 0,
  "minimap": "minimaps/000000.png"
}]
```

### route.json (after localization)

```json
[{
  "index": 0,
  "timestamp": 0.0,
  "frame": 0,
  "minimap": "minimaps/000000.png",
  "tile_x": -5,
  "tile_y": 3,
  "confidence": 0.3421,
  "match_score": 47,
  "tracking_mode": "tracking",
  "event_type": "normal",
  "segment_id": 0,
  "lat": -0.0512,
  "lng": 0.2834,
  "map_x": 1234.5,
  "map_y": 5678.9,
  "candidates": [...]
}]
```

### optimized_route.json

Same structure as localized route.json, but with Viterbi-smoothed positions. Lost states may appear where confidence was too low.

## Dependencies

- Python 3.11+
- OpenCV (`cv2`)
- NumPy
- Pillow
- EasyOCR + PyTorch (GPU optional)
- yt-dlp (for YouTube download)
- Playwright (for CDN downloader overlay extraction)
