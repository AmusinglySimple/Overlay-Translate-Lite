import os
import sys
import platform
import json
from utils.logging_config import setup_logger

# --- Project Root ---
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Support Folder (Standards-Compliant Location) ---
SUPPORT_FOLDER_NAME = "Support"
COMPANY_NAME = "YourOrganization"
APP_NAME = "OverlayTranslateLite"

try:
    if platform.system() == "Windows":
        app_data_path = os.getenv('LOCALAPPDATA', os.getenv('APPDATA', os.path.expanduser("~")))
        _support_folder_path = os.path.join(app_data_path, COMPANY_NAME, APP_NAME)
    elif platform.system() == "Darwin":
        _support_folder_path = os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_NAME)
    else:
        _support_folder_path = os.path.join(os.path.expanduser("~"), ".config", APP_NAME)
    
    os.makedirs(_support_folder_path, exist_ok=True)
    
    test_file = os.path.join(_support_folder_path, '.permission_test')
    with open(test_file, 'w') as f:
        f.write('ok')
    os.remove(test_file)
    
    SUPPORT_FOLDER = _support_folder_path
    if sys.stdout:
        print(f"INFO: Using standard application data folder: {SUPPORT_FOLDER}")

except Exception as e:
    if sys.stdout:
        print(f"WARNING: Could not create standard data folder ({e}). Using application directory.")
    _support_folder_path = os.path.join(PROJECT_ROOT, SUPPORT_FOLDER_NAME)
    try:
        os.makedirs(_support_folder_path, exist_ok=True)
        SUPPORT_FOLDER = _support_folder_path
    except Exception as e2:
        if sys.stdout:
            print(f"CRITICAL: Could not create any support folder ({e2}).")
        SUPPORT_FOLDER = PROJECT_ROOT

# --- Configuration File ---
CONFIG_FILE = os.path.join(PROJECT_ROOT, "window_positions.json")

# --- Log File Path ---
LOG_FILE_PATH = os.path.join(SUPPORT_FOLDER, 'overlay_translate_lite.log')

# --- Minimum Opacity ---
MIN_OPACITY = 0.1

# ===================================================================
# APPLICATION CONSTANTS — Lite Version
# ===================================================================

# Helper to read values from config.ini
def get_config(key, fallback):
    """Simple config reader for config.ini [App] section."""
    import configparser
    try:
        _ini = configparser.ConfigParser()
        _ini.read(os.path.join(PROJECT_ROOT, "config.ini"))
        return _ini.get("App", key, fallback=str(fallback))
    except Exception:
        return str(fallback)

# --- Network & Server Constants ---
FLASK_SERVER_PORT = int(get_config('flask_port', 5000))
FLASK_SERVER_HOST = "127.0.0.1"
FLASK_REQUEST_TIMEOUT = 30
FLASK_RETRY_INITIAL_DELAY = 1.0

# --- OCR Constants ---
OCR_RETRY_INITIAL_DELAY = 2.0
IMAGE_PREPROCESS_RETRY_DELAY = 0.5

# --- Image Optimization Constants ---
IMAGE_OPTIMIZATION_ENABLED = True
IMAGE_MAX_DIMENSION = 1920
IMAGE_PNG_COMPRESSION = 6
IMAGE_SCALE_FACTOR = 0.75

# --- Translation Input Constants ---
DEFAULT_MAX_INPUT_CHARS = 5000

# --- UI Constants ---
DEFAULT_FONT_SIZE = 20
MIN_FONT_SIZE = 10
MAX_FONT_SIZE = 36
PREVIEW_FONT_SIZE = 16
FONT_SIZE_STEP = 2

# Dialog Layout Constants
DIALOG_MARGIN = 25
DIALOG_SPACING = 15
DIALOG_MIN_WIDTH = 450
DIALOG_MIN_HEIGHT = 500
DIALOG_ICON_SIZE = 20

# UI Timing Constants
CAPTURE_HIDE_DELAY = 0.08
WORKER_CANCEL_TIMEOUT = 1000

# --- Thread & Worker Constants ---
WORKER_STOP_TIMEOUT = 1500

# --- Live Translation Performance Configuration ---
LIVE_TRANSLATION_DEFAULT_INTERVAL = int(get_config('live_translation_interval', 3000))
LIVE_TRANSLATION_MIN_INTERVAL = int(get_config('live_translation_min_interval', 1000))
LIVE_TRANSLATION_MAX_INTERVAL = int(get_config('live_translation_max_interval', 10000))

# Image change detection thresholds
IMAGE_CHANGE_THRESHOLD_AGGRESSIVE = 0.02
IMAGE_CHANGE_THRESHOLD_BALANCED = 0.05
IMAGE_CHANGE_THRESHOLD_QUALITY = 0.01

# Performance mode settings
PERFORMANCE_MODE_AGGRESSIVE = 'aggressive'
PERFORMANCE_MODE_BALANCED = 'balanced'
PERFORMANCE_MODE_QUALITY = 'quality'

# --- Server Health Check Constants ---
SERVER_READY_CHECK_TIMEOUT = 12.0
SERVER_READY_CHECK_INTERVAL = 0.5
SERVER_READY_REQUEST_TIMEOUT = 1.5

# ===================================================================

# --- Logging Setup ---
logger = setup_logger(
    logger_name="OverlayTranslateLite",
    log_file_path=LOG_FILE_PATH,
    console_level=20,
    file_level=10,
    enable_console=True,
    enable_file=True
)

logger.info("=" * 60)
logger.info("Logger Initialized - OverlayTranslate Lite")
logger.info(f"Project Root: {PROJECT_ROOT}")
logger.info(f"Support Folder: {SUPPORT_FOLDER}")
logger.info(f"Log File: {LOG_FILE_PATH}")
logger.info("=" * 60)


# --- Predefined Themes ---

DEFAULT_THEME = {
    "name": "Default Neon",
    "colors": {
        "bg_main":          "#C8141414", "bg_groupbox":      "#961E1E1E",
        "bg_titlebar":      "#C8282828", "bg_input":         "#961E1E1E",
        "bg_tooltip":       "#F032323C", "bg_menu":          "#C8141414",
        "bg_menu_item_sel": "#FF4A90E2", "text_light":       "#FFE0E0E0",
        "text_accent":      "#FF00FFCC", "text_secondary":   "#FF4A90E2",
        "text_button":      "#FFFFFFFF", "text_disabled":    "#64FFFFFF",
        "text_tooltip":     "#FFF0F0F0", "border_main":      "#00000000",
        "border_accent":    "#FF00FFCC", "border_medium":    "#32FFFFFF",
        "border_light":     "#14FFFFFF", "border_menu":      "#14FFFFFF",
        "grad_button_start":    "#FF4A90E2", "grad_button_end":      "#FF00FFCC",
        "grad_button_hover_start":"#FF5AA1F2", "grad_button_hover_end":"#FF00FFDD",
        "grad_button_pressed":  "#FF357ABD", "grad_slider_start":    "#FF4A90E2",
        "grad_slider_end":      "#FF00FFCC", "progress_chunk_start": "#FF4A90E2",
        "progress_chunk_end":   "#FF00FFCC", "checkbox_checked":     "#FF00FFCC",
    }
}

THEME_DARK_CYBER = {
    "name": "Dark Cyber",
    "colors": {
        "bg_main": "#E6050818", "bg_groupbox": "#A00A0F2A", "bg_titlebar": "#CC101535",
        "bg_input": "#A00A0F2A", "bg_tooltip": "#F01A2040", "bg_menu": "#E6050818",
        "bg_menu_item_sel": "#FF8A2BE2", "text_light": "#FFC0C0FF", "text_accent": "#FFDA70D6",
        "text_secondary": "#FF8A2BE2", "text_button": "#FFFFFFFF", "text_disabled": "#64A0A0B0",
        "text_tooltip": "#FFD0D0FF", "border_main": "#00000000", "border_accent": "#FFDA70D6",
        "border_medium": "#408A2BE2", "border_light": "#208A2BE2", "border_menu": "#208A2BE2",
        "grad_button_start": "#FF8A2BE2", "grad_button_end": "#FFDA70D6",
        "grad_button_hover_start": "#FF9932CC", "grad_button_hover_end": "#FFFF00FF",
        "grad_button_pressed": "#FF4B0082", "grad_slider_start": "#FF8A2BE2",
        "grad_slider_end": "#FFDA70D6", "progress_chunk_start": "#FF8A2BE2",
        "progress_chunk_end": "#FFDA70D6", "checkbox_checked": "#FFDA70D6",
    }
}

THEME_STANDARD_DARK = {
    "name": "Standard Dark",
    "colors": {
        "bg_main": "#E0282828", "bg_groupbox": "#A0303030", "bg_titlebar": "#C83A3A3A",
        "bg_input": "#A0202020", "bg_tooltip": "#F51A1A1A", "bg_menu": "#E0282828",
        "bg_menu_item_sel": "#FF3A70A3", "text_light": "#FFE0E0E0", "text_accent": "#FF5CACEE",
        "text_secondary": "#FF4A90E2", "text_button": "#FFFFFFFF", "text_disabled": "#64A0A0A0",
        "text_tooltip": "#FFE0E0E0", "border_main": "#00000000", "border_accent": "#FF5CACEE",
        "border_medium": "#40606060", "border_light": "#20808080", "border_menu": "#30808080",
        "grad_button_start": "#FF4A90E2", "grad_button_end": "#FF3A70A3",
        "grad_button_hover_start": "#FF5AA1F2", "grad_button_hover_end": "#FF4A80B3",
        "grad_button_pressed": "#FF2A5A8A", "grad_slider_start": "#FF5CACEE",
        "grad_slider_end": "#FF4A90E2", "progress_chunk_start": "#FF5CACEE",
        "progress_chunk_end": "#FF4A90E2", "checkbox_checked": "#FF5CACEE",
    }
}

THEME_STANDARD_LIGHT = {
    "name": "Standard Light",
    "colors": {
        "bg_main": "#E0F0F0F0", "bg_groupbox": "#D0E8E8E8", "bg_titlebar": "#C8D0D0D0",
        "bg_input": "#FEFFFFFF", "bg_tooltip": "#F5FFFFE1", "bg_menu": "#E0F0F0F0",
        "bg_menu_item_sel": "#FF007ACC", "text_light": "#FF1A1A1A", "text_accent": "#FF0059B3",
        "text_secondary": "#FF007ACC", "text_button": "#FFFFFFFF", "text_disabled": "#FFA0A0A0",
        "text_tooltip": "#FF1A1A1A", "border_main": "#00000000", "border_accent": "#FF007ACC",
        "border_medium": "#40808080", "border_light": "#20A0A0A0", "border_menu": "#30A0A0A0",
        "grad_button_start": "#FF007ACC", "grad_button_end": "#FF0059B3",
        "grad_button_hover_start": "#FF008AE6", "grad_button_hover_end": "#FF006CD9",
        "grad_button_pressed": "#FF004C99", "grad_slider_start": "#FF007ACC",
        "grad_slider_end": "#FF0059B3", "progress_chunk_start": "#FF007ACC",
        "progress_chunk_end": "#FF0059B3", "checkbox_checked": "#FF007ACC",
    }
}

THEME_OCEAN_DEPTH = {
    "name": "Ocean Depth",
    "colors": {
        "bg_main": "#E0051F30", "bg_groupbox": "#A00A2F40", "bg_titlebar": "#C8103F50",
        "bg_input": "#A00A2F40", "bg_tooltip": "#F0001A2A", "bg_menu": "#E0051F30",
        "bg_menu_item_sel": "#FF20B2AA", "text_light": "#FFD0F0FF", "text_accent": "#FF40E0D0",
        "text_secondary": "#FF5FC5B8", "text_button": "#FFEEFCFA", "text_disabled": "#6480A0B0",
        "text_tooltip": "#FFD0F0FF", "border_main": "#00000000", "border_accent": "#FF40E0D0",
        "border_medium": "#4020B2AA", "border_light": "#204682B4", "border_menu": "#204682B4",
        "grad_button_start": "#FF168070", "grad_button_end": "#FF1B9C90",
        "grad_button_hover_start": "#FF20A090", "grad_button_hover_end": "#FF28B8A8",
        "grad_button_pressed": "#FF0D5F55", "grad_slider_start": "#FF20B2AA",
        "grad_slider_end": "#FF40E0D0", "progress_chunk_start": "#FF20B2AA",
        "progress_chunk_end": "#FF40E0D0", "checkbox_checked": "#FF40E0D0",
    }
}

PREDEFINED_THEMES = {
    DEFAULT_THEME["name"]: DEFAULT_THEME,
    THEME_DARK_CYBER["name"]: THEME_DARK_CYBER,
    THEME_STANDARD_DARK["name"]: THEME_STANDARD_DARK,
    THEME_STANDARD_LIGHT["name"]: THEME_STANDARD_LIGHT,
    THEME_OCEAN_DEPTH["name"]: THEME_OCEAN_DEPTH,
}

# --- Current Theme Management ---
_current_theme_data = json.loads(json.dumps(DEFAULT_THEME))

def get_current_theme():
    global _current_theme_data
    return _current_theme_data

def update_current_theme(new_theme_data):
    global _current_theme_data
    if isinstance(new_theme_data, dict) and "colors" in new_theme_data and "name" in new_theme_data:
        _current_theme_data = json.loads(json.dumps(new_theme_data))
    else:
        logger.error("Attempted to update theme with invalid data structure.")

# --- ensure_support_folder ---
def ensure_support_folder():
    try:
        if not os.path.exists(SUPPORT_FOLDER):
            os.makedirs(SUPPORT_FOLDER)
    except Exception as e:
        logger.error(f"Failed to ensure support folder exists at {SUPPORT_FOLDER}: {e}")
