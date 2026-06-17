from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .tile_source import TileSource


@dataclass(frozen=True)
class MapDataset:
    """
    Self-contained dataset for one map region.

    Phase-1 compatibility:
    - We keep using TileSource's expectations by pointing TileSource at this map's directory
      containing tile_database.json.
    """
    name: str
    display_name: str
    map_type: str
    map_dir: Path
    metadata: dict[str, Any]

    coarse_zoom: int
    fine_zoom: int
    tile_size: int

    parent_map: str | None = None
    surface_bounds: dict[str, Any] | None = None

    def tile_source(self, zoom: int) -> TileSource:
        return TileSource(self.map_dir, zoom=zoom)

    def tile_database_path(self) -> Path:
        return self.map_dir / "tile_database.json"

    @staticmethod
    def load(map_dir: Path) -> "MapDataset":
        metadata_path = map_dir / "metadata.json"
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        name = metadata["name"]
        display_name = metadata.get("display_name", name)
        map_type = metadata.get("type", "surface")

        zoom_levels = metadata["zoom_levels"]
        coarse_zoom = int(metadata.get("coarse_zoom", min(map(int, zoom_levels.keys()))))
        fine_zoom = int(metadata.get("fine_zoom", max(map(int, zoom_levels.keys()))))

        tile_size = int(metadata.get("tile_size", 256))

        parent_map = metadata.get("parent_map", None)
        surface_bounds = metadata.get("surface_bounds", None)

        return MapDataset(
            name=name,
            display_name=display_name,
            map_type=map_type,
            map_dir=map_dir,
            metadata=metadata,
            coarse_zoom=coarse_zoom,
            fine_zoom=fine_zoom,
            tile_size=tile_size,
            parent_map=parent_map,
            surface_bounds=surface_bounds,
        )
