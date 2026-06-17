"""Extract minimap frames from video using calibration profiles."""
import json
import logging
import sys
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

# Ensure parent project is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.detector import crop_minimap
from src.preprocessing import crop_title_region
from src.profile_manager import get_default_profile
from src.constants import (
    DEFAULT_VERIFICATION_FRAMES, DEFAULT_VERIFICATION_COLS,
    THUMB_WIDTH, THUMB_HEIGHT, SHEET_PADDING, LABEL_HEIGHT,
    SHEET_BG_COLOR, JPEG_QUALITY, VERIFY_WINDOW_SIZE,
    DEFAULT_EXTRACTION_FPS, OCR_DOWNSCALE_FACTOR,
    FILMSTRIP_INTERVAL_SECONDS, FILMSTRIP_THUMB_SIZE, FILMSTRIP_PADDING,
    FILMSTRIP_LABEL_HEIGHT, FILMSTRIP_EXTRA_WIDTH, FILMSTRIP_BG_COLOR,
    FILMSTRIP_CIRCLE_THICKNESS, FILMSTRIP_FONT_SCALE,
)

logger = logging.getLogger(__name__)


def verify_minimap_region(
    video_path: Path,
    profile: dict,
    num_frames: int = DEFAULT_VERIFICATION_FRAMES,
    cols: int = DEFAULT_VERIFICATION_COLS,
    output_path: Path | None = None,
) -> Path:
    """Generate a contact sheet showing minimap crop region on sampled frames.

    This is the mandatory verification step before extraction.
    Shows the user exactly what will be cropped so they can confirm.

    Args:
        video_path: Path to video file
        profile: Calibration profile with minimap_region_ratio
        num_frames: Number of frames to sample
        cols: Columns in contact sheet
        output_path: Where to save preview

    Returns:
        Path to preview image
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        raise RuntimeError("Cannot read frame count")

    minimap_ratio = profile.get("minimap_region_ratio", {})
    title_ratio = profile.get("title_region_ratio", {})
    circle = profile.get("minimap_circle", {})

    thumb_w = THUMB_WIDTH
    thumb_h = THUMB_HEIGHT
    rows = (num_frames + cols - 1) // cols
    padding = SHEET_PADDING
    label_h = LABEL_HEIGHT

    sheet_h = rows * (thumb_h + label_h + padding) + padding
    sheet_w = cols * (thumb_w + padding) + padding
    sheet = np.zeros((sheet_h, sheet_w, 3), dtype=np.uint8)
    sheet[:] = SHEET_BG_COLOR

    indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)

    for i, frame_idx in enumerate(indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue

        h, w = frame.shape[:2]
        thumb = cv2.resize(frame, (thumb_w, thumb_h))
        sx = thumb_w / w
        sy = thumb_h / h

        # Draw minimap region (blue)
        if minimap_ratio:
            mx1 = int(minimap_ratio["x"] * w * sx)
            my1 = int(minimap_ratio["y"] * h * sy)
            mx2 = int((minimap_ratio["x"] + minimap_ratio["width"]) * w * sx)
            my2 = int((minimap_ratio["y"] + minimap_ratio["height"]) * h * sy)
            cv2.rectangle(thumb, (mx1, my1), (mx2, my2), (255, 0, 0), 2)

            # Draw minimap circle (green)
            if circle and circle.get("radius", 0) > 0:
                cx = int((minimap_ratio["x"] * w + circle["center_x"]) * sx)
                cy = int((minimap_ratio["y"] * h + circle["center_y"]) * sy)
                cr = int(circle["radius"] * sx)
                cv2.circle(thumb, (cx, cy), cr, (0, 255, 0), 2)

        # Draw title/caption region (yellow)
        if title_ratio:
            tx1 = int(title_ratio["x"] * w * sx)
            ty1 = int(title_ratio["y"] * h * sy)
            tx2 = int((title_ratio["x"] + title_ratio["width"]) * w * sx)
            ty2 = int((title_ratio["y"] + title_ratio["height"]) * h * sy)
            cv2.rectangle(thumb, (tx1, ty1), (tx2, ty2), (0, 255, 255), 2)

        row = i // cols
        col = i % cols
        y_off = padding + row * (thumb_h + label_h + padding)
        x_off = padding + col * (thumb_w + padding)

        sheet[y_off:y_off + thumb_h, x_off:x_off + thumb_w] = thumb

        ts = frame_idx / cap.get(cv2.CAP_PROP_FPS) if cap.get(cv2.CAP_PROP_FPS) > 0 else 0
        mins = int(ts) // 60
        secs = int(ts) % 60
        label = f"{mins:02d}:{secs:02d}"
        cv2.putText(sheet, label, (x_off + 5, y_off + thumb_h + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    cap.release()

    if output_path is None:
        output_path = Path("output") / "verification_preview.jpg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), sheet, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])

    logger.info("Verification preview saved: %s", output_path)
    return output_path


def verify_and_confirm(
    video_path: Path,
    profile: dict,
    output_dir: Path,
) -> bool:
    """Show verification preview in window, ask to confirm, then delete.

    Returns True if user confirms, False to abort.
    """
    import tempfile

    # Generate preview to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    verify_minimap_region(video_path, profile, output_path=tmp_path)

    # Show in window
    img = cv2.imread(str(tmp_path))
    if img is not None:
        cv2.namedWindow("Verification", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Verification", *VERIFY_WINDOW_SIZE)
        cv2.imshow("Verification", img)

        print(f"\n  Blue = Minimap crop | Green = Minimap circle | Yellow = Title/Caption")
        print(f"  Does the crop region look correct?")
        print("  Press any key to continue...")

        cv2.waitKey(0)
        cv2.destroyWindow("Verification")

    # Delete temp file
    tmp_path.unlink(missing_ok=True)

    # Ask confirmation in terminal
    while True:
        choice = input("  Proceed with extraction? [Y/n]: ").strip().lower()
        if choice in ("", "y", "yes"):
            return True
        if choice in ("n", "no"):
            return False
        print("  Please enter Y or n")


def extract_minimaps(
    video_path: str | Path,
    video_name: str,
    profile: dict | None = None,
    fps: int = DEFAULT_EXTRACTION_FPS,
    output_base: Path | None = None,
) -> Path:
    """Extract minimap and title crops from video at specified FPS.

    Args:
        video_path: Path to video file (absolute or relative to caller)
        video_name: Name for output folder
        profile: Calibration profile dict with minimap_region_ratio and title_region_ratio (None for default)
        fps: Sampling rate
        output_base: Base output directory (defaults to route_explorer/output)

    Returns:
        Path to route.json
    """
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if not video_name or not isinstance(video_name, str):
        raise ValueError(f"video_name must be a non-empty string, got {video_name!r}")

    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")

    if profile is None:
        profile = get_default_profile()

    if output_base is None:
        output_base = Path(__file__).parent.parent / "output"

    route_dir = output_base / video_name
    minimaps_dir = route_dir / "minimaps"
    titles_dir = route_dir / "titles"
    minimaps_dir.mkdir(parents=True, exist_ok=True)
    titles_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    source_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_interval = max(1, round(source_fps / fps))
    duration = total_frames / source_fps if source_fps > 0 else 0

    logger.info(
        "Extracting minimaps: %s (%.1fs, %.1f fps, every %d frames)",
        video_path.name, duration, source_fps, frame_interval,
    )
    print(f"Extracting minimaps from {video_path.name}...")
    print(f"  Duration: {duration:.1f}s, Source: {source_fps:.1f} fps, Sampling: {fps} fps")

    has_title = profile and "title_region_ratio" in profile

    ocr_reader = None
    if has_title:
        try:
            from src.ocr import get_reader
            ocr_reader = get_reader()
            print("  OCR enabled for title/caption extraction")
        except Exception as e:
            logger.warning("OCR not available, title crops will be saved without text: %s", e)
            has_title = False

    route_entries = []
    frame_idx = 0
    extracted = 0
    progress = tqdm(total=total_frames, desc="Extracting", unit="frame")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            minimap = crop_minimap(frame, profile=profile)
            minimap_name = f"{extracted:06d}.png"
            cv2.imwrite(str(minimaps_dir / minimap_name), minimap)

            timestamp = frame_idx / source_fps
            entry = {
                "index": extracted,
                "timestamp": round(timestamp, 3),
                "frame": frame_idx,
                "minimap": f"minimaps/{minimap_name}",
            }

            if has_title:
                title_crop = crop_title_region(frame, profile=profile)
                title_name = f"{extracted:06d}.png"
                cv2.imwrite(str(titles_dir / title_name), title_crop)
                entry["title_crop"] = f"titles/{title_name}"

                if ocr_reader is not None:
                    import easyocr
                    small = cv2.resize(title_crop, None, fx=OCR_DOWNSCALE_FACTOR, fy=OCR_DOWNSCALE_FACTOR, interpolation=cv2.INTER_AREA)
                    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    results = ocr_reader.readtext(gray)
                    if results:
                        texts = [(text, conf) for (_, text, conf) in results]
                        best_text = max(texts, key=lambda x: x[1])
                        entry["caption_raw"] = best_text[0]
                        entry["caption_confidence"] = round(best_text[1], 4)
                    else:
                        entry["caption_raw"] = ""
                        entry["caption_confidence"] = 0.0

            route_entries.append(entry)
            extracted += 1

        frame_idx += 1
        progress.update(1)

    progress.close()
    cap.release()

    # Save route.json
    route_dir = output_base / video_name
    route_dir.mkdir(parents=True, exist_ok=True)
    route_path = route_dir / "route.json"
    with open(route_path, "w", encoding="utf-8") as f:
        json.dump(route_entries, f, indent=2)

    logger.info("Extracted %d minimaps to %s", extracted, minimaps_dir)
    print(f"  Extracted {extracted} minimaps")

    # Generate filmstrip overview
    generate_filmstrip(route_entries, minimaps_dir, route_dir)

    return route_path


def generate_filmstrip(
    route_entries: list[dict],
    minimaps_dir: Path,
    output_dir: Path,
    interval_seconds: int = FILMSTRIP_INTERVAL_SECONDS,
    thumb_size: int = FILMSTRIP_THUMB_SIZE,
    padding: int = FILMSTRIP_PADDING,
    label_height: int = FILMSTRIP_LABEL_HEIGHT,
) -> Path:
    """Generate a filmstrip overview image showing minimaps at regular intervals.

    Layout:
        00:00  ○
        00:30  ○
        01:00  ○
        ...

    Args:
        route_entries: List of route.json entries
        minimaps_dir: Directory containing minimap PNGs
        output_dir: Where to save overview.jpg
        interval_seconds: Seconds between shown minimaps
        thumb_size: Width/height of each minimap thumbnail
        padding: Pixels between entries
        label_height: Pixels for timestamp label

    Returns:
        Path to overview.jpg
    """
    if not route_entries:
        logger.warning("No route entries for filmstrip")
        return output_dir / "overview.jpg"

    # Select entries at regular intervals
    selected = []
    last_shown_ts = -interval_seconds  # Force first entry

    for entry in route_entries:
        ts = entry["timestamp"]
        if ts - last_shown_ts >= interval_seconds:
            selected.append(entry)
            last_shown_ts = ts

    # Always include last entry
    if selected[-1] != route_entries[-1]:
        selected.append(route_entries[-1])

    n = len(selected)
    if n == 0:
        logger.warning("No entries selected for filmstrip")
        return output_dir / "overview.jpg"

    # Layout: vertical filmstrip
    cell_height = thumb_size + label_height + padding
    total_height = n * cell_height + padding
    total_width = thumb_size + padding * 2 + FILMSTRIP_EXTRA_WIDTH  # Extra space for labels

    strip = np.zeros((total_height, total_width, 3), dtype=np.uint8)
    strip[:] = FILMSTRIP_BG_COLOR  # Dark background

    for i, entry in enumerate(selected):
        minimap_path = minimaps_dir / Path(entry["minimap"]).name
        if not minimap_path.exists():
            continue

        img = cv2.imread(str(minimap_path))
        if img is None:
            continue

        # Resize to thumbnail
        thumb = cv2.resize(img, (thumb_size, thumb_size))

        # Calculate position
        y_off = padding + i * cell_height
        x_off = padding

        # Place minimap
        strip[y_off:y_off + thumb_size, x_off:x_off + thumb_size] = thumb

        # Draw green circle indicator
        center = (x_off + thumb_size // 2, y_off + thumb_size // 2)
        cv2.circle(strip, center, thumb_size // 2 - 2, (0, 255, 0), FILMSTRIP_CIRCLE_THICKNESS)

        # Add timestamp label
        ts = entry["timestamp"]
        minutes = int(ts) // 60
        seconds = int(ts) % 60
        label = f"{minutes:02d}:{seconds:02d}"

        label_x = x_off + thumb_size + 15
        label_y = y_off + thumb_size // 2 + 5
        cv2.putText(strip, label, (label_x, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, FILMSTRIP_FONT_SCALE, (200, 200, 200), 2)

    # Save
    overview_path = output_dir / "overview.jpg"
    cv2.imwrite(str(overview_path), strip, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])

    logger.info("Filmstrip saved: %s (%d entries)", overview_path, n)
    print(f"  Filmstrip saved: {overview_path}")

    return overview_path
