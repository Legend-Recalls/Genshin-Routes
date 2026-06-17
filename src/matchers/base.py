"""Shared types and helpers for image matcher plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

import cv2
import numpy as np

from ..constants import TOP_K_CANDIDATES


@dataclass
class CandidateImage:
    """A map tile or manually extracted map patch to score."""

    tile_x: int
    tile_y: int
    image: np.ndarray
    path: Path | None = None
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Candidate:
    """A scored matcher result."""

    tile_x: int
    tile_y: int
    score: float
    image: np.ndarray
    path: Path | None = None
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    debug_image: np.ndarray | None = None


class Matcher(Protocol):
    name: str

    def match(self, minimap: np.ndarray) -> list[Candidate]:
        ...


class BaseMatcher:
    """Base class for plugins.

    New algorithms only need to accept an iterable of CandidateImage objects and
    implement match(minimap) -> list[Candidate].
    """

    name = "base"

    def __init__(self, candidates: Iterable[CandidateImage], top_k: int = TOP_K_CANDIDATES):
        self.candidates = list(candidates)
        self.top_k = top_k

    @classmethod
    def is_available(cls) -> bool:
        return True

    def match(self, minimap: np.ndarray) -> list[Candidate]:
        raise NotImplementedError

    def _top(self, results: list[Candidate]) -> list[Candidate]:
        return sorted(results, key=lambda c: c.score, reverse=True)[: self.top_k]


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def normalized_bgr(image: np.ndarray, size: tuple[int, int] | None = None) -> np.ndarray:
    out = image
    if out.ndim == 2:
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    elif out.shape[2] == 4:
        out = cv2.cvtColor(out, cv2.COLOR_BGRA2BGR)
    if size:
        out = cv2.resize(out, size, interpolation=cv2.INTER_AREA)
    return out
