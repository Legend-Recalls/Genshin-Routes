"""AKAZE feature matcher."""

from __future__ import annotations

import cv2

from .base import BaseMatcher, Candidate, normalized_bgr, to_gray


class AKAZEMatcher(BaseMatcher):
    name = "AKAZE"

    def __init__(self, candidates, top_k: int = 20):
        super().__init__(candidates, top_k)
        self.detector = cv2.AKAZE_create()
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    @classmethod
    def is_available(cls) -> bool:
        return hasattr(cv2, "AKAZE_create")

    def match(self, minimap):
        mini_gray = to_gray(minimap)
        mini_kp, mini_desc = self.detector.detectAndCompute(mini_gray, None)
        if mini_desc is None or not mini_kp:
            return []

        results = []
        for candidate in self.candidates:
            cand_gray = to_gray(candidate.image)
            cand_kp, cand_desc = self.detector.detectAndCompute(cand_gray, None)
            good = []
            if cand_desc is None or not cand_kp:
                score = 0.0
                debug = None
            else:
                matches = sorted(self.matcher.match(mini_desc, cand_desc), key=lambda m: m.distance)
                good = [m for m in matches if m.distance < 80]
                score = min(1.0, len(good) / max(len(mini_kp), 1))
                debug = cv2.drawMatches(
                    normalized_bgr(minimap),
                    mini_kp,
                    normalized_bgr(candidate.image),
                    cand_kp,
                    good[:40],
                    None,
                    flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
                )
            results.append(
                Candidate(
                    candidate.tile_x,
                    candidate.tile_y,
                    float(score),
                    candidate.image,
                    candidate.path,
                    candidate.label,
                    {**candidate.metadata, "matches": len(good), "minimap_keypoints": len(mini_kp), "candidate_keypoints": len(cand_kp)},
                    debug,
                )
            )
        return self._top(results)
