import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from src.ocr import OCRResult
from src.preprocessing import crop_title_region

logger = logging.getLogger(__name__)


@dataclass
class PuzzleDetection:
    puzzle_id: int
    puzzle_type: str
    timestamp: float
    frame_number: int
    frame: np.ndarray
    minimap_crop: np.ndarray
    title_crop: np.ndarray
    ocr_result: OCRResult


class PuzzleDetector:
    def __init__(self, profile: dict | None = None):
        self._profile = profile
        self._last_number: Optional[int] = None
        self._last_name: Optional[str] = None
        self._detections: list[PuzzleDetection] = []

    def process_frame(
        self,
        frame: np.ndarray,
        frame_number: int,
        timestamp: float,
        ocr_result: OCRResult,
    ) -> Optional[PuzzleDetection]:
        if not ocr_result.valid:
            return None

        if ocr_result.parsed_number == self._last_number:
            return None

        self._last_number = ocr_result.parsed_number
        self._last_name = ocr_result.parsed_name

        title_crop = crop_title_region(frame, profile=self._profile)
        minimap_crop = crop_minimap(frame, profile=self._profile)

        detection = PuzzleDetection(
            puzzle_id=ocr_result.parsed_number,
            puzzle_type=ocr_result.parsed_name,
            timestamp=timestamp,
            frame_number=frame_number,
            frame=frame.copy(),
            minimap_crop=minimap_crop,
            title_crop=title_crop,
            ocr_result=ocr_result,
        )

        self._detections.append(detection)
        logger.info(
            "Puzzle detected: %s #%d at %.1fs (frame %d)",
            ocr_result.parsed_name, ocr_result.parsed_number,
            timestamp, frame_number,
        )
        print(f"  Puzzle detected: {ocr_result.parsed_name} #{ocr_result.parsed_number}")

        return detection

    @property
    def detections(self) -> list[PuzzleDetection]:
        return self._detections


def crop_minimap(frame: np.ndarray, profile: dict | None = None) -> np.ndarray:
    h, w = frame.shape[:2]

    if profile and "minimap_region_ratio" in profile:
        r = profile["minimap_region_ratio"]
        x1 = int(r["x"] * w)
        y1 = int(r["y"] * h)
        x2 = int((r["x"] + r["width"]) * w)
        y2 = int((r["y"] + r["height"]) * h)
    else:
        from config import MINIMAP_CROP
        x1 = int(w * MINIMAP_CROP["x_start_ratio"])
        x2 = int(w * MINIMAP_CROP["x_end_ratio"])
        y1 = int(h * MINIMAP_CROP["y_start_ratio"])
        y2 = int(h * MINIMAP_CROP["y_end_ratio"])

    return frame[y1:y2, x1:x2]
