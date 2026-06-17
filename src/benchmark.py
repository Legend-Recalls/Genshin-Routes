from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BenchmarkFrame:
    index: int
    elapsed_ms: float
    confidence: float
    tracking_mode: str | None = None
    event_type: str | None = None


class BenchmarkReport:
    """
    Collects localization benchmark metrics during route localization.
    Writes a JSON report next to the localized route data.
    """

    def __init__(self) -> None:
        self.started_at = time.time()

        # frame-level tracking
        self.frames_processed: int = 0
        self.total_elapsed_ms: float = 0.0
        self.frame_elapsed_ms: list[float] = []
        self.frame_confidences: list[float] = []

        # event counters
        self.global_searches: int = 0
        self.teleports_detected: int = 0
        self.map_switches: int = 0
        self.lost_frames: int = 0

        # confidence histogram (10 bins over [0,1])
        self.confidence_bins: list[float] = [0.0] * 10

        # low-confidence clusters (simple run-length encoding)
        self.low_confidence_regions: list[dict[str, Any]] = []

        # clustering thresholds
        self.low_conf_threshold: float = 0.12

        # store per-frame info to build clusters
        self._current_low_run: dict[str, Any] | None = None

        # timestamps of frames for segment stats if needed later
        self.frames: list[BenchmarkFrame] = []

    def record_frame(
        self,
        *,
        index: int,
        elapsed_ms: float,
        confidence: float,
        tracking_mode: str | None = None,
        event_type: str | None = None,
    ) -> None:
        self.frames_processed += 1
        self.total_elapsed_ms += elapsed_ms
        self.frame_elapsed_ms.append(elapsed_ms)
        self.frame_confidences.append(confidence)

        # histogram
        bin_idx = int(min(9, max(0, math.floor(confidence * 10.0))))
        self.confidence_bins[bin_idx] += 1

        # event-ish counters
        if tracking_mode == "lost" or event_type == "lost":
            self.lost_frames += 1

        if event_type == "teleport":
            self.teleports_detected += 1

        # low confidence clustering (simple)
        is_low = confidence < self.low_conf_threshold
        if is_low:
            if self._current_low_run is None:
                self._current_low_run = {
                    "start_index": index,
                    "end_index": index,
                    "frames": 1,
                    "min_confidence": confidence,
                }
            else:
                self._current_low_run["end_index"] = index
                self._current_low_run["frames"] += 1
                self._current_low_run["min_confidence"] = min(
                    self._current_low_run["min_confidence"], confidence
                )
        else:
            if self._current_low_run is not None:
                self.low_confidence_regions.append(self._current_low_run)
                self._current_low_run = None

        self.frames.append(
            BenchmarkFrame(
                index=index,
                elapsed_ms=elapsed_ms,
                confidence=confidence,
                tracking_mode=tracking_mode,
                event_type=event_type,
            )
        )

    def record_global_search(self) -> None:
        self.global_searches += 1

    def record_map_switch(self) -> None:
        self.map_switches += 1

    def _percentile(self, values: list[float], p: float) -> float:
        if not values:
            return 0.0
        values_sorted = sorted(values)
        if len(values_sorted) == 1:
            return values_sorted[0]
        k = (len(values_sorted) - 1) * (p / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return values_sorted[int(k)]
        d0 = values_sorted[int(f)] * (c - k)
        d1 = values_sorted[int(c)] * (k - f)
        return d0 + d1

    def generate(self, route_dir: Path) -> dict[str, Any]:
        # flush low run if still open
        if self._current_low_run is not None:
            self.low_confidence_regions.append(self._current_low_run)
            self._current_low_run = None

        avg_conf = sum(self.frame_confidences) / max(1, len(self.frame_confidences))
        median_conf = self._percentile(self.frame_confidences, 50)

        avg_elapsed = self.total_elapsed_ms / max(1, self.frames_processed)
        p95_elapsed = self._percentile(self.frame_elapsed_ms, 95)

        report: dict[str, Any] = {
            "frames_processed": self.frames_processed,
            "global_searches": self.global_searches,
            "average_confidence": avg_conf,
            "median_confidence": median_conf,
            "confidence_histogram": self.confidence_bins,
            "teleports_detected": self.teleports_detected,
            "map_switches": self.map_switches,
            "lost_frames": self.lost_frames,
            "lost_frame_pct": (self.lost_frames / max(1, self.frames_processed)),
            "avg_localization_ms": avg_elapsed,
            "p95_localization_ms": p95_elapsed,
            "low_confidence_regions": self.low_confidence_regions,
            "per_segment_stats": [],
            "generated_at_unix": time.time(),
        }

        out_path = route_dir / "benchmark_report.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[Benchmark] Saved benchmark report: {out_path}")
        return report

    def print_summary(self) -> None:
        print(
            f"[Benchmark] frames={self.frames_processed}, "
            f"avg_conf={sum(self.frame_confidences)/max(1,len(self.frame_confidences)):.3f}, "
            f"p95_ms={self._percentile(self.frame_elapsed_ms,95):.1f}, "
            f"teleports={self.teleports_detected}, lost_frames={self.lost_frames}"
        )
