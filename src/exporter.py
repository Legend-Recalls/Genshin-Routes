from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _load_route_json(route_dir: Path, prefer_optimized: bool = True) -> list[dict[str, Any]]:
    if prefer_optimized:
        p = route_dir / "optimized_route.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    p = route_dir / "route.json"
    if not p.exists():
        raise FileNotFoundError(f"route file not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _to_timestamp_seconds(entry: dict[str, Any]) -> float | None:
    # route.json appears to store timestamp as-is; keep permissive parsing
    ts = entry.get("timestamp", None)
    if ts is None:
        return None
    try:
        return float(ts)
    except (TypeError, ValueError):
        return None


def _feature_collection(feature_list: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": feature_list}


class RouteExporter:
    """Exports localized routes to interchange formats (JSON, GeoJSON, CSV)."""

    def __init__(self, route_dir: Path):
        self.route_dir = route_dir

    def load_route(self, prefer_optimized: bool = True) -> list[dict[str, Any]]:
        return _load_route_json(self.route_dir, prefer_optimized=prefer_optimized)

    def to_json(self, output: Path, prefer_optimized: bool = True) -> Path:
        entries = self.load_route(prefer_optimized=prefer_optimized)

        # Clean JSON: keep only core fields needed by viewer/export
        cleaned: list[dict[str, Any]] = []
        for e in entries:
            cleaned.append(
                {
                    "timestamp": e.get("timestamp"),
                    "frame": e.get("frame"),
                    "lat": e.get("lat"),
                    "lng": e.get("lng"),
                    "map_name": e.get("map_name"),
                    "confidence": e.get("confidence"),
                    "segment_id": e.get("segment_id"),
                    "event_type": e.get("event_type"),
                    "tracking_mode": e.get("tracking_mode"),
                }
            )

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
        return output

    def to_geojson(self, output: Path, prefer_optimized: bool = True) -> Path:
        entries = self.load_route(prefer_optimized=prefer_optimized)

        # Build LineString per segment_id where we have valid lat/lng
        segments: dict[Any, list[tuple[float, float, dict[str, Any]]]] = {}
        points_for_events: list[dict[str, Any]] = []

        for e in entries:
            lat = e.get("lat")
            lng = e.get("lng")
            seg = e.get("segment_id")
            if lat is None or lng is None:
                continue
            try:
                lat_f = float(lat)
                lng_f = float(lng)
            except (TypeError, ValueError):
                continue

            segments.setdefault(seg, []).append(
                (lng_f, lat_f, e)
            )  # lon,lat

            if e.get("event_type") in ("teleport", "lost"):
                # Add points for teleport/lost markers
                points_for_events.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [lng_f, lat_f]},
                        "properties": {
                            "timestamp": e.get("timestamp"),
                            "frame": e.get("frame"),
                            "map_name": e.get("map_name"),
                            "confidence": e.get("confidence"),
                            "segment_id": seg,
                            "event_type": e.get("event_type"),
                            "tracking_mode": e.get("tracking_mode"),
                        },
                    }
                )

        features: list[dict[str, Any]] = []

        # Stable ordering of segments by numeric if possible
        def seg_key(k: Any) -> Any:
            try:
                return (0, float(k))
            except Exception:
                return (1, str(k))

        for seg_id in sorted(segments.keys(), key=seg_key):
            coords = [[lon, lat] for (lon, lat, _) in segments[seg_id]]
            if len(coords) < 2:
                continue
            # map_name: use first non-null
            first = next((e for _, _, e in segments[seg_id] if e.get("map_name")), None)
            map_name = first.get("map_name") if first else None

            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {
                        "segment_id": seg_id,
                        "map_name": map_name,
                    },
                }
            )

        features.extend(points_for_events)

        out = _feature_collection(features)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(out, indent=2), encoding="utf-8")
        return output

    def to_csv(self, output: Path, prefer_optimized: bool = True) -> Path:
        entries = self.load_route(prefer_optimized=prefer_optimized)

        output.parent.mkdir(parents=True, exist_ok=True)

        headers = [
            "timestamp",
            "frame",
            "lat",
            "lng",
            "map_name",
            "confidence",
            "segment_id",
            "event_type",
            "tracking_mode",
            "map_x",
            "map_y",
        ]

        with output.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for e in entries:
                writer.writerow(
                    {
                        "timestamp": e.get("timestamp"),
                        "frame": e.get("frame"),
                        "lat": e.get("lat"),
                        "lng": e.get("lng"),
                        "map_name": e.get("map_name"),
                        "confidence": e.get("confidence"),
                        "segment_id": e.get("segment_id"),
                        "event_type": e.get("event_type"),
                        "tracking_mode": e.get("tracking_mode"),
                        "map_x": e.get("map_x"),
                        "map_y": e.get("map_y"),
                    }
                )

        return output

    def export_all(self, output_dir: Path) -> dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "route.json"
        geojson_path = output_dir / "route.geojson"
        csv_path = output_dir / "route.csv"

        self.to_json(json_path, prefer_optimized=True)
        self.to_geojson(geojson_path, prefer_optimized=True)
        self.to_csv(csv_path, prefer_optimized=True)

        return {"json": json_path, "geojson": geojson_path, "csv": csv_path}
