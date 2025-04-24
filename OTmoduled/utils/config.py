# utils/config.py
import os
import logging
import logging.handlers
import sys
import platform
import json

# --- Project Root ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Support Folder ---
SUPPORT_FOLDER_NAME = "Support"
_support_folder_path = os.path.join(os.path.expanduser("~"), "Desktop", SUPPORT_FOLDER_NAME)
try:
    if not os.path.exists(_support_folder_path): os.makedirs(_support_folder_path)
except OSError: # Simplified fallback
    _support_folder_path = os.path.join(PROJECT_ROOT, SUPPORT_FOLDER_NAME)
    try:
        if not os.path.exists(_support_folder_path): os.makedirs(_support_folder_path)
    except OSError: _support_folder_path = PROJECT_ROOT
SUPPORT_FOLDER = _support_folder_path

# --- Configuration File ---
CONFIG_FILE = os.path.join(PROJECT_ROOT, "window_positions.json")

# --- Log File Path ---
LOG_FILE_PATH = os.path.join(SUPPORT_FOLDER, 'overlay_translate.log')

# --- Minimum Opacity ---
MIN_OPACITY = 0.1

# --- Logging Setup ---
# Keep the existing logging setup - no changes needed here
# ... (logger setup code remains the same) ...
logger = logging.getLogger("OverlayTranslate") # Use the named logger
logger.setLevel(logging.DEBUG)
# Clear existing handlers if any (e.g., during reload/multiple init calls)
for handler in logger.handlers[:]:
    try: handler.close(); logger.removeHandler(handler)
    except Exception as e: print(f"Error removing logging handler: {e}")
# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)
# File handler
try:
    file_handler = logging.handlers.RotatingFileHandler(LOG_FILE_PATH, maxBytes=2*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
except Exception as e: print(f"Error setting up file logging to '{LOG_FILE_PATH}': {e}")
logger.info(f"--- Logger Initialized ---")
logger.info(f"Project Root: {PROJECT_ROOT}")
logger.info(f"Support Folder: {SUPPORT_FOLDER}")
logger.info(f"Log File: {LOG_FILE_PATH}")
logger.info(f"Config File: {CONFIG_FILE}")
# --- End Logging Setup ---


# --- Predefined Themes ---

DEFAULT_THEME = { # Keep this as the fallback
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
        "bg_main":          "#E6050818",  # Very dark blue-purple, semi-transparent
        "bg_groupbox":      "#A00A0F2A",  # Darker blue-purple groupbox
        "bg_titlebar":      "#CC101535",  # Slightly lighter title
        "bg_input":         "#A00A0F2A",  # Same as groupbox
        "bg_tooltip":       "#F01A2040",  # Darker tooltip
        "bg_menu":          "#E6050818",  # Main background for menu
        "bg_menu_item_sel": "#FF8A2BE2",  # BlueViolet selection
        "text_light":       "#FFC0C0FF",  # Light purple-ish text
        "text_accent":      "#FFDA70D6",  # Orchid accent
        "text_secondary":   "#FF8A2BE2",  # BlueViolet secondary
        "text_button":      "#FFFFFFFF",
        "text_disabled":    "#64A0A0B0",  # Muted grey-purple
        "text_tooltip":     "#FFD0D0FF",
        "border_main":      "#00000000",
        "border_accent":    "#FFDA70D6",  # Orchid border
        "border_medium":    "#408A2BE2",  # Transparent BlueViolet
        "border_light":     "#208A2BE2",
        "border_menu":      "#208A2BE2",
        "grad_button_start":    "#FF8A2BE2",  # BlueViolet
        "grad_button_end":      "#FFDA70D6",  # Orchid
        "grad_button_hover_start":"#FF9932CC",  # DarkOrchid
        "grad_button_hover_end":"#FFFF00FF",  # Magenta
        "grad_button_pressed":  "#FF4B0082",  # Indigo
        "grad_slider_start":    "#FF8A2BE2",
        "grad_slider_end":      "#FFDA70D6",
        "progress_chunk_start": "#FF8A2BE2",
        "progress_chunk_end":   "#FFDA70D6",
        "checkbox_checked":     "#FFDA70D6",
    }
}

THEME_LIGHT_SOLAR = {
    "name": "Light Solar",
    "colors": {
        "bg_main":          "#E0F5F5DC",  # Very light beige/off-white, mostly opaque
        "bg_groupbox":      "#B0E0E0E0",  # Light grey groupbox
        "bg_titlebar":      "#C8D8D8D0",  # Slightly darker grey title
        "bg_input":         "#CCFFFFFF",  # White input background
        "bg_tooltip":       "#F5F5F5F5",  # Opaque light grey tooltip
        "bg_menu":          "#E0F5F5DC",  # Main background for menu
        "bg_menu_item_sel": "#FFFF8C00",  # DarkOrange selection
        "text_light":       "#FF2F4F4F",  # DarkSlateGray primary text
        "text_accent":      "#FFFF4500",  # OrangeRed accent
        "text_secondary":   "#FFDC143C",  # Crimson secondary
        "text_button":      "#FF2F4F4F",  # Dark text on light buttons
        "text_disabled":    "#FFA0A0A0",  # Grey disabled text
        "text_tooltip":     "#FF1E1E1E",  # Very dark tooltip text
        "border_main":      "#00000000",
        "border_accent":    "#FFFF4500",  # OrangeRed border
        "border_medium":    "#40A9A9A9",  # Transparent DarkGray
        "border_light":     "#20C0C0C0",  # Transparent Silver
        "border_menu":      "#20C0C0C0",
        "grad_button_start":    "#FFFFD700",  # Gold
        "grad_button_end":      "#FFFF8C00",  # DarkOrange
        "grad_button_hover_start":"#FFFFE440",  # Lighter Gold
        "grad_button_hover_end":"#FFFFA500",  # Orange
        "grad_button_pressed":  "#FFCD853F",  # Peru
        "grad_slider_start":    "#FFFFD700",
        "grad_slider_end":      "#FFFF8C00",
        "progress_chunk_start": "#FFFFD700",
        "progress_chunk_end":   "#FFFF8C00",
        "checkbox_checked":     "#FFFF4500",
    }
}

# --- NEW THEMES START ---

THEME_OCEAN_DEPTH = {
    "name": "Ocean Depth",
    "colors": {
        "bg_main":          "#E0051F30", # Deep blue, semi-transparent
        "bg_groupbox":      "#A00A2F40", # Slightly lighter blue
        "bg_titlebar":      "#C8103F50", # Even lighter blue title
        "bg_input":         "#A00A2F40", # Same as groupbox
        "bg_tooltip":       "#F0001A2A", # Darker tooltip
        "bg_menu":          "#E0051F30", # Main background for menu
        "bg_menu_item_sel": "#FF20B2AA", # LightSeaGreen selection
        "text_light":       "#FFD0F0FF", # Very light blue/cyan text
        "text_accent":      "#FF40E0D0", # Turquoise accent
        "text_secondary":   "#FF20B2AA", # LightSeaGreen secondary
        "text_button":      "#FF002030", # Dark text on light buttons
        "text_disabled":    "#6480A0B0", # Muted grey-blue
        "text_tooltip":     "#FFD0F0FF", # Light tooltip text
        "border_main":      "#00000000",
        "border_accent":    "#FF40E0D0", # Turquoise border
        "border_medium":    "#4020B2AA", # Transparent LightSeaGreen
        "border_light":     "#204682B4", # Transparent SteelBlue
        "border_menu":      "#204682B4",
        "grad_button_start":    "#FF20B2AA", # LightSeaGreen
        "grad_button_end":      "#FF48D1CC", # MediumTurquoise
        "grad_button_hover_start":"#FF30C2BA", # Brighter LightSeaGreen
        "grad_button_hover_end":"#FF58E1DC", # Brighter MediumTurquoise
        "grad_button_pressed":  "#FF008080", # Teal
        "grad_slider_start":    "#FF20B2AA",
        "grad_slider_end":      "#FF40E0D0", # Turquoise
        "progress_chunk_start": "#FF20B2AA",
        "progress_chunk_end":   "#FF40E0D0",
        "checkbox_checked":     "#FF40E0D0",
    }
}

THEME_FOREST_CANOPY = {
    "name": "Forest Canopy",
    "colors": {
        "bg_main":          "#E01A3A1A", # Dark green, semi-transparent
        "bg_groupbox":      "#A02F4F2F", # DarkSlateGreen groupbox
        "bg_titlebar":      "#C83F5F3F", # Darker green title
        "bg_input":         "#A02F4F2F", # Same as groupbox
        "bg_tooltip":       "#F01E4E1E", # Very dark green tooltip
        "bg_menu":          "#E01A3A1A", # Main background for menu
        "bg_menu_item_sel": "#FF8FBC8F", # DarkSeaGreen selection
        "text_light":       "#FFD0FFD0", # Light green text
        "text_accent":      "#FF98FB98", # PaleGreen accent
        "text_secondary":   "#FF8FBC8F", # DarkSeaGreen secondary
        "text_button":      "#FF103010", # Dark text on light buttons
        "text_disabled":    "#6480A080", # Muted grey-green
        "text_tooltip":     "#FFD0FFD0", # Light tooltip text
        "border_main":      "#00000000",
        "border_accent":    "#FF98FB98", # PaleGreen border
        "border_medium":    "#408FBC8F", # Transparent DarkSeaGreen
        "border_light":     "#20556B2F", # Transparent DarkOliveGreen
        "border_menu":      "#20556B2F",
        "grad_button_start":    "#FF8FBC8F", # DarkSeaGreen
        "grad_button_end":      "#FF9ACD32", # YellowGreen
        "grad_button_hover_start":"#FF9FDCAF", # Lighter DarkSeaGreen
        "grad_button_hover_end":"#FFAADF42", # Lighter YellowGreen
        "grad_button_pressed":  "#FF556B2F", # DarkOliveGreen
        "grad_slider_start":    "#FF8FBC8F",
        "grad_slider_end":      "#FF98FB98", # PaleGreen
        "progress_chunk_start": "#FF8FBC8F",
        "progress_chunk_end":   "#FF98FB98",
        "checkbox_checked":     "#FF98FB98",
    }
}

THEME_RETRO_WAVE = {
    "name": "Retro Wave",
    "colors": {
        "bg_main":          "#E61C0C30", # Dark purple-blue background
        "bg_groupbox":      "#A02C1C40", # Darker purple groupbox
        "bg_titlebar":      "#CC3C2C50", # Slightly lighter title
        "bg_input":         "#A02C1C40", # Same as groupbox
        "bg_tooltip":       "#F03C0C50", # Darker purple tooltip
        "bg_menu":          "#E61C0C30", # Main background for menu
        "bg_menu_item_sel": "#FFFF00FF", # Magenta selection
        "text_light":       "#FFFFCCFF", # Light pink text
        "text_accent":      "#FF00FFFF", # Cyan accent
        "text_secondary":   "#FFFF00FF", # Magenta secondary
        "text_button":      "#FFFFFFFF", # White text on vibrant buttons
        "text_disabled":    "#64A080A0", # Muted grey-purple
        "text_tooltip":     "#FFFFEEFF", # Very light pink tooltip text
        "border_main":      "#00000000",
        "border_accent":    "#FF00FFFF", # Cyan border
        "border_medium":    "#40FF00FF", # Transparent Magenta
        "border_light":     "#208A2BE2", # Transparent BlueViolet
        "border_menu":      "#208A2BE2",
        "grad_button_start":    "#FFFF00FF", # Magenta
        "grad_button_end":      "#FFDA70D6", # Orchid
        "grad_button_hover_start":"#FFFF33FF", # Brighter Magenta
        "grad_button_hover_end":"#FFEA80E6", # Lighter Orchid
        "grad_button_pressed":  "#FF8B008B", # DarkMagenta
        "grad_slider_start":    "#FF00FFFF", # Cyan
        "grad_slider_end":      "#FFFF00FF", # Magenta
        "progress_chunk_start": "#FF00FFFF",
        "progress_chunk_end":   "#FFFF00FF",
        "checkbox_checked":     "#FF00FFFF",
    }
}

THEME_STANDARD_LIGHT = {
    "name": "Standard Light",
    "colors": {
        "bg_main":          "#E0F0F0F0", # Light Gray background
        "bg_groupbox":      "#D0E8E8E8", # Slightly darker gray groupbox
        "bg_titlebar":      "#C8D0D0D0", # Gray titlebar
        "bg_input":         "#FEFFFFFF", # White input fields
        "bg_tooltip":       "#F5FFFFE1", # Light yellow tooltip
        "bg_menu":          "#E0F0F0F0", # Light Gray menu
        "bg_menu_item_sel": "#FF007ACC", # Standard blue selection
        "text_light":       "#FF1A1A1A", # Very dark gray text
        "text_accent":      "#FF0059B3", # Darker blue accent
        "text_secondary":   "#FF007ACC", # Standard blue secondary
        "text_button":      "#FFFFFFFF", # White text on buttons
        "text_disabled":    "#FFA0A0A0", # Gray disabled text
        "text_tooltip":     "#FF1A1A1A", # Dark tooltip text
        "border_main":      "#00000000",
        "border_accent":    "#FF007ACC", # Standard blue border
        "border_medium":    "#40808080", # Gray medium border
        "border_light":     "#20A0A0A0", # Lighter gray border
        "border_menu":      "#30A0A0A0",
        "grad_button_start":    "#FF007ACC", # Standard blue
        "grad_button_end":      "#FF0059B3", # Darker blue
        "grad_button_hover_start":"#FF008AE6", # Lighter blue
        "grad_button_hover_end":"#FF006CD9", # Slightly lighter dark blue
        "grad_button_pressed":  "#FF004C99", # Even darker blue
        "grad_slider_start":    "#FF007ACC",
        "grad_slider_end":      "#FF0059B3",
        "progress_chunk_start": "#FF007ACC",
        "progress_chunk_end":   "#FF0059B3",
        "checkbox_checked":     "#FF007ACC",
    }
}

THEME_STANDARD_DARK = {
    "name": "Standard Dark",
    "colors": {
        "bg_main":          "#E0282828", # Dark Gray background
        "bg_groupbox":      "#A0303030", # Slightly lighter gray groupbox
        "bg_titlebar":      "#C83A3A3A", # Medium gray titlebar
        "bg_input":         "#A0202020", # Very dark input fields
        "bg_tooltip":       "#F51A1A1A", # Dark tooltip
        "bg_menu":          "#E0282828", # Dark Gray menu
        "bg_menu_item_sel": "#FF3A70A3", # Medium blue selection
        "text_light":       "#FFE0E0E0", # Light gray text
        "text_accent":      "#FF5CACEE", # Sky blue accent
        "text_secondary":   "#FF4A90E2", # Lighter blue secondary
        "text_button":      "#FFFFFFFF", # White text on buttons
        "text_disabled":    "#64A0A0A0", # Gray disabled text
        "text_tooltip":     "#FFE0E0E0", # Light gray tooltip text
        "border_main":      "#00000000",
        "border_accent":    "#FF5CACEE", # Sky blue border
        "border_medium":    "#40606060", # Medium dark gray border
        "border_light":     "#20808080", # Lighter dark gray border
        "border_menu":      "#30808080",
        "grad_button_start":    "#FF4A90E2", # Lighter blue
        "grad_button_end":      "#FF3A70A3", # Medium blue
        "grad_button_hover_start":"#FF5AA1F2", # Bright lighter blue
        "grad_button_hover_end":"#FF4A80B3", # Bright medium blue
        "grad_button_pressed":  "#FF2A5A8A", # Darker medium blue
        "grad_slider_start":    "#FF5CACEE", # Sky blue
        "grad_slider_end":      "#FF4A90E2", # Lighter blue
        "progress_chunk_start": "#FF5CACEE",
        "progress_chunk_end":   "#FF4A90E2",
        "checkbox_checked":     "#FF5CACEE",
    }
}

# --- END NEW THEME DEFINITIONS ---


# Dictionary to hold all predefined themes by name
# --- MODIFY THIS DICTIONARY to include the new themes ---
PREDEFINED_THEMES = {
    DEFAULT_THEME["name"]: DEFAULT_THEME,
    THEME_DARK_CYBER["name"]: THEME_DARK_CYBER,
    THEME_LIGHT_SOLAR["name"]: THEME_LIGHT_SOLAR,
    THEME_OCEAN_DEPTH["name"]: THEME_OCEAN_DEPTH,
    THEME_FOREST_CANOPY["name"]: THEME_FOREST_CANOPY,
    THEME_RETRO_WAVE["name"]: THEME_RETRO_WAVE,
    THEME_STANDARD_LIGHT["name"]: THEME_STANDARD_LIGHT,  # Added
    THEME_STANDARD_DARK["name"]: THEME_STANDARD_DARK,    # Added
}
# --- AI API Configuration (Keep this) ---
ai_api_config = {"provider": None, "endpoint": None, "key_stored": False}

# --- Current Theme Management (Keep this) ---
# This variable holds the *currently active* theme dictionary in memory
_current_theme_data = json.loads(json.dumps(DEFAULT_THEME)) # Start with default

def get_current_theme():
    """Gets the currently loaded theme data."""
    global _current_theme_data
    # logger.debug(f"[get_current_theme] Returning theme: '{_current_theme_data.get('name', 'N/A')}'")
    return _current_theme_data

def update_current_theme(new_theme_data):
    """Updates the global theme data variable."""
    global _current_theme_data
    if isinstance(new_theme_data, dict) and "colors" in new_theme_data and "name" in new_theme_data:
        # Log the change
        old_name = _current_theme_data.get('name', 'N/A')
        new_name = new_theme_data.get('name')
        # logger.debug(f"[update_current_theme] Updating theme from '{old_name}' to '{new_name}'")
        # Perform a deep copy to ensure independence
        _current_theme_data = json.loads(json.dumps(new_theme_data))
    else:
        logger.error("Attempted to update theme with invalid data structure.")

# --- ensure_support_folder (Keep this) ---
def ensure_support_folder():
    """Ensures the support folder exists."""
    try:
        if not os.path.exists(SUPPORT_FOLDER):
            os.makedirs(SUPPORT_FOLDER)
            logger.info(f"Created Support folder at {SUPPORT_FOLDER}")
    except OSError as e:
        logger.error(f"Failed to create support folder at {SUPPORT_FOLDER}: {e}")