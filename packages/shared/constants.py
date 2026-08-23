"""
FaceSentry Shared Constants
"""

import os
import sys

VERSION = "1.0.0"
SYSTEM_NAME = "FaceSentry"

# Default Network Settings
DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8000
DEFAULT_WEB_PORT = 3000

# Default Policy Timeouts (Seconds)
DEFAULT_ABSENCE_TIMEOUT_SECONDS = 10
DEFAULT_UNKNOWN_FACE_TIMEOUT_SECONDS = 5
DEFAULT_SPOOF_LOCK_TIMEOUT_SECONDS = 0
DEFAULT_GRACE_PERIOD_SECONDS = 3
DEFAULT_SNOOZE_MAX_MINUTES = 60

# Default Detection & Matching Thresholds
DEFAULT_SIMILARITY_THRESHOLD = 0.65
DEFAULT_LIVENESS_THRESHOLD = 0.75
DEFAULT_EAR_BLINK_THRESHOLD = 0.20
DEFAULT_MIN_FACE_SIZE = 80

# Hardware & Frame Rates
DEFAULT_CAMERA_INDEX = 0
DEFAULT_TARGET_FPS = 15
DEFAULT_FRAME_WIDTH = 640
DEFAULT_FRAME_HEIGHT = 480

# Security Defaults
DEFAULT_MAX_PIN_ATTEMPTS = 5
DEFAULT_PIN_LOCKOUT_SECONDS = 300
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST_KB = 65536
ARGON2_PARALLELISM = 4

# Path Resolution Logic
def get_base_dir() -> str:
    """
    Returns the appropriate base directory for FaceSentry data.
    If FACESENTRY_DEV_MODE=1, returns the local ./data directory.
    Otherwise, returns %LOCALAPPDATA%/FaceSentry.
    """
    if os.environ.get("FACESENTRY_DEV_MODE", "0") == "1":
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        # Fallback if LOCALAPPDATA isn't set for some reason
        local_app_data = os.path.expanduser("~\\AppData\\Local")
    
    return os.path.join(local_app_data, "FaceSentry")

BASE_DATA_DIR = get_base_dir()

# Local Paths
DEFAULT_DATABASE_PATH = os.path.join(BASE_DATA_DIR, "facesentry.db")
DEFAULT_MODELS_DIR = os.path.join(BASE_DATA_DIR, "models")
DEFAULT_ENROLLMENT_DIR = os.path.join(BASE_DATA_DIR, "enrollment")
DEFAULT_LOGS_DIR = os.path.join(BASE_DATA_DIR, "logs")
