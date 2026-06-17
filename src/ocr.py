import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import easyocr
import numpy as np

from config import OCR_CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)

READER: Optional[easyocr.Reader] = None


def get_reader() -> easyocr.Reader:
    global READER
    if READER is None:
        import torch
        use_gpu = torch.cuda.is_available()
        logger.info("EasyOCR GPU mode: %s", use_gpu)
        READER = easyocr.Reader(["en"], gpu=use_gpu)
    return READER


@dataclass
class OCRResult:
    raw_text: str
    confidence: float
    parsed_name: str
    parsed_number: int
    valid: bool = False


PUZZLE_PATTERN = re.compile(
    r"(.+?)\s*#?\s*(\d+)",
    re.IGNORECASE,
)


def parse_ocr_text(raw_text: str, confidence: float) -> OCRResult:
    text = raw_text.strip()

    match = PUZZLE_PATTERN.search(text)
    if match:
        name = match.group(1).strip()
        number_str = match.group(2).strip()
        try:
            number = int(number_str)
        except ValueError:
            number = -1
        valid = number > 0 and confidence >= OCR_CONFIDENCE_THRESHOLD
        return OCRResult(
            raw_text=text,
            confidence=confidence,
            parsed_name=name,
            parsed_number=number,
            valid=valid,
        )

    return OCRResult(
        raw_text=text,
        confidence=confidence,
        parsed_name="UNKNOWN",
        parsed_number=-1,
        valid=False,
    )


def crop_title_region(frame: np.ndarray, profile: dict | None = None) -> np.ndarray:
    h, w = frame.shape[:2]

    if profile and "title_region_ratio" in profile:
        r = profile["title_region_ratio"]
        x1 = int(r["x"] * w)
        y1 = int(r["y"] * h)
        x2 = int((r["x"] + r["width"]) * w)
        y2 = int((r["y"] + r["height"]) * h)
    else:
        from config import TITLE_CROP
        x1 = int(w * TITLE_CROP["x_start_ratio"])
        x2 = int(w * TITLE_CROP["x_end_ratio"])
        y1 = int(h * TITLE_CROP["y_start_ratio"])
        y2 = int(h * TITLE_CROP["y_end_ratio"])

    return frame[y1:y2, x1:x2]


def run_ocr_on_crop(crop: np.ndarray) -> list[tuple[str, float]]:
    reader = get_reader()

    small = cv2.resize(crop, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    results = reader.readtext(gray)
    return [(text, conf) for (_, text, conf) in results]


def run_ocr(frame: np.ndarray, frame_number: int, timestamp: float, profile: dict | None = None) -> OCRResult:
    crop = crop_title_region(frame, profile=profile)

    detections = run_ocr_on_crop(crop)

    if not detections:
        return OCRResult(
            raw_text="",
            confidence=0.0,
            parsed_name="UNKNOWN",
            parsed_number=-1,
            valid=False,
        )

    best_text = ""
    best_conf = 0.0
    for text, conf in detections:
        if conf > best_conf:
            best_text = text
            best_conf = conf

    combined_text = " ".join(text for text, _ in detections)

    result = parse_ocr_text(combined_text, best_conf)

    logger.debug(
        "Frame %d: raw='%s' conf=%.2f -> name='%s' num=%d valid=%s",
        frame_number, combined_text, best_conf,
        result.parsed_name, result.parsed_number, result.valid,
    )

    return result
