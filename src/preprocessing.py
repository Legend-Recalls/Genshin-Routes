import cv2
import numpy as np


def create_circular_mask(h: int, w: int, radius_scale: float = 0.90) -> np.ndarray:
    """Create a 2D uint8 mask for cv2.detectAndCompute."""
    center = (w // 2, h // 2)
    radius = int(min(center) * radius_scale)
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, center, radius, 255, -1)
    return mask


def multi_scale(image: np.ndarray, scales=(0.9, 1.0, 1.1)) -> list[tuple[float, np.ndarray, np.ndarray]]:
    """Return multiple scaled variants of the minimap and their masks."""
    variants = []
    h, w = image.shape[:2]
    for scale in scales:
        if scale == 1.0:
            variants.append((scale, image, create_circular_mask(h, w)))
            continue
            
        new_w, new_h = int(w * scale), int(h * scale)
        if new_w > 0 and new_h > 0:
            resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            variants.append((scale, resized, create_circular_mask(new_h, new_w)))
            
    return variants


def prepare_minimap(image: np.ndarray, scales=(0.9, 1.0, 1.1)) -> list[tuple[float, np.ndarray, np.ndarray]]:
    """Pipeline: generate multi-scale variants with masks."""
    return multi_scale(image, scales)


def crop_title_region(frame: np.ndarray, profile: dict | None = None) -> np.ndarray:
    """Crop the title/caption region from a frame using profile ratios."""
    h, w = frame.shape[:2]

    if profile and "title_region_ratio" in profile:
        r = profile["title_region_ratio"]
        x1 = int(r["x"] * w)
        y1 = int(r["y"] * h)
        x2 = int((r["x"] + r["width"]) * w)
        y2 = int((r["y"] + r["height"]) * h)
    elif profile and "title_region" in profile:
        r = profile["title_region"]
        x1, y1 = r["x"], r["y"]
        x2, y2 = x1 + r["width"], y1 + r["height"]
    else:
        x1, y1, x2, y2 = int(w * 0.55), int(h * 0.07), int(w * 0.95), int(h * 0.17)

    return frame[y1:y2, x1:x2]
