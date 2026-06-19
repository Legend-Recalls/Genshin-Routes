"""Centralized constants for the Route Explorer codebase."""

# --- AKAZE / Feature Matching ---
AKAZE_DISTANCE_THRESHOLD = 80
TOP_K_CANDIDATES = 20
TOP_K_COARSE = 20
TOP_K_OUTPUT_JSON = 5
MIN_MATCHES_FOR_HOMOGRAPHY = 6
RANSAC_REPROJECTION_THRESHOLD = 5.0
MIN_HOMOGRAPHY_INLIERS = 5
OFF_PATCH_INLIER_PENALTY = 0.5
DEBUG_DRAW_MATCHES_LIMIT = 40
MAX_WORKERS_PRECOMPUTE = 4

# --- Localization ---
CONFIDENCE_THRESHOLD = 0.12
MIN_EXPECTED_MATCHES = 40.0
LOST_FRAMES_BEFORE_GLOBAL = 6
LOST_FRAMES_BEFORE_EXPANDING = 5
TELEPORT_DISTANCE_PX = 1500
CACHE_CAPACITY = 50

# --- Multi-scale ---
DEFAULT_SCALES = (0.9, 1.0, 1.1)

# --- Viterbi Optimizer ---
LOST_EMISSION_COST = 2.0
LOST_TRANSITION_PENALTY = 1.0
MAX_SPEED_TILES_PER_SEC = 1.5
TRANSITION_SPEED_MULTIPLIER = 0.2
TELEPORT_TRANSITION_COST = 0.5
OVER_SPEED_BASE_PENALTY = 20.0
OVER_SPEED_VELOCITY_MULTIPLIER = 5.0

# --- OCR ---
OCR_DOWNSCALE_FACTOR = 0.5
INVALID_PUZZLE_NUMBER = -1

# --- Tile ---
DEFAULT_TILE_SIZE = 256

# --- Extraction / Verification ---
DEFAULT_VERIFICATION_FRAMES = 8
DEFAULT_VERIFICATION_COLS = 4
THUMB_WIDTH = 320
THUMB_HEIGHT = 180
SHEET_PADDING = 5
LABEL_HEIGHT = 25
SHEET_BG_COLOR = (40, 40, 40)
JPEG_QUALITY = 90
VERIFY_WINDOW_SIZE = (1280, 720)
DEFAULT_EXTRACTION_FPS = 1

# --- Filmstrip ---
FILMSTRIP_INTERVAL_SECONDS = 30
FILMSTRIP_THUMB_SIZE = 128
FILMSTRIP_PADDING = 10
FILMSTRIP_LABEL_HEIGHT = 30
FILMSTRIP_EXTRA_WIDTH = 200
FILMSTRIP_BG_COLOR = (30, 30, 30)
FILMSTRIP_CIRCLE_THICKNESS = 2
FILMSTRIP_FONT_SCALE = 0.7

# --- HTTP Cache ---
HTTP_CACHE_MAX_AGE_TILES = 604800  # 7 days
HTTP_CACHE_MAX_AGE_MEDIA = 86400  # 1 day
DEFAULT_SERVER_PORT = 9090

# --- Circular Mask ---
CIRCULAR_MASK_RADIUS_SCALE = 0.90

# --- Optical Flow / Motion Model ---
# DIS optical flow preset: 0=ultrafast, 1=fast, 2=medium.
DIS_FLOW_PRESET = 1
# Min median flow magnitude (px on the minimap) below which we treat the
# frame pair as "no motion" and skip emission.
FLOW_MIN_MAGNITUDE_PX = 0.5
# If the per-frame median flow magnitude exceeds this, assume a scene cut /
# teleport and emit flow=None (so the motion model resets).
FLOW_TELEPORT_MAGNITUDE_PX = 60.0
# Downscale factor applied to the minimap crop before dense flow, for speed.
FLOW_DOWNSCALE = 0.5

# --- Path Fusion ---
# AKAZE confidence at/above which a frame is a reliable absolute anchor.
FUSION_ANCHOR_CONFIDENCE = 0.20
# Minimap-px -> world-px scale. The minimap crop (~524px) shows ~2 fine tiles
# (fine tile = 256px at zoom 15); refined empirically during calibration.
FUSION_MINIMAP_TO_WORLD_SCALE = 1.0
# Direction: world moves OPPOSITE to minimap-content flow (player fixed at
# center; when player moves right, map scrolls left). Calibrated via
# DIS optical flow on test_clip: median scale=1.9 map-px per flow-px.
FUSION_FLOW_SCALE_X = -1.9
FUSION_FLOW_SCALE_Y = -1.9
# Max dead-reckoning distance (tiles) before falling back to interpolation.
FUSION_MAX_DEADRECKON_TILES = 8.0

# --- Benchmark ---
CONFIDENCE_HISTOGRAM_BINS = 10
HISTOGRAM_BIN_SCALE = 10.0
