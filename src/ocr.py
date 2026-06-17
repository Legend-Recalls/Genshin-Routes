import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import easyocr
import numpy as np

from config import OCR_CONFIDENCE_THRESHOLD
from src.preprocessing import crop_title_region
from src.constants import OCR_DOWNSCALE_FACTOR, INVALID_PUZZLE_NUMBER

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
            number = INVALID_PUZZLE_NUMBER
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
        parsed_number=INVALID_PUZZLE_NUMBER,
        valid=False,
    )


def run_ocr_on_crop(crop: np.ndarray) -> list[tuple[str, float]]:
    reader = get_reader()

    small = cv2.resize(crop, None, fx=OCR_DOWNSCALE_FACTOR, fy=OCR_DOWNSCALE_FACTOR, interpolation=cv2.INTER_AREA)
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
            parsed_number=INVALID_PUZZLE_NUMBER,
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
