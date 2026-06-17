"""Route Explorer configuration - extends parent project config."""
from pathlib import Path
import importlib.util
import sys

REPO_ROOT = Path(__file__).parent.parent
PROJECT_ROOT = Path(__file__).parent

# Load parent config directly to avoid circular import
_parent_config_path = REPO_ROOT / "config.py"
_spec = importlib.util.spec_from_file_location("parent_config", str(_parent_config_path))
_parent_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_parent_config)

# Copy parent config attributes EXCEPT paths (we define our own)
for attr in dir(_parent_config):
    if not attr.startswith("_") and attr not in ("OUTPUT_DIR", "DATA_DIR", "PROJECT_ROOT"):
        globals()[attr] = getattr(_parent_config, attr)

# Ensure parent src is importable (append so local src/ takes priority)
sys.path.append(str(REPO_ROOT))

# Route Explorer specific paths — these override parent
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT / "data"
