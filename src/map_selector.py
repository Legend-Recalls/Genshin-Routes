from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .map_dataset import MapDataset
from .map_manager import MapManager


class MapSelector:
    """Decides which map(s) the localizer should search."""

    def __init__(self, map_manager: MapManager):
        self.map_manager = map_manager

    def select(
        self,
        current_map: MapDataset | None,
        tracking_ok: bool,
        last_position: Tuple[float, float] | None,  # lat, lng
    ) -> List[MapDataset]:
        """
        Initial dumb strategy:
        1) tracking_ok -> [current_map]
        2) otherwise:
           - if last_position known, prefer nearby underground maps (based on surface_bounds overlap)
           - then include surface
           - then include all maps as fallback
        """
        if tracking_ok and current_map is not None:
            return [current_map]

        if last_position is None:
            return self.map_manager.all_maps()

        lat, lng = last_position

        candidates: List[MapDataset] = []
        nearby = self.map_manager.maps_near(lat, lng)

        # Prefer underground candidates first (when relevant), but always allow surface.
        for m in nearby:
            if m.map_type == "underground" and m not in candidates:
                candidates.append(m)

        # Ensure surface is included.
        for m in self.map_manager.surface_maps():
            if m not in candidates:
                candidates.append(m)

        # Fill with remaining maps (global fallback).
        for m in self.map_manager.all_maps():
            if m not in candidates:
                candidates.append(m)

        return candidates
