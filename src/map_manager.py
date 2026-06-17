from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .map_dataset import MapDataset


class MapManager:
    """Discovers and manages all available map datasets."""

    def __init__(self, maps_dir: Path):
        self.maps_dir = maps_dir
        self.maps: dict[str, MapDataset] = {}
        self.active_map: MapDataset | None = None
        self.discover_maps()

    def discover_maps(self) -> list[str]:
        self.maps.clear()
        if not self.maps_dir.exists():
            return []

        for map_dir in sorted([p for p in self.maps_dir.iterdir() if p.is_dir()]):
            metadata_path = map_dir / "metadata.json"
            if not metadata_path.exists():
                continue
            dataset = MapDataset.load(map_dir)
            self.maps[dataset.name] = dataset

        return sorted(self.maps.keys())

    def get_map(self, name: str) -> MapDataset:
        if name not in self.maps:
            raise KeyError(f"Unknown map: {name}")
        return self.maps[name]

    def set_active(self, name: str) -> MapDataset:
        self.active_map = self.get_map(name)
        return self.active_map

    def all_maps(self) -> list[MapDataset]:
        return list(self.maps.values())

    def underground_maps(self) -> list[MapDataset]:
        return [m for m in self.maps.values() if m.map_type == "underground"]

    def surface_maps(self) -> list[MapDataset]:
        return [m for m in self.maps.values() if m.map_type == "surface"]

    def maps_near(self, lat: float, lng: float) -> list[MapDataset]:
        """
        Dumb fallback proximity selection:
        - If a dataset has surface_bounds, prefer those whose bounds contain (lat,lng).
        - Otherwise return all maps (caller can rank).
        """
        candidates: list[MapDataset] = []

        for m in self.maps.values():
            sb = m.surface_bounds
            if not sb:
                continue
            # Expected overlay_metadata.json shape: {west,east,north,south} or similar.
            # We'll support a couple likely keys.
            west = sb.get("west") if isinstance(sb, dict) else None
            east = sb.get("east") if isinstance(sb, dict) else None
            north = sb.get("north") if isinstance(sb, dict) else None
            south = sb.get("south") if isinstance(sb, dict) else None

            # Some sources might store min/max in different keys
            min_lng = sb.get("min_lng", west)
            max_lng = sb.get("max_lng", east)
            min_lat = sb.get("min_lat", south)
            max_lat = sb.get("max_lat", north)

            if min_lng is None or max_lng is None or min_lat is None or max_lat is None:
                continue

            if (min_lat <= lat <= max_lat) and (min_lng <= lng <= max_lng):
                candidates.append(m)

        if candidates:
            return candidates

        return list(self.maps.values())
