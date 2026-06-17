"""Interactive minimap region selection for each video."""
import cv2
import numpy as np
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ROI:
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    def to_ratio(self, frame_w: int, frame_h: int) -> dict:
        return {
            "x": round(self.x / frame_w, 6),
            "y": round(self.y / frame_h, 6),
            "width": round(self.width / frame_w, 6),
            "height": round(self.height / frame_h, 6),
        }


@dataclass
class Circle:
    center_x: int
    center_y: int
    radius: int

    def to_dict(self) -> dict:
        return {"center_x": self.center_x, "center_y": self.center_y, "radius": self.radius}


WINDOW_NAME = "Calibrate"


class ROICreator:
    def __init__(self, frame: np.ndarray, label: str):
        self.frame = frame.copy()
        self.display = frame.copy()
        self.label = label
        self.h, self.w = frame.shape[:2]
        self.dragging = False
        self.drag_start = None
        self.roi: Optional[ROI] = None
        self.move_step = 5

    def _draw(self) -> None:
        self.display = self.frame.copy()
        cv2.putText(
            self.display,
            f"{self.label} - Drag to select, Arrows=nudge, +/- step, Enter=ok, Esc=cancel",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1,
        )
        if self.roi:
            x, y, w, h = self.roi.x, self.roi.y, self.roi.width, self.roi.height
            cv2.rectangle(self.display, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(self.display, f"{w}x{h}", (x, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    def _on_mouse(self, event, x, y, flags, param) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            self.dragging = True
            self.drag_start = (x, y)
            self.roi = ROI(x, y, 0, 0)
        elif event == cv2.EVENT_MOUSEMOVE and self.dragging:
            sx, sy = self.drag_start
            self.roi = ROI(min(sx, x), min(sy, y), abs(x - sx), abs(y - sy))
        elif event == cv2.EVENT_LBUTTONUP:
            self.dragging = False
            if self.roi and self.roi.width < 5 and self.roi.height < 5:
                self.roi = None

    def select(self) -> Optional[ROI]:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, min(self.w, 1280), min(self.h, 720))
        cv2.setMouseCallback(WINDOW_NAME, self._on_mouse)

        print(f"\nDraw {self.label} region:")
        print("  Drag to draw | Arrows: nudge | +/-: step size | Enter: confirm | Esc: cancel")

        while True:
            self._draw()
            cv2.imshow(WINDOW_NAME, self.display)
            key = cv2.waitKey(30) & 0xFF

            if key == 13:
                if self.roi and self.roi.width > 10 and self.roi.height > 10:
                    cv2.destroyWindow(WINDOW_NAME)
                    return self.roi
                print("  ROI too small")
            elif key == 27:
                cv2.destroyWindow(WINDOW_NAME)
                return None
            elif key == 81:
                self.roi.x -= self.move_step if self.roi else 0
            elif key == 82:
                self.roi.y -= self.move_step if self.roi else 0
            elif key == 83:
                self.roi.x += self.move_step if self.roi else 0
            elif key == 84:
                self.roi.y += self.move_step if self.roi else 0
            elif key in (ord("+"), ord("=")):
                self.move_step = min(50, self.move_step + 5)
                print(f"  Step: {self.move_step}px")
            elif key == ord("-"):
                self.move_step = max(5, self.move_step - 5)
                print(f"  Step: {self.move_step}px")
        return None


class CircleCreator:
    def __init__(self, minimap_crop: np.ndarray):
        self.crop = minimap_crop.copy()
        self.h, self.w = minimap_crop.shape[:2]
        self.center: Optional[tuple[int, int]] = None
        self.circle: Optional[Circle] = None
        self.radius_offset = 0

    def _draw(self) -> None:
        display = self.crop.copy()
        cv2.putText(display, "Click center, then edge. +/- radius. Enter=ok, Esc=cancel, R=reset",
                    (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        if self.center:
            cv2.circle(display, self.center, 5, (0, 0, 255), -1)
        if self.circle:
            r = self.circle.radius + self.radius_offset
            cv2.circle(display, (self.circle.center_x, self.circle.center_y), r, (0, 255, 0), 2)
        return display

    def _on_mouse(self, event, x, y, flags, param) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            if self.center is None:
                self.center = (x, y)
            else:
                dx = x - self.center[0]
                dy = y - self.center[1]
                self.circle = Circle(self.center[0], self.center[1], int((dx**2 + dy**2)**0.5))

    def select(self) -> Optional[Circle]:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, min(self.w * 2, 800), min(self.h * 2, 800))
        cv2.setMouseCallback(WINDOW_NAME, self._on_mouse)

        print("\nDefine minimap circle:")
        print("  Click center, then edge | +/-: radius | R: reset | Enter: confirm | Esc: cancel")

        while True:
            cv2.imshow(WINDOW_NAME, self._draw())
            key = cv2.waitKey(30) & 0xFF

            if key == 13 and self.circle:
                r = self.circle.radius + self.radius_offset
                if r > 10:
                    cv2.destroyWindow(WINDOW_NAME)
                    return Circle(self.circle.center_x, self.circle.center_y, r)
                print("  Circle too small")
            elif key == 27:
                cv2.destroyWindow(WINDOW_NAME)
                return None
            elif key == ord("r"):
                self.center = None
                self.circle = None
                self.radius_offset = 0
                print("  Reset")
            elif key in (ord("+"), ord("=")):
                self.radius_offset += 2
            elif key == ord("-"):
                self.radius_offset -= 2
        return None


def seek_frame(video_path: Path) -> Optional[tuple[np.ndarray, float]]:
    """Let user find a frame with HUD using trackbar."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"Cannot open: {video_path}")
        return None

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    dur = total / fps if fps > 0 else 0

    pos = [0]
    img = [None]

    def read():
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos[0])
        ret, f = cap.read()
        if ret:
            img[0] = f

    def on_track(p):
        pos[0] = p

    win = "Seek"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
    cv2.createTrackbar("Frame", win, 0, total - 1, on_track)

    read()

    print(f"\n{dur:.0f}s, {fps:.0f}fps, {total} frames")
    print("Drag slider to find HUD frame. Enter=ok, Esc=cancel")

    last_pos = pos[0]
    while True:
        # Check if trackbar moved
        tp = cv2.getTrackbarPos("Frame", win)
        if tp != last_pos:
            pos[0] = tp
            read()
            last_pos = tp

        if img[0] is not None:
            disp = cv2.resize(img[0], (960, 540))
            ts = pos[0] / fps
            cv2.putText(disp, f"{pos[0]} | {ts:.1f}s", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow(win, disp)

        key = cv2.waitKey(30) & 0xFF
        if key == 13:
            cv2.destroyWindow(win)
            cap.release()
            return img[0], pos[0] / fps
        elif key == 27:
            cv2.destroyWindow(win)
            cap.release()
            return None

    cap.release()
    return None


def calibrate_video(video_path: Path) -> Optional[dict]:
    """Full calibration workflow: seek frame, draw title box, draw minimap box, draw circle.

    Returns a profile dict with title_region, minimap_region and minimap_circle, or None if cancelled.
    """
    result = seek_frame(video_path)
    if result is None:
        return None

    frame, timestamp = result
    h, w = frame.shape[:2]
    print(f"\nFrame at {timestamp:.1f}s ({w}x{h})")

    title_roi = ROICreator(frame, "Title/Caption Region")
    title = title_roi.select()
    if title is None:
        print("Calibration cancelled")
        return None

    print(f"  Title region: ({title.x},{title.y}) {title.width}x{title.height}")

    minimap_roi = ROICreator(frame, "Minimap Region")
    minimap = minimap_roi.select()
    if minimap is None:
        print("Calibration cancelled")
        return None

    print(f"  Minimap region: ({minimap.x},{minimap.y}) {minimap.width}x{minimap.height}")

    minimap_crop = frame[minimap.y:minimap.y + minimap.height, minimap.x:minimap.x + minimap.width]

    circle_creator = CircleCreator(minimap_crop)
    circle = circle_creator.select()
    if circle is None:
        print("Calibration cancelled")
        return None

    print(f"  Minimap circle: center=({circle.center_x},{circle.center_y}) radius={circle.radius}")

    return {
        "video_resolution": [w, h],
        "title_region": title.to_dict(),
        "title_region_ratio": title.to_ratio(w, h),
        "minimap_region": minimap.to_dict(),
        "minimap_region_ratio": minimap.to_ratio(w, h),
        "minimap_circle": circle.to_dict(),
    }
