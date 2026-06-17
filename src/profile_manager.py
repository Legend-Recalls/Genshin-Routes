import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

PROFILES_DIR = PROJECT_ROOT / "profiles"


def _ensure_dir() -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def list_profiles() -> list[str]:
    _ensure_dir()
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def get_profile_path(name: str) -> Path:
    return PROFILES_DIR / f"{name}.json"


def load_profile(name: str) -> Optional[dict]:
    path = get_profile_path(name)
    if not path.exists():
        logger.warning("Profile not found: %s", name)
        return None

    with open(path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    logger.info("Loaded profile: %s", name)
    return profile


def save_profile(name: str, profile: dict) -> Path:
    _ensure_dir()

    profile["profile_name"] = name
    if "created" not in profile:
        profile["created"] = date.today().isoformat()

    path = get_profile_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    logger.info("Saved profile: %s -> %s", name, path)
    print(f"Profile saved: {path}")
    return path


def delete_profile(name: str) -> bool:
    path = get_profile_path(name)
    if path.exists():
        path.unlink()
        logger.info("Deleted profile: %s", name)
        return True
    return False


def get_default_profile() -> dict:
    from config import TITLE_CROP, MINIMAP_CROP

    return {
        "profile_name": "default",
        "title_region": {
            "x": 0,
            "y": 0,
            "width": 0,
            "height": 0,
        },
        "title_region_ratio": {
            "x": TITLE_CROP["x_start_ratio"],
            "y": TITLE_CROP["y_start_ratio"],
            "width": TITLE_CROP["x_end_ratio"] - TITLE_CROP["x_start_ratio"],
            "height": TITLE_CROP["y_end_ratio"] - TITLE_CROP["y_start_ratio"],
        },
        "minimap_region": {
            "x": 0,
            "y": 0,
            "width": 0,
            "height": 0,
        },
        "minimap_region_ratio": {
            "x": MINIMAP_CROP["x_start_ratio"],
            "y": MINIMAP_CROP["y_start_ratio"],
            "width": MINIMAP_CROP["x_end_ratio"] - MINIMAP_CROP["x_start_ratio"],
            "height": MINIMAP_CROP["y_end_ratio"] - MINIMAP_CROP["y_start_ratio"],
        },
        "minimap_circle": {
            "center_x": 0,
            "center_y": 0,
            "radius": 0,
        },
    }


def pick_profile() -> Optional[dict]:
    profiles = list_profiles()

    if not profiles:
        print("\nNo calibration profiles found.")
        print("Would you like to:")
        print("  1) Create Profile")
        print("  2) Use Default Config")
        choice = input("\nChoice (1 or 2): ").strip()

        if choice == "1":
            return None
        else:
            return get_default_profile()

    print("\nAvailable calibration profiles:")
    for i, name in enumerate(profiles, 1):
        print(f"  {i}) {name}")
    print(f"  {len(profiles) + 1}) Use Default Config")

    choice = input(f"\nChoice (1-{len(profiles) + 1}): ").strip()

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(profiles):
            return load_profile(profiles[idx])
        elif idx == len(profiles):
            return get_default_profile()
    except (ValueError, IndexError):
        pass

    print("Invalid choice, using default config")
    return get_default_profile()
