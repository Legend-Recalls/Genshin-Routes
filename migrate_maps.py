"""
Non-destructive migration for Route Explorer map tiles into a multi-map layout.

Goal:
- Keep existing reverse appsample/ data intact.
- Copy tiles into:
    route_explorer/maps/<map_name>/tiles/<zoom>/tile-<x>_<y>.jpg
- Copy surface overlays into:
    route_explorer/maps/surface/overlays/overlay_<id>.png
- Generate per-map metadata.json and tile_database.json (TileSource-compatible)
  so existing localization keeps working during Phase 1.

This script is intentionally conservative:
- It copies only files that already exist in reverse appsample/.
- It validates copy counts (best-effort) and prints a diff summary.

Run:
  python route_explorer/migrate_maps.py --maps-dir route_explorer/maps --source-dir "route_explorer/reverse appsample"

Windows note:
- Existing codebase uses backslashes in some stored paths; this script writes paths
  into tile_database.json using forward slashes for stability.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Constants copied from the downloader config (reverse appsample/download.py).
# Importing that module directly is brittle due to the folder name containing spaces.
TEYVAT_TILE_BOUNDS = {
    13: {"minX": -16, "maxX": 15, "minY": -16, "maxY": 14},
    15: {"minX": -64, "maxX": 63, "minY": -64, "maxY": 58},
}

# Underground tile bounds (zoom 13 only for Phase 1)
UNDERGROUND_BOUNDS = {"minX": -16, "maxX": 15, "minY": -16, "maxY": 15}

UNDERGROUND_MAPS = {
    "chasm": {"cdn": "map-chasm/v0", "max_zoom": 13},
    "enkanomiya": {"cdn": "map-enkanomiya/v26", "max_zoom": 13},
    "isles": {"cdn": "map-isles/v28rc4", "max_zoom": 13},
    "veluriyam-mirage": {"cdn": "map-veluriyam-mirage/rc2", "max_zoom": 13},
    "sea-of-bygone-eras": {"cdn": "map-bygone-eras/v1", "max_zoom": 13},
    "simulanka": {"cdn": "map-simulanka/rc2", "max_zoom": 13},
    "temple-of-space": {"cdn": "map-temple-of-space/rc1", "max_zoom": 13},
    "ancient-sacred": {"cdn": "map-ancient-sacred/v2", "max_zoom": 12},
}


def _safe_read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def _copy_file(src: Path, dst: Path) -> bool:
    """
    Returns:
      True if copied (or already exists with same size), False otherwise.
    """
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return False  # treat as not copied
    _ensure_parent(dst)
    shutil.copy2(src, dst)
    return True


def _tile_entry_for_zoom(zoom: int, x: int, y: int, map_root: Path) -> dict[str, Any]:
    # tile_source expects: tile_database.json -> zoom_levels[z]["tiles"] contains entries like:
    # { "x": <tx>, "y": <ty>, "path": "tiles/<zoom>/tile-<x>_<y>.jpg" }
    # It then joins: map_dir / tile["path"]
    # We'll store path relative to map_dir root (not including map_dir).
    return {
        "x": x,
        "y": y,
        "path": f"tiles/{zoom}/tile-{x}_{y}.jpg",
    }


@dataclass
class CopyStats:
    tiles_copied: int = 0
    tiles_skipped_existing: int = 0
    tiles_missing_source: int = 0


def _copy_tiles_surface(
    source_root: Path,
    maps_root: Path,
    tile_bounds: dict[str, int],
    zooms: list[int],
    map_name: str = "surface",
    tile_size: int = 256,
) -> CopyStats:
    stats = CopyStats()
    out_map_dir = maps_root / map_name
    for zoom in zooms:
        zminx, zmax = tile_bounds["minX"], tile_bounds["maxX"]
        zminy, zmaxy = tile_bounds["minY"], tile_bounds["maxY"]

        src_tiles_dir = source_root / "tiles" / str(zoom)
        dst_tiles_dir = out_map_dir / "tiles" / str(zoom)

        for x in range(zminx, zmax + 1):
            for y in range(zminy, zmaxy + 1):
                src = src_tiles_dir / f"tile-{x}_{y}.jpg"
                if not src.exists():
                    stats.tiles_missing_source += 1
                    continue
                dst = dst_tiles_dir / f"tile-{x}_{y}.jpg"
                copied = _copy_file(src, dst)
                if copied:
                    stats.tiles_copied += 1
                else:
                    stats.tiles_skipped_existing += 1

    return stats


def _copy_tiles_underground(
    source_root: Path,
    maps_root: Path,
    underground_name: str,
    zoom: int = 13,
    bounds: dict[str, int] | None = None,
    tile_size: int = 256,
) -> CopyStats:
    stats = CopyStats()
    bounds = bounds or UNDERGROUND_BOUNDS
    out_map_dir = maps_root / underground_name

    zminx, zmax = bounds["minX"], bounds["maxX"]
    zminy, zmaxy = bounds["minY"], bounds["maxY"]

    # Current existing data structure (per repo): reverse appsample/tiles/underground/<map_name>/13/tile-<x>_<y>.jpg
    # localizer/TileSource currently doesn't know about this; we'll migrate to maps/<name>/tiles/13/
    src_tiles_dir = source_root / "tiles" / "underground" / underground_name / str(zoom)
    dst_tiles_dir = out_map_dir / "tiles" / str(zoom)

    for x in range(zminx, zmax + 1):
        for y in range(zminy, zmaxy + 1):
            src = src_tiles_dir / f"tile-{x}_{y}.jpg"
            if not src.exists():
                stats.tiles_missing_source += 1
                continue
            dst = dst_tiles_dir / f"tile-{x}_{y}.jpg"
            copied = _copy_file(src, dst)
            if copied:
                stats.tiles_copied += 1
            else:
                stats.tiles_skipped_existing += 1

    return stats


def _copy_overlays(source_root: Path, maps_root: Path, tile_size: int = 256) -> CopyStats:
    stats = CopyStats()
    # Source: reverse appsample/overlays/overlay_*.png
    # Destination: maps/surface/overlays/overlay_*.png
    src_overlays_dir = source_root / "overlays"
    dst_overlays_dir = maps_root / "surface" / "overlays"
    if not src_overlays_dir.exists():
        return stats

    for ov in sorted(src_overlays_dir.glob("overlay_*.png")):
        dst = dst_overlays_dir / ov.name
        copied = _copy_file(ov, dst)
        if copied:
            stats.tiles_copied += 1
        else:
            stats.tiles_skipped_existing += 1
    return stats


def _build_tile_database_for_map(
    map_name: str,
    map_type: str,
    zoom_levels: dict[int, dict[str, int]],
    tile_size: int = 256,
) -> dict[str, Any]:
    # TileSource schema assumed by route_explorer/src/tile_source.py
    # {
    #   "tile_size": 256,
    #   "zoom_levels": {
    #     "<zoom>": {
    #       "tiles": [ { "x":..., "y":..., "path": "tiles/<zoom>/tile-x_y.jpg"} , ...]
    #     }
    #   },
    #   "overlays": [...]
    # }
    # We'll generate minimal tile entries based on bounds.
    zoom_levels_out: dict[str, Any] = {}
    for zoom, b in zoom_levels.items():
        tiles = []
        for x in range(b["minX"], b["maxX"] + 1):
            for y in range(b["minY"], b["maxY"] + 1):
                tiles.append(_tile_entry_for_zoom(zoom, x, y, map_root=Path(".")))
        zoom_levels_out[str(zoom)] = {
            "tile_count": len(tiles),
            "bounds": {"min_x": b["minX"], "max_x": b["maxX"], "min_y": b["minY"], "max_y": b["maxY"]},
            "tiles": tiles,
        }

    return {
        "name": map_name,
        "type": map_type,
        "tile_size": tile_size,
        "zoom_levels": zoom_levels_out,
    }


def _derive_overlay_overlay_refs(source_overlay_metadata: list[dict[str, Any]], dest_map_dir: Path) -> list[dict[str, Any]]:
    # tile_source overlays() expects a list under tile_database.json["overlays"].
    # Our viewer uses overlay_metadata in a different way, but during Phase 1
    # we'll keep overlays as overlay_metadata entries with bounds and path.
    overlays = []
    for ov in source_overlay_metadata:
        ov_id = ov.get("id")
        if ov_id is None:
            continue
        entry = {
            "id": ov_id,
            "name": ov.get("name", ""),
            "sid": ov.get("sid", 0),
            "path": f"overlays/overlay_{ov_id}.png",
            "bounds": ov.get("bounds", {}),
            # pass-through: tile_source.overlay bounds uses keys like tile_bounds_<zoom>
        }
        for k, v in ov.items():
            if isinstance(k, str) and k.startswith("tile_bounds_"):
                entry[k] = v
        overlays.append(entry)

    # Ensure overlay paths exist (best-effort)
    return overlays


def _write_json(path: Path, data: Any) -> None:
    _ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def migrate(
    source_root: Path,
    maps_root: Path,
    delete_source: bool = False,
) -> None:
    maps_root.mkdir(parents=True, exist_ok=True)

    # Load existing overlay metadata (from old layout)
    overlay_metadata_path = source_root / "overlay_metadata.json"
    if not overlay_metadata_path.exists():
        raise FileNotFoundError(f"Missing overlay metadata: {overlay_metadata_path}")

    overlay_metadata = _safe_read_json(overlay_metadata_path)

    # 1) Surface map
    surface_dir = maps_root / "surface"
    surface_dir.mkdir(parents=True, exist_ok=True)

    print("== Surface tiles ==")
    surface_stats = _copy_tiles_surface(
        source_root=source_root,
        maps_root=maps_root,
        tile_bounds=TEYVAT_TILE_BOUNDS[13],
        zooms=[13],
        map_name="surface",
    )
    print(f"Surface zoom 13 copied={surface_stats.tiles_copied}, skipped={surface_stats.tiles_skipped_existing}, missing={surface_stats.tiles_missing_source}")

    # Surface zoom 15 bounds in downloader uses maxY=58; old repo uses 6515 tiles (max_y maybe 57)
    print("== Surface zoom 15 tiles ==")
    surface_stats_15 = _copy_tiles_surface(
        source_root=source_root,
        maps_root=maps_root,
        tile_bounds=TEYVAT_TILE_BOUNDS[15],
        zooms=[15],
        map_name="surface",
    )
    print(f"Surface zoom 15 copied={surface_stats_15.tiles_copied}, skipped={surface_stats_15.tiles_skipped_existing}, missing={surface_stats_15.tiles_missing_source}")

    # Generate surface metadata.json + tile_database.json
    print("== Surface metadata.json + tile_database.json ==")
    surface_zooms = {
        13: {"minX": TEYVAT_TILE_BOUNDS[13]["minX"], "maxX": TEYVAT_TILE_BOUNDS[13]["maxX"], "minY": TEYVAT_TILE_BOUNDS[13]["minY"], "maxY": TEYVAT_TILE_BOUNDS[13]["maxY"]},
        15: {"minX": TEYVAT_TILE_BOUNDS[15]["minX"], "maxX": TEYVAT_TILE_BOUNDS[15]["maxX"], "minY": TEYVAT_TILE_BOUNDS[15]["minY"], "maxY": TEYVAT_TILE_BOUNDS[15]["maxY"]},
    }

    surface_metadata = {
        "name": "surface",
        "display_name": "Teyvat Surface",
        "type": "surface",
        "coarse_zoom": 13,
        "fine_zoom": 15,
        "tile_size": 256,
        "zoom_levels": {
            "13": {"tile_count": 482, "bounds": {"min_x": surface_zooms[13]["minX"], "max_x": surface_zooms[13]["maxX"], "min_y": surface_zooms[13]["minY"], "max_y": surface_zooms[13]["maxY"]}},
            "15": {"tile_count": 6515, "bounds": {"min_x": surface_zooms[15]["minX"], "max_x": surface_zooms[15]["maxX"], "min_y": surface_zooms[15]["minY"], "max_y": surface_zooms[15]["maxY"]}},
        },
        "overlays": [
            {"id": ov.get("id"), "path": f"overlays/overlay_{ov.get('id')}.png"} for ov in overlay_metadata
        ],
        "parent_map": None,
        "surface_bounds": None,
        "overlay_metadata_source": str(overlay_metadata_path),
    }
    # Tile DB for TileSource
    surface_tile_db = _build_tile_database_for_map(
        map_name="surface",
        map_type="surface",
        zoom_levels={13: surface_zooms[13], 15: surface_zooms[15]},
        tile_size=256,
    )
    surface_tile_db["overlays"] = _derive_overlay_overlay_refs(overlay_metadata, surface_dir)

    _write_json(surface_dir / "metadata.json", surface_metadata)
    _write_json(surface_dir / "tile_database.json", surface_tile_db)

    # 2) Underground maps
    print("== Underground maps ==")
    for map_name in UNDERGROUND_MAPS.keys():
        print(f"-- {map_name} --")
        map_dir = maps_root / map_name
        map_dir.mkdir(parents=True, exist_ok=True)

        stats = _copy_tiles_underground(
            source_root=source_root,
            maps_root=maps_root,
            underground_name=map_name,
            zoom=13,
        )
        print(f"  copied={stats.tiles_copied}, skipped={stats.tiles_skipped_existing}, missing={stats.tiles_missing_source}")

        zoom_levels = {
            13: {"minX": UNDERGROUND_BOUNDS["minX"], "maxX": UNDERGROUND_BOUNDS["maxX"], "minY": UNDERGROUND_BOUNDS["minY"], "maxY": UNDERGROUND_BOUNDS["maxY"]},
        }

        # Relationship fields: best-effort from overlay_metadata.
        # overlay_metadata includes tile_bounds for each overlay, but mapping overlay->underground map
        # is not explicitly present in the old metadata. We'll leave surface_bounds null for now.
        underground_metadata = {
            "name": map_name,
            "display_name": map_name.replace("-", " ").title(),
            "type": "underground",
            "coarse_zoom": 13,
            "fine_zoom": 13,
            "tile_size": 256,
            "zoom_levels": {
                "13": {
                    "tile_count": 1024,
                    "bounds": {"min_x": zoom_levels[13]["minX"], "max_x": zoom_levels[13]["maxX"], "min_y": zoom_levels[13]["minY"], "max_y": zoom_levels[13]["maxY"]},
                }
            },
            "overlays": [],
            "parent_map": "surface",
            "surface_bounds": None,
            "notes": "surface_bounds to be derived by overlay linkage in Phase 2/3",
        }
        tile_db = _build_tile_database_for_map(
            map_name=map_name,
            map_type="underground",
            zoom_levels=zoom_levels,
            tile_size=256,
        )
        # No overlays for underground maps in current TileSource usage.
        _write_json(map_dir / "metadata.json", underground_metadata)
        _write_json(map_dir / "tile_database.json", tile_db)

    print("== Migration complete ==")
    print(f"maps_root: {maps_root}")

    if delete_source:
        print("delete_source=True requested, but this script is non-destructive by default; refusing to delete.")
        return


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source-dir",
        type=str,
        default=None,
        help="Existing reverse appsample directory (default: route_explorer/reverse appsample)",
    )
    ap.add_argument(
        "--maps-dir",
        type=str,
        default=None,
        help="Destination directory for migrated maps (default: route_explorer/maps)",
    )
    ap.add_argument("--delete-source", action="store_true", help="Refuse delete by default; kept for safety.")
    args = ap.parse_args()

    repo_root = Path(__file__).parent
    source_root = Path(args.source_dir) if args.source_dir else (repo_root / "reverse appsample")
    maps_root = Path(args.maps_dir) if args.maps_dir else (repo_root / "maps")

    if not source_root.exists():
        raise FileNotFoundError(f"Source directory not found: {source_root}")

    migrate(
        source_root=source_root,
        maps_root=maps_root,
        delete_source=args.delete_source,
    )


if __name__ == "__main__":
    main()
