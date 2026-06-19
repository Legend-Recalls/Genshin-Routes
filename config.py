"""Route Explorer configuration - extends parent project config."""
from pathlib import Path
import importlib.util
import sys

REPO_ROOT = Path(__file__).parent
PROJECT_ROOT = Path(__file__).parent

# Load parent config if it exists (monorepo layout)
_parent_config_path = REPO_ROOT.parent / "config.py"
if _parent_config_path.exists():
    _spec = importlib.util.spec_from_file_location("parent_config", str(_parent_config_path))
    _parent_config = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_parent_config)
    for attr in dir(_parent_config):
        if not attr.startswith("_") and attr not in ("OUTPUT_DIR", "DATA_DIR", "PROJECT_ROOT"):
            globals()[attr] = getattr(_parent_config, attr)

# Ensure parent src is importable (append so local src/ takes priority)
sys.path.append(str(REPO_ROOT))

# Route Explorer paths
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT / "data"
MAPS_DIR = PROJECT_ROOT / "maps"
VIDEOS_DIR = PROJECT_ROOT / "videos"

# Constants that may not be in parent config
if "OCR_CONFIDENCE_THRESHOLD" not in globals():
    OCR_CONFIDENCE_THRESHOLD = 0.6

if "TITLE_CROP" not in globals():
    TITLE_CROP = {
        "x_start_ratio": 0.55,
        "x_end_ratio": 0.95,
        "y_start_ratio": 0.07,
        "y_end_ratio": 0.17,
    }

if "MINIMAP_CROP" not in globals():
    MINIMAP_CROP = {
        "x_start_ratio": 0.0,
        "x_end_ratio": 0.18,
        "y_start_ratio": 0.0,
        "y_end_ratio": 0.25,
    }
