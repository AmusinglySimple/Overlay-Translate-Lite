import os
import re # Ensure this import is at the top of the file
import sys
import time
import datetime # <-- Ensure datetime is imported
import logging
import logging.handlers
import requests
import threading
import subprocess
import webbrowser
import textwrap
import tempfile
import shutil
import json
import gc # Added for explicit garbage collection possibility
import platform
import keyring
import math
from threading import Thread
import zipfile

# Ensure PySide6 is imported correctly
try:
    from PySide6 import QtCore, QtWidgets, QtGui
    from PySide6.QtWidgets import (
        QDialog, QApplication, QVBoxLayout, QLabel, QMainWindow, QPushButton,
        QInputDialog, QSlider, QMessageBox, QProgressBar, QSystemTrayIcon, QMenu,
        QWidget, QHBoxLayout, QTextEdit, QLineEdit, QFileDialog, QGroupBox, QCheckBox,
        QColorDialog, QComboBox, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QButtonGroup # Combined imports
    )
    from PySide6.QtCore import Qt, QPoint, QRect, QTimer, QThread, Signal, QPropertyAnimation, QEasingCurve, QPointF, QEventLoop, QSize
    from PySide6.QtGui import (
        QPixmap, QPainter, QColor, QPen, QBrush, QImage, QLinearGradient, QFontInfo,
        QKeySequence, QShortcut, QFont, QIcon, QFontDatabase, QPolygonF
    )
    # QGraphicsOpacityEffect, QGraphicsDropShadowEffect already imported above
except ImportError:
    print("PySide6 not found. Please install it: pip install PySide6")
    sys.exit(1)

# Ensure other dependencies are imported correctly
try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    from paddleocr import PaddleOCR
    from langdetect import detect
    import cv2
    import numpy as np
except ImportError as e:
    print(f"Missing dependency: {e}. Please install requirements.")
    print("Try: pip install Pillow paddleocr paddlepaddle langdetect-py opencv-python numpy keyring") # Added keyring
    sys.exit(1)


# Import the Flask app from app.py - Ensure app.py is in the same directory or Python path
try:
    # Change this line if your Flask app file is named differently
    from app import app as flask_app
except ImportError:
    print("Error: Could not import 'app' from app.py. Make sure app.py is in the same directory.")
    sys.exit(1)
except Exception as flask_import_err:
    print(f"Error importing Flask app: {flask_import_err}") # Catch other potential import errors
    sys.exit(1)

# --- Constants ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(PROJECT_ROOT, "window_positions.json")
# Use a subfolder within the project for support files for better encapsulation
SUPPORT_FOLDER_NAME = "Support"
# Place support folder on Desktop
SUPPORT_FOLDER = os.path.join(os.path.expanduser("~"), "Desktop", SUPPORT_FOLDER_NAME)

# --- MODIFICATION 1: Log File Location ---
# Ensure support folder exists *before* setting up logging path
try:
    if not os.path.exists(SUPPORT_FOLDER):
        os.makedirs(SUPPORT_FOLDER)
        print(f"Created Support folder at {SUPPORT_FOLDER}") # Use print as logger not set up yet
except OSError as e:
    print(f"CRITICAL: Failed to create support folder at {SUPPORT_FOLDER}: {e}")
    # Fallback to project root if desktop creation fails
    SUPPORT_FOLDER = os.path.join(PROJECT_ROOT, SUPPORT_FOLDER_NAME)
    try:
        if not os.path.exists(SUPPORT_FOLDER):
            os.makedirs(SUPPORT_FOLDER)
            print(f"Created fallback Support folder at {SUPPORT_FOLDER}")
    except OSError as e2:
        print(f"CRITICAL: Failed to create fallback support folder: {e2}. Logs may fail.")
        SUPPORT_FOLDER = PROJECT_ROOT # Last resort


LOG_FILE_PATH = os.path.join(SUPPORT_FOLDER, 'overlay_translate.log') # <-- Use SUPPORT_FOLDER
# --- END MODIFICATION 1 ---

MIN_OPACITY = 0.1 # Minimum opacity level (10%) where widget becomes click-through

# --- Logging Setup ---
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
# Clear existing handlers if any (e.g., during reload)
for handler in logger.handlers[:]:
    try:
        handler.close()
        logger.removeHandler(handler)
    except Exception as e:
        print(f"Error removing logging handler: {e}")


# Console handler
console_handler = logging.StreamHandler(sys.stdout) # Use stdout
console_handler.setLevel(logging.INFO) # Keep console less verbose
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# File handler
try:
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE_PATH, maxBytes=2*1024*1024, backupCount=5, encoding='utf-8' # Use 2MB log files
    )
    file_handler.setLevel(logging.DEBUG) # Log everything to file
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
except Exception as e:
    print(f"Error setting up file logging to '{LOG_FILE_PATH}': {e}") # Print error if logging fails


logging.info(f"Project Root: {PROJECT_ROOT}")
logging.info(f"Support Folder: {SUPPORT_FOLDER}")
logging.info(f"Log File: {LOG_FILE_PATH}")


# --- Constants ---
# ... (other constants) ...

# --- Default Theme Definition ---
DEFAULT_THEME = {
    "name": "Default Neon",
    "colors": {
        # Backgrounds - Example Conversions (Verify alpha values!)
        "bg_main":          "#C8141414",  # rgba(20, 20, 20, 200)
        "bg_groupbox":      "#961E1E1E",  # rgba(30, 30, 30, 150)
        "bg_titlebar":      "#C8282828",  # rgba(40, 40, 40, 200)
        "bg_input":         "#961E1E1E",  # rgba(30, 30, 30, 150)
        "bg_tooltip":       "#F032323C",  # rgba(50, 50, 60, 240)
        "bg_menu":          "#C8141414",  # rgba(20, 20, 20, 200)
        "bg_menu_item_sel": "#FF4A90E2",  # Solid Color

        # Text
        "text_light":       "#FFE0E0E0",
        "text_accent":      "#FF00FFCC",
        "text_secondary":   "#FF4A90E2",
        "text_button":      "#FFFFFFFF",
        "text_disabled":    "#64FFFFFF",  # rgba(255, 255, 255, 100)
        "text_tooltip":     "#FFF0F0F0",

        # Borders
        "border_main":      "#00000000",  # rgba(0, 0, 0, 0) - Fully Transparent
        "border_accent":    "#FF00FFCC",
        "border_medium":    "#32FFFFFF",  # rgba(255, 255, 255, 50)
        "border_light":     "#14FFFFFF",  # rgba(255, 255, 255, 20)
        "border_menu":      "#14FFFFFF",  # rgba(255, 255, 255, 20)

        # Gradients / Specific Elements
        "grad_button_start":    "#FF4A90E2",
        "grad_button_end":      "#FF00FFCC",
        "grad_button_hover_start":"#FF5AA1F2",
        "grad_button_hover_end":"#FF00FFDD",
        "grad_button_pressed":  "#FF357ABD",
        "grad_slider_start":    "#FF4A90E2",
        "grad_slider_end":      "#FF00FFCC",
        "progress_chunk_start": "#FF4A90E2",
        "progress_chunk_end":   "#FF00FFCC",
        "checkbox_checked":     "#FF00FFCC",
    }
}
# current_theme = DEFAULT_THEME.copy() # Already initialized elsewhere


# --- Global Variables & Initial Setup ---
paddle_ocr = None # OCR is initialized later in main block
ai_api_config = {"provider": None, "endpoint": None} # Initialize with None


# --- Helper Functions ---

def get_system_font_path(font_name):
    system = platform.system()
    font_paths = {
        "Windows": {
            "Arial": r"C:\Windows\Fonts\arial.ttf",
            "MSYH": r"C:\Windows\Fonts\msyh.ttc", # Microsoft YaHei (Simplified Chinese)
            "Malgun": r"C:\Windows\Fonts\malgun.ttf", # Malgun Gothic (Korean)
            "MSGothic": r"C:\Windows\Fonts\msgothic.ttc", # MS Gothic (Japanese)
            "Roboto": r"C:\Windows\Fonts\Roboto-Regular.ttf", # Assumes Roboto installed
            "Segoe UI": r"C:\Windows\Fonts\segoeui.ttf", # Common UI font
        },
        "Darwin": { # macOS
            "Arial": "/Library/Fonts/Arial.ttf",
            "MSYH": "/System/Library/Fonts/STHeiti Light.ttc", # Heiti SC/TC often used
            "Malgun": "/System/Library/Fonts/AppleGothic.ttf", # Apple SD Gothic Neo is better if available
            "MSGothic": "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", # Hiragino Kaku Gothic often used
            "Roboto": "/Library/Fonts/Roboto-Regular.ttf", # Assumes installed
            "San Francisco": "/System/Library/Fonts/SFNS.ttf", # Common UI font
        },
        "Linux": {
            "Arial": "/usr/share/fonts/truetype/msttcorefonts/arial.ttf", # If installed
            "MSYH": "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", # WenQuanYi Micro Hei common fallback
            "Malgun": "/usr/share/fonts/truetype/nanum/NanumGothic.ttf", # Nanum often used
            "MSGothic": "/usr/share/fonts/truetype/takao-gothic/TakaoPGothic.ttf", # Takao common fallback
            "Roboto": "/usr/share/fonts/truetype/roboto/Roboto-Regular.ttf", # Common path
            "Noto Sans": "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", # Good coverage
            "DejaVu Sans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", # Common fallback
        }
    }

    default_font_map = {
        "Windows": r"C:\Windows\Fonts\segoeui.ttf", # Use Segoe UI as a more modern default
        "Darwin": "/System/Library/Fonts/SFNS.ttf", # Use SF as default
        "Linux": "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf" # Prefer Noto Sans
    }
    # Fallback default if preferred defaults aren't found
    fallback_default = {
        "Windows": r"C:\Windows\Fonts\arial.ttf",
        "Darwin": "/Library/Fonts/Arial.ttf",
        "Linux": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    }

    default_font = default_font_map.get(system, "arial.ttf") # Start with preferred default
    if not os.path.exists(default_font):
        default_font = fallback_default.get(system, "arial.ttf") # Use fallback if preferred not found


    font_map = font_paths.get(system, {})
    specific_font_path = None

    # Normalize font_name input
    normalized_font_name = font_name.lower().strip()

    # Mapping language codes/common names to font keys in font_paths
    lang_to_font_key = {
        "default": ["Roboto", "Segoe UI", "San Francisco", "Noto Sans", "Arial"], # Preference order for default
        "zh": ["MSYH", "Noto Sans CJK SC"],
        "ja": ["MSGothic", "Noto Sans CJK JP", "MSYH"],
        "ko": ["Malgun", "Noto Sans CJK KR"],
        "zh-cn": ["MSYH", "Noto Sans CJK SC"],
        "zh-tw": ["MSYH", "Noto Sans CJK TC"],
         # Add more language codes if needed
    }


    keys_to_try = []
    if normalized_font_name in lang_to_font_key:
        keys_to_try = lang_to_font_key[normalized_font_name]
    else:
        # Try direct name match first
        for key, path in font_map.items():
             if key.lower() == normalized_font_name:
                 keys_to_try = [key]
                 break
        # If no direct match, treat as default
        if not keys_to_try:
            keys_to_try = lang_to_font_key["default"]

    # Try finding an existing path from the list of keys
    for key in keys_to_try:
        path = font_map.get(key)
        if path and os.path.exists(path):
            specific_font_path = path
            break

    # If no specific font found, use the system default
    if not specific_font_path:
         specific_font_path = default_font


    # Final check if the chosen path exists
    if not specific_font_path or not os.path.exists(specific_font_path):
        logging.warning(f"Font file not found for '{font_name}' at path '{specific_font_path}'. Falling back to absolute default '{default_font}'")
        # Check if default_font exists either
        if not os.path.exists(default_font):
             logging.error(f"System default font '{default_font}' also not found. Font rendering may fail.")
             # As a last resort, return a name hoping the OS finds *something*
             return "Arial" if system == "Windows" else "Sans" # Generic names
        specific_font_path = default_font # Use the validated default font

    logging.debug(f"Using font path for '{font_name}': {specific_font_path}")
    return specific_font_path


def choose_font_for_text(text, default_font_family="Roboto", font_size=24):
    """Chooses a QFont based on detected script in the text."""
    # Prioritize specific scripts
    if any('\u4e00' <= c <= '\u9fff' for c in text):  # CJK Unified Ideographs (Common Chinese)
        return QFont("Microsoft YaHei", font_size) # Good coverage
    elif any('\u3040' <= c <= '\u30ff' for c in text):  # Hiragana and Katakana (Japanese)
        return QFont("MS Gothic", font_size) # Or Meiryo/Yu Gothic on newer Windows
    elif any('\uac00' <= c <= '\ud7af' for c in text):  # Hangul Syllables (Korean)
        return QFont("Malgun Gothic", font_size)
    # Add more script checks if needed (e.g., Cyrillic, Arabic, Thai)
    # elif any('\u0400' <= c <= '\u04ff' for c in text): # Cyrillic
    #     return QFont("Arial", font_size) # Arial usually has good Cyrillic support
    else:
        # Fallback to the default family
        return QFont(default_font_family, font_size)


def initialize_paddle_ocr(lang='en'):
    global paddle_ocr
    logging.info(f"Attempting to initialize PaddleOCR with language: {lang}")
    try:
        # Explicitly free memory if replacing an existing instance
        if paddle_ocr:
            logging.debug("Deleting existing PaddleOCR instance...")
            del paddle_ocr
            paddle_ocr = None
            gc.collect() # Suggest garbage collection
            logging.debug("Existing PaddleOCR instance deleted and GC called.")

        paddle_ocr = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            use_gpu=False, # Keep GPU off for broader compatibility unless specifically needed/configured
            det=True,
            rec=True,
            # e2e=False, # Use det+rec instead of end-to-end
            show_log=False # Keep console clean
        )
        logging.info(f"PaddleOCR initialized successfully for language: {lang}")

    except Exception as e:
        logging.error(f"Failed to initialize PaddleOCR: {e}", exc_info=True) # Log traceback
        paddle_ocr = None
        # Provide more specific error feedback if possible
        msg = f"Failed to initialize PaddleOCR for language '{lang}'.\n\nError: {e}\n\n"
        msg += "Please ensure PaddleOCR and PaddlePaddle are correctly installed.\n"
        msg += "Try running: pip install --upgrade paddleocr paddlepaddle\n"
        msg += "Check internet connection if models need downloading."
        # Can't use QMessageBox here as this might be called before app exec
        print(f"CRITICAL ERROR: {msg}")
        # Consider exiting or disabling OCR features if critical
        # sys.exit(1)


# Add optional argument process_theme
def load_window_positions(process_theme=True):
    global current_theme
    # Initialize theme from default FIRST if processing is intended
    if process_theme:
        current_theme = json.loads(json.dumps(DEFAULT_THEME)) # Deep copy default

    positions = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                positions = json.load(f) # Load the whole file

            # --- Process Theme Section only if requested ---
            if process_theme:
                loaded_theme_data = positions.get('theme')
                if loaded_theme_data and isinstance(loaded_theme_data, dict) and "colors" in loaded_theme_data:
                    # ... (rest of the theme processing logic from previous step) ...
                    temp_theme_name = loaded_theme_data.get('name', DEFAULT_THEME['name'])
                    temp_theme_colors = {}
                    loaded_colors = loaded_theme_data.get("colors", {})
                    all_keys_valid = True
                    for key, default_value in DEFAULT_THEME["colors"].items():
                        loaded_value = loaded_colors.get(key)
                        validated_color = default_value
                        if loaded_value is not None:
                            try:
                                if isinstance(loaded_value, str) and loaded_value.startswith("rgba("):
                                     parts = loaded_value.strip('rgba()').split(',')
                                     r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
                                     a_float = float(parts[3])
                                     a_hex = max(0, min(255, int(a_float * 255)))
                                     hex_color = f"#{a_hex:02X}{r:02X}{g:02X}{b:02X}".upper()
                                     if QColor(hex_color).isValid(): validated_color = hex_color
                                     else: raise ValueError("Converted hex invalid")
                                elif isinstance(loaded_value, str) and loaded_value.startswith('#'):
                                     hex_color = loaded_value.upper()
                                     if len(hex_color) == 7: hex_color = "#FF" + hex_color[1:]
                                     if len(hex_color) == 9 and QColor(hex_color).isValid(): validated_color = hex_color
                                     else: raise ValueError("Invalid hex format/value")
                                else: raise ValueError("Unsupported format")
                            except Exception as e:
                                logging.warning(f"Invalid color format '{loaded_value}' for key '{key}': {e}. Using default.")
                                validated_color = default_value
                                all_keys_valid = False
                        else:
                            logging.warning(f"Loaded theme missing color key: {key}. Using default.")
                            validated_color = default_value
                            all_keys_valid = False
                        temp_theme_colors[key] = validated_color

                    if all_keys_valid:
                        current_theme["name"] = temp_theme_name
                        current_theme["colors"] = temp_theme_colors
                        logging.info(f"Loaded theme: {current_theme.get('name', 'Unnamed')}")
                    else:
                        logging.warning("Using default theme due to missing keys or invalid color formats in loaded theme.")
                        # current_theme remains the default set at the start
                        logging.info(f"Using default theme: {current_theme.get('name', 'Unnamed')}")

                else:
                    logging.info(f"No valid theme found in config. Using default theme: {current_theme.get('name', 'Unnamed')}")
            # --- End Process Theme Section ---

        except json.JSONDecodeError as e:
            logging.error(f"Failed to decode config JSON from {CONFIG_FILE}: {e}")
            if process_theme: current_theme = DEFAULT_THEME.copy()
        except Exception as e:
            logging.error(f"Failed to load config from {CONFIG_FILE}: {e}")
            if process_theme: current_theme = DEFAULT_THEME.copy()
    else:
        logging.info("Config file not found. Using default theme and settings.")
        if process_theme: current_theme = DEFAULT_THEME.copy()

    # If theme wasn't processed, ensure current_theme exists (should be set at app start)
    if 'current_theme' not in globals() or not current_theme:
        current_theme = DEFAULT_THEME.copy() # Safety net

    return positions

def save_window_positions(positions):
    global current_theme
    try:
        # Add the current theme to the dictionary being saved
        positions['theme'] = current_theme
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f: # Specify encoding
            json.dump(positions, f, indent=4, ensure_ascii=False) # ensure_ascii=False for non-latin chars
        logging.info(f"Window positions and theme '{current_theme.get('name', 'Unnamed')}' saved successfully to {CONFIG_FILE}.")
    except Exception as e:
        logging.error(f"Failed to save window positions/theme to {CONFIG_FILE}: {e}")

def generate_stylesheet(theme_colors):
    """Generates the full stylesheet string from theme colors."""
    colors = theme_colors # Shortcut

    # IMPORTANT: Create a *template* string first
    stylesheet_template = f"""
        QDialog, QMainWindow {{
            background-color: {colors['bg_main']};
            color: {colors['text_light']};
            font-family: 'Roboto', Arial, sans-serif;
            border-radius: 15px;
            /* border: 1px solid {colors['border_main']}; */ /* Optional border */
        }}
        QLabel {{
            color: {colors['text_accent']};
            font-size: 14px;
            background-color: transparent;
        }}
         QLabel[objectName="DefaultTextLabel"] {{ /* Example specific label */
            color: {colors['text_light']};
        }}
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {colors['grad_button_start']}, stop:1 {colors['grad_button_end']});
            color: {colors['text_button']};
            border-radius: 10px;
            padding: 12px;
            font-size: 14px;
            font-weight: 600;
            border: none;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {colors['grad_button_hover_start']}, stop:1 {colors['grad_button_hover_end']});
        }}
        QPushButton:pressed {{
            background: {colors['grad_button_pressed']};
            padding-top: 14px;
            padding-bottom: 10px;
        }}
        QPushButton:disabled {{
            background: rgba(120, 120, 120, 100); /* Example: Use a fixed disabled style or theme it */
            color: {colors['text_disabled']};
        }}
        QCheckBox {{
            color: {colors['text_light']};
            font-size: 14px;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px; height: 16px; border-radius: 4px;
            border: 1px solid {colors['border_medium']};
            background-color: {colors['bg_input']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {colors['checkbox_checked']};
            border: 1px solid {colors['checkbox_checked']};
        }}
        QCheckBox::indicator:hover {{
            border: 1px solid {colors['border_accent']};
        }}
        QLineEdit {{
            background: {colors['bg_input']};
            color: {colors['text_light']};
            border: 1px solid {colors['border_light']};
            border-radius: 6px;
            padding: 8px;
        }}
        QLineEdit:focus {{
            border: 1px solid {colors['border_accent']};
        }}
        QGroupBox {{
            color: {colors['text_accent']};
            font-size: 16px; font-weight: 600;
            border: 1px solid {colors['border_light']};
            border-radius: 10px; margin-top: 12px;
            padding-top: 25px; padding-bottom: 10px; padding-left: 10px; padding-right: 10px;
            background: {colors['bg_groupbox']};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 6px 12px; color: {colors['text_accent']};
            margin-left: 10px; margin-top: 3px;
            background-color: {colors['bg_titlebar']};
            border-radius: 5px;
        }}
        QTextEdit {{
            background: {colors['bg_input']};
            color: {colors['text_accent']};
            font-family: 'Roboto Mono', 'Courier New', monospace; font-size: 14px;
            border: 1px solid {colors['border_light']};
            border-radius: 10px; padding: 12px;
        }}
        QSlider::groove:horizontal {{
            height: 6px; background: rgba(255, 255, 255, 20); /* Lighten/darken based on bg? */
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, stop:0 #ffffff, stop:1 {colors['text_secondary']}); /* Use secondary accent */
            width: 16px; height: 16px; border-radius: 8px; margin: -5px 0;
        }}
        QSlider::sub-page:horizontal {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {colors['grad_slider_start']}, stop:1 {colors['grad_slider_end']});
            border-radius: 3px;
        }}
        QComboBox {{
            background: {colors['bg_input']};
            color: {colors['text_accent']};
            border: 1px solid {colors['border_light']};
            border-radius: 6px; padding: 5px;
        }}
        QComboBox:hover {{ border: 1px solid {colors['border_accent']}; }}
        QComboBox::drop-down {{ border: none; background: transparent; width: 20px; }}
        QComboBox::down-arrow {{ image: none; }}
        QComboBox QAbstractItemView {{
            background: {colors['bg_menu']}; /* Use menu bg */
            color: {colors['text_accent']};
            selection-background-color: {colors['bg_menu_item_sel']};
            selection-color: {colors['text_button']};
            border: 1px solid {colors['border_medium']};
            border-radius: 5px; padding: 5px; outline: 0px;
        }}
        QProgressBar {{
            border: 1px solid {colors['border_light']};
            border-radius: 6px; background: {colors['bg_input']};
            color: {colors['text_light']}; text-align: center;
            font-size: 12px; height: 18px;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {colors['progress_chunk_start']}, stop:1 {colors['progress_chunk_end']});
            border-radius: 5px; margin: 1px;
        }}
        QMenuBar {{
            background: {colors['bg_main']}; /* Use main bg or specific menu bg */
            color: {colors['text_accent']};
            font-size: 14px; font-family: 'Roboto', Arial, sans-serif;
        }}
        QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
        QMenuBar::item:selected {{ background: {colors['bg_menu_item_sel']}; color: {colors['text_button']}; }}
        QMenu {{
            background: {colors['bg_menu']};
            color: {colors['text_light']};
            border: 1px solid {colors['border_menu']};
            border-radius: 8px; padding: 5px;
        }}
        QMenu::item {{ padding: 6px 25px; border-radius: 0px; }}
        QMenu::item:selected {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {colors['grad_button_start']}, stop:1 {colors['grad_button_end']}); /* Reuse button gradient */
            color: {colors['text_button']};
        }}
        QMenu::separator {{ height: 1px; background: {colors['border_light']}; margin: 5px 0; }}
         /* Add Tooltip Style */
        QToolTip {{
            background-color: {colors['bg_tooltip']};
            color: {colors['text_tooltip']};
            border: 1px solid {colors['border_medium']};
            padding: 5px;
            border-radius: 4px;
            opacity: 230; /* Requires composition manager */
        }}

        /* Styles for LiveTranslationWindow */
        QDialog#LiveTranslationWindow {{ /* Target specific dialog */
             background-color: {colors['bg_groupbox']}; /* Use groupbox background */
             border: 1px solid {colors['border_accent']}; /* Use accent border color */
             border-radius: 8px; /* Smaller radius */
        }}
        QLabel#LiveLabel {{ /* Target specific label */
             color: {colors['text_accent']}; /* Use accent text color */
             background-color: transparent; /* Ensure transparent background */
             padding: 8px;
             font-weight: normal;
             border: none; /* Ensure label has no border */
        }}

    """
    # Add more rules as needed...
    return stylesheet_template

def apply_theme():
    """Applies the current_theme stylesheet to the application."""
    global current_theme
    try:
        # Ensure current_theme has the necessary structure
        if not isinstance(current_theme, dict) or "colors" not in current_theme:
            logging.error("Invalid theme structure found. Reverting to default.")
            current_theme = DEFAULT_THEME.copy()

        stylesheet = generate_stylesheet(current_theme["colors"])
        app_instance = QApplication.instance()
        if app_instance:
            app_instance.setStyleSheet(stylesheet)
            logging.info(f"Applied theme: {current_theme.get('name', 'Unnamed')}")
        else:
            logging.warning("Cannot apply theme: No QApplication instance exists.")
    except Exception as e:
        logging.error(f"Failed to apply theme: {e}", exc_info=True)
        # Fallback to default stylesheet if generation fails
        try:
             stylesheet = generate_stylesheet(DEFAULT_THEME["colors"])
             app_instance = QApplication.instance()
             if app_instance:
                 app_instance.setStyleSheet(stylesheet)
                 logging.warning("Fell back to default theme due to error.")
        except Exception as fallback_e:
             logging.error(f"Failed to apply even default theme: {fallback_e}")

def ensure_support_folder():
    try:
        if not os.path.exists(SUPPORT_FOLDER):
            os.makedirs(SUPPORT_FOLDER)
            logging.info(f"Created Support folder at {SUPPORT_FOLDER}")
    except OSError as e:
        logging.error(f"Failed to create support folder at {SUPPORT_FOLDER}: {e}")
        # Fallback or notify user? For now, just log the error.

# --- TranslationWorker Thread ---
class TranslationWorker(QThread):
    translation_complete = Signal(dict) # Emit a dictionary with results
    error = Signal(str) # Emit error messages

    def __init__(self, file_name, source_language, target_language, fonts, use_translate_with_ai=False, contrast_factor=1.0, live=False, parent=None):
        super().__init__(parent)
        self.file_name = file_name
        self.source_language = source_language
        self.target_language = target_language
        self.fonts = fonts # Dictionary of font paths
        self.use_translate_with_ai = use_translate_with_ai
        self.contrast_factor = contrast_factor
        self.live = live
        self.is_running = True # Flag to allow stopping the thread

        # Validate inputs
        if not os.path.exists(file_name):
            logging.error(f"Input file does not exist: {file_name}")
            self.is_running = False # Prevent run if file is missing
            # Emit error immediately? Or let run() handle it? Let run handle.

    def stop(self):
        logging.debug(f"TranslationWorker requested to stop for file: {os.path.basename(self.file_name)}")
        self.is_running = False

    def preprocess_image(self, image):
        # Simplified preprocessing - focus on contrast and grayscale/binary
        try:
            start_time = time.time()
            logging.debug(f"Preprocessing image: {image.size}, mode: {image.mode}")

            # Ensure RGB format for consistency
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Apply contrast adjustment
            if self.contrast_factor != 1.0:
                 img_array = np.array(image)
                 img_array = cv2.convertScaleAbs(img_array, alpha=self.contrast_factor, beta=0)
                 image = Image.fromarray(img_array) # Convert back to PIL Image

            # Convert to grayscale
            gray_image = image.convert('L')

            # Apply adaptive thresholding using OpenCV for better text segmentation
            img_array = np.array(gray_image)
            binary = cv2.adaptiveThreshold(img_array, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)

            # Convert back to PIL Image
            preprocessed_image = Image.fromarray(binary)

            logging.debug(f"Preprocessing finished in {time.time() - start_time:.3f} seconds")
            return preprocessed_image

        except Exception as e:
            logging.error(f"Image preprocessing failed: {e}", exc_info=True)
            self.error.emit(f"Image preprocessing failed: {e}")
            raise # Re-raise to stop processing in run()

    def correct_ocr_text(self, text):
        # Simple rule-based corrections (expand as needed)
        corrections = {
            'OpenAl': 'OpenAI', 'CpenAl': 'OpenAI', 'nive penAl': 'nivel OpenAI', # Fixed level OpenAI too
            'tngresa': 'ingresa',
            'seccin': 'sección',
            'suscripcion': 'suscripción',
            'ChatGpT': 'ChatGPT',
            'configuraci6n': 'configuración',
            'interna*': 'interna',
            'aplicaciontodo': 'aplicación todo', # Simple split
            'utlizar': 'utilizar',
            'Ollama ': 'Ollama', # Trailing space
             # Add more common OCR errors based on observation
        }
        corrected_text = text
        for wrong, correct in corrections.items():
            corrected_text = corrected_text.replace(wrong, correct)
        if corrected_text != text:
            logging.debug(f"OCR Correction applied: '{text}' -> '{corrected_text}'")
        return corrected_text

    def translate_with_ai(self, original_text, num_lines):
        """Initiates AI translation using AITranslationWorker."""
        if not self.is_running: return original_text # Check if stopped

        if not ai_api_config.get("provider"):
            logging.warning("No AI API provider configured; skipping AI translation.")
            return None # Return None to indicate fallback needed

        logging.debug(f"Starting AI translation via AITranslationWorker for {num_lines} lines.")
        try:
            # Use QEventLoop to wait for the worker thread synchronously within this thread
            loop = QEventLoop()
            ai_worker = AITranslationWorker(original_text, self.source_language, self.target_language, num_lines)

            translated_text = None
            error_message = None

            def on_translation_complete(text):
                nonlocal translated_text
                translated_text = text
                logging.debug(f"Received AI translation: '{text[:100]}...'")
                if loop.isRunning(): loop.quit()

            def on_error(error):
                nonlocal error_message
                error_message = error
                logging.error(f"AI translation error: {error}")
                if loop.isRunning(): loop.quit()

            def on_finished():
                if loop.isRunning(): loop.quit() # Ensure loop quits even if no signal emitted

            ai_worker.translation_complete.connect(on_translation_complete)
            ai_worker.error.connect(on_error)
            ai_worker.finished.connect(on_finished) # Connect finished signal

            ai_worker.start()
            loop.exec() # Wait here until loop.quit() is called

            # Check if stopped during wait
            if not self.is_running:
                 logging.warning("TranslationWorker stopped during AI translation.")
                 ai_worker.stop() # Try to stop the AI worker too
                 return None

            if error_message:
                logging.error(f"AI translation failed: {error_message}")
                self.error.emit(f"AI Translation Error: {error_message}")
                return None # Indicate fallback needed
            if translated_text is None:
                logging.error("No translation received from AI worker (timed out or other issue).")
                self.error.emit("AI Translation Error: No response received.")
                return None # Indicate fallback needed

            logging.debug(f"AI translation successful, returning: '{translated_text[:100]}...'")
            return translated_text

        except Exception as e:
            logging.error(f"Exception during AI translation initiation or waiting: {e}", exc_info=True)
            self.error.emit(f"AI Translation Exception: {e}")
            return None # Indicate fallback needed

    def translate_with_flask(self, text, src_lang, tgt_lang):
        """Translates text using the local Flask server."""
        if not self.is_running: return None

        url = "http://127.0.0.1:5000/api/translate"
        data = {
            "text": text,
            "source_lang": src_lang,
            "target_lang": tgt_lang
        }
        logging.debug(f"Sending translation request to Flask: {data}")
        try:
            response = requests.post(url, headers={"Content-Type": "application/json"}, json=data, timeout=30) # 30s timeout
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            result = response.json()
            translated_text = result.get("translated_text")
            if translated_text:
                 logging.debug(f"Flask translation successful: '{translated_text[:100]}...'")
                 return translated_text
            else:
                 error_msg = result.get("error", "Empty translation from Flask server.")
                 logging.error(f"Flask server translation failed: {error_msg}")
                 self.error.emit(f"Translation Service Error: {error_msg}")
                 return None
        except requests.exceptions.ConnectionError:
            logging.error(f"Flask server connection failed at {url}.")
            self.error.emit("Translation Service Unavailable (Connection Error)")
            return None
        except requests.exceptions.Timeout:
            logging.error(f"Flask server request timed out ({url}).")
            self.error.emit("Translation Service Timed Out")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Flask server request failed: {e}", exc_info=True)
            self.error.emit(f"Translation Service Request Error: {e}")
            return None
        except json.JSONDecodeError:
             logging.error(f"Failed to decode JSON response from Flask server: {response.text[:200]}")
             self.error.emit("Translation Service Error: Invalid response format.")
             return None


    def run(self):
        if not self.is_running:
            logging.warning(f"TranslationWorker.run cancelled before start for {os.path.basename(self.file_name)}.")
            return

        start_time = time.time()
        result = {'file_name': self.file_name, 'original_text': '', 'translated_text': '', 'error_message': '', 'boxes': [], 'translated_lines': [], 'live': self.live, 'timestamp': datetime.datetime.now()} # Add timestamp

        temp_file = None # Initialize here for finally block

        try:
            # 1. Check PaddleOCR initialization
            if not paddle_ocr:
                raise Exception("PaddleOCR is not initialized. Cannot perform OCR.")

            # 2. Load Image
            try:
                image = Image.open(self.file_name)
                image.load() # Load image data to catch potential file errors early
                logging.debug(f"Image loaded: {self.file_name}, size: {image.size}, mode: {image.mode}")
            except FileNotFoundError:
                raise Exception(f"Image file not found: {self.file_name}")
            except Exception as e:
                raise Exception(f"Failed to load image '{os.path.basename(self.file_name)}': {e}")

            # 3. Preprocess Image
            try:
                preprocessed_image = self.preprocess_image(image)
            except Exception as e:
                # Error already logged in preprocess_image
                raise Exception("Image preprocessing failed.") # Keep message simple here

            # Save preprocessed image for OCR (PaddleOCR often works better with file paths)
            base_name = os.path.basename(self.file_name)
            temp_file_name = f"preprocessed_{os.path.splitext(base_name)[0]}_{int(time.time()*1000)}.png"
            ensure_support_folder() # Make sure folder exists
            temp_file = os.path.join(SUPPORT_FOLDER, temp_file_name)

            try:
                preprocessed_image.save(temp_file, format='PNG')
                logging.debug(f"Preprocessed image saved to: {temp_file}")
            except Exception as e:
                raise Exception(f"Failed to save preprocessed image: {e}")

            # 4. Perform OCR
            logging.debug(f"Starting PaddleOCR on: {temp_file}")
            ocr_start_time = time.time()
            try:
                # Wrap OCR call in try/except RuntimeError
                try:
                    ocr_result = paddle_ocr.ocr(temp_file, cls=True)
                except RuntimeError as ocr_runtime_err:
                    # Catch the specific low-level error
                    logging.error(f"PaddleOCR runtime error: {ocr_runtime_err}", exc_info=True)
                    raise Exception(f"OCR engine runtime error: {ocr_runtime_err}")
                # End Wrap
                logging.debug(f"PaddleOCR finished in {time.time() - ocr_start_time:.3f} seconds.")
            except Exception as e:
                # Keep the general exception handling, but the RuntimeError is now more specific
                logging.error(f"PaddleOCR processing failed: {e}", exc_info=True)
                raise Exception(f"OCR engine failed: {e}") # Re-raise general or the specific one from above


            # Check if stopped during OCR
            if not self.is_running:
                logging.warning("TranslationWorker stopped during OCR.")
                return

            # 5. Process OCR Results
            if not ocr_result or not ocr_result[0]: # Handle empty or invalid result
                logging.warning("OCR detected no text.")
                result['translated_text'] = "No text detected."
            else:
                lines = []
                boxes = []
                confidences = []
                for line_info in ocr_result[0]:
                    if len(line_info) >= 2 and len(line_info[0]) >= 4 and len(line_info[1]) >= 2:
                        box = line_info[0]
                        text = line_info[1][0]
                        confidence = line_info[1][1]

                        x_coords = [p[0] for p in box]
                        y_coords = [p[1] for p in box]
                        left, top = min(x_coords), min(y_coords)
                        right, bottom = max(x_coords), max(y_coords)

                        lines.append(text)
                        boxes.append((left, top, right, bottom))
                        confidences.append(confidence)
                    else:
                        logging.warning(f"Unexpected OCR result structure skipped: {line_info}")

                if not lines:
                    logging.warning("OCR result structure valid, but no lines extracted.")
                    result['translated_text'] = "No text detected (extraction failed)."
                else:
                    original_text = '\n'.join(lines)
                    original_text = self.correct_ocr_text(original_text)
                    result['original_text'] = original_text
                    result['boxes'] = boxes
                    avg_confidence = sum(confidences) / len(confidences) if confidences else 0
                    logging.info(f"OCR successful: Found {len(lines)} lines. Avg Confidence: {avg_confidence:.2f}")
                    logging.debug(f"Original Text:\n{original_text}")

                    # 6. Determine Source Language
                    actual_source_lang = self.source_language
                    if actual_source_lang == 'auto':
                        try:
                            if len(original_text.strip()) > 5:
                                # Limit text length for langdetect
                                text_to_detect = original_text[:1000] if len(original_text) > 1000 else original_text
                                detected_lang = detect(text_to_detect)
                                actual_source_lang = detected_lang
                                logging.info(f"Detected source language: {actual_source_lang}")
                            else:
                                logging.info("Text too short for auto-detection, keeping 'auto'.")
                        except Exception as lang_detect_err:
                            logging.warning(f"Language detection failed: {lang_detect_err}. Falling back to English ('en').")
                            actual_source_lang = 'en' # Fallback
                            self.error.emit("Language detection failed, using English.")

                    # 7. Translate
                    translated_text = None
                    if self.use_translate_with_ai and not self.live:
                        logging.info("Attempting translation with AI...")
                        translated_text = self.translate_with_ai(original_text, len(lines))
                        if translated_text:
                            logging.info("AI translation successful.")
                        else:
                            logging.warning("AI translation failed or returned empty. Falling back to Flask server.")

                    if translated_text is None:
                        logging.info("Attempting translation with Flask server...")
                        translated_text = self.translate_with_flask(original_text, actual_source_lang, self.target_language)
                        if translated_text:
                            logging.info("Flask translation successful.")
                        else:
                             logging.error("Flask translation also failed.")
                             translated_text = "Translation failed (Service Unavailable)." # Final fallback text

                    # 8. Process Translated Text
                    result['translated_text'] = translated_text if translated_text else "Translation Failed."
                    logging.debug(f"Final translated_text for result: '{result['translated_text'][:100]}...'")

                    if translated_text and translated_text != "Translation failed (Service Unavailable)." and translated_text != "No text detected.":
                        translated_lines_raw = translated_text.split('\n')
                        logging.debug(f"Raw translated lines: {len(translated_lines_raw)}")

                        num_boxes = len(boxes)
                        num_translated_raw = len(translated_lines_raw)

                        if num_translated_raw == num_boxes:
                            result['translated_lines'] = translated_lines_raw
                            logging.debug("Translated line count matches box count.")
                        else:
                            logging.warning(f"Mismatch: {num_translated_raw} translated lines for {num_boxes} boxes. Attempting redistribution.")
                            if num_translated_raw < num_boxes:
                                logging.debug(f"Padding translated lines with {num_boxes - num_translated_raw} empty strings.")
                                result['translated_lines'] = translated_lines_raw + [""] * (num_boxes - num_translated_raw)
                            else: # num_translated_raw > num_boxes
                                logging.debug(f"Truncating translated lines from {num_translated_raw} to {num_boxes}.")
                                result['translated_lines'] = translated_lines_raw[:num_boxes]
                    else:
                        result['translated_lines'] = [""] * len(boxes) # Provide empty strings for each box

        except Exception as e:
            logging.error(f"Error in TranslationWorker run: {e}", exc_info=True)
            result['error_message'] = str(e)
            if not result.get('translated_text'):
                result['translated_text'] = f"Error: {e}"
            self.error.emit(result['error_message'])

        finally:
            # Clean up temporary preprocessed file
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logging.debug(f"Removed temporary file: {temp_file}")
                except Exception as e:
                    logging.warning(f"Failed to remove temporary file {temp_file}: {e}")

            # Emit result if the thread wasn't stopped externally
            if self.is_running:
                total_time = time.time() - start_time
                logging.info(f"TranslationWorker finished in {total_time:.3f} seconds for {os.path.basename(self.file_name)}.")
                logging.debug(f"Emitting result: translated_lines count = {len(result.get('translated_lines', []))}")
                self.translation_complete.emit(result)
            else:
                logging.warning(f"TranslationWorker finished but was stopped, not emitting result for {os.path.basename(self.file_name)}.")


# --- AITranslationWorker Thread ---
class AITranslationWorker(QThread):
    translation_complete = Signal(str) # Emits the final translated string
    error = Signal(str) # Emits error messages

    def __init__(self, text, source_language, target_language, num_lines, parent=None):
        super().__init__(parent)
        self.text = text
        self.source_language = source_language # Keep for potential future use in prompt
        self.target_language = target_language
        self.num_lines = num_lines # Crucial for formatting the output correctly
        self.is_running = True

    def stop(self):
        logging.debug("AITranslationWorker requested to stop.")
        self.is_running = False

    def run(self):
        if not self.is_running:
            logging.warning("AITranslationWorker cancelled before start.")
            return

        if not ai_api_config.get("provider"):
            self.error.emit("No AI API provider configured.")
            logging.error("AI translation run attempted without configured provider.")
            return

        start_time = time.time()
        logging.info(f"Starting AI translation ({ai_api_config['provider']}) for {self.num_lines} lines...")

        try:
            # Language mapping for prompt clarity
            lang_map = { "en": "English", "es": "Spanish", "fr": "French", "de": "German",
                         "it": "Italian", "pt": "Portuguese", "ru": "Russian",
                         "zh-cn": "Simplified Chinese", "ja": "Japanese", "ko": "Korean",
                         "ch": "Chinese" # Add mapping for PaddleOCR's 'ch'
                       }
            target_lang_name = lang_map.get(self.target_language, self.target_language) # Default to code if not mapped
            source_lang_name = lang_map.get(self.source_language, self.source_language) # Map source too

            # Construct the prompt carefully
            lines = self.text.split('\n')
            # Ensure we don't exceed the expected number of lines in the input representation
            lines_to_process = lines[:self.num_lines]
            numbered_text = '\n'.join(f"{i+1}. {line}" for i, line in enumerate(lines_to_process))

            # Refined Prompt - Explicitly ask for line-by-line and number matching
            prompt = (
                f"Translate the following numbered text from {source_lang_name} to {target_lang_name}. "
                f"Provide a translation for each numbered line. Maintain the original line breaks and meaning. "
                f"The output MUST contain exactly {self.num_lines} numbered lines, corresponding to the input lines. "
                f"If an input line is empty or untranslatable, provide an empty translation for that number (e.g., '3. '). "
                f"Do not add any introductory text, summaries, or explanations. Only provide the numbered translated lines.\n\n"
                f"Input Text:\n{numbered_text}\n\n"
                f"Translated Text ({target_lang_name}):"
            )
            logging.debug(f"AI Translation Prompt:\n---PROMPT START---\n{prompt}\n---PROMPT END---")


            headers = {"Content-Type": "application/json"}
            api_key = None
            provider = ai_api_config["provider"]
            endpoint = ai_api_config["endpoint"]

            # Get API key securely if needed
            if provider in ["OpenAI", "LM Studio"]:
                 try:
                     api_key = keyring.get_password("OverlayTranslate", provider)
                     if api_key:
                         headers["Authorization"] = f"Bearer {api_key}"
                     else:
                         # Allow LM Studio potentially without key if server configured that way
                         if provider == "OpenAI":
                            raise ValueError(f"API key for {provider} not found in keyring.")
                         else:
                            logging.warning(f"API key for {provider} not found, proceeding without Authorization header.")
                 except Exception as key_err:
                     raise ValueError(f"Failed to retrieve API key for {provider}: {key_err}")


            response = None
            max_tokens = max(150 * self.num_lines, 200) # Estimate tokens needed, minimum 200

            # --- API Specific Request Logic ---
            if provider == "OpenAI":
                data = {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens, "temperature": 0.3, "n": 1, "stop": None
                }
                logging.debug(f"Sending request to OpenAI: {endpoint}, data: {data}")
                response = requests.post(endpoint, headers=headers, json=data, timeout=60)
            elif provider == "Ollama":
                if endpoint.endswith('/api/chat'):
                     data = {
                         "model": "llama3.1:8b", # Example model, adjust if needed
                         "messages": [{"role": "user", "content": prompt}],
                         "stream": False, "options": { "temperature": 0.3, "num_predict": max_tokens }
                     }
                     logging.debug(f"Sending request to Ollama (chat): {endpoint}, data: {data}")
                     response = requests.post(endpoint, headers=headers, json=data, timeout=60)
                elif endpoint.endswith('/api/generate'):
                     data = {
                         "model": "llama3.1:8b", # Example model
                         "prompt": prompt, "stream": False,
                         "options": { "temperature": 0.3, "num_predict": max_tokens }
                     }
                     logging.debug(f"Sending request to Ollama (generate): {endpoint}, data: {data}")
                     response = requests.post(endpoint, headers=headers, json=data, timeout=60)
                else:
                    raise ValueError("Ollama endpoint must end with /api/chat or /api/generate")
            elif provider == "LM Studio":
                data = {
                    "model": "loaded-model", # Assume user loads model in LM Studio UI
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens, "temperature": 0.3, "stream": False
                }
                logging.debug(f"Sending request to LM Studio: {endpoint}, data: {data}")
                response = requests.post(endpoint, headers=headers, json=data, timeout=60)
            else:
                raise ValueError(f"Unsupported AI provider: {provider}")

            # --- Process Response ---
            if not self.is_running: return

            response.raise_for_status()
            result = response.json()
            logging.debug(f"AI Response JSON: {result}")

            raw_translated_text = ""
            if provider == "OpenAI" or provider == "LM Studio":
                if "choices" in result and len(result["choices"]) > 0 and "message" in result["choices"][0] and "content" in result["choices"][0]["message"]:
                    raw_translated_text = result["choices"][0]["message"]["content"]
                else:
                    logging.error(f"Unexpected response structure from {provider}: {result}")
                    raise ValueError(f"Invalid response format from {provider}.")
            elif provider == "Ollama":
                if endpoint.endswith('/api/chat'):
                    if "message" in result and "content" in result["message"]:
                        raw_translated_text = result["message"]["content"]
                    else:
                         logging.error(f"Unexpected response structure from Ollama Chat: {result}")
                         raise ValueError("Invalid response format from Ollama Chat.")
                elif endpoint.endswith('/api/generate'):
                     if "response" in result:
                        raw_translated_text = result["response"]
                     else:
                         logging.error(f"Unexpected response structure from Ollama Generate: {result}")
                         raise ValueError("Invalid response format from Ollama Generate.")

            if not raw_translated_text:
                logging.warning("AI response content is empty.")
                raise ValueError("AI returned an empty response.")

            logging.debug(f"Raw AI translated text:\n---RAW START---\n{raw_translated_text}\n---RAW END---")

            # --- Parse the numbered lines from the response using Regex --- # MODIFIED SECTION
            translated_lines = [""] * self.num_lines # Initialize with empty strings
            lines_found = 0
            # Regex to find lines starting with optional space, number, dot/paren, optional space
            # Captures the number (group 1) and the content (group 2)
            line_pattern = re.compile(r"^\s*(\d+)[\.\)]\s*(.*)") # Using re.compile for efficiency

            for line in raw_translated_text.split('\n'):
                line = line.strip() # Strip leading/trailing whitespace from the whole line first
                if not line: continue

                match = line_pattern.match(line)
                if match:
                    try:
                        line_num_str = match.group(1)
                        content = match.group(2).strip() # Strip content after matching
                        line_index = int(line_num_str) - 1 # Convert to 0-based index

                        # Ensure index is valid for the expected number of lines
                        if 0 <= line_index < self.num_lines:
                            translated_lines[line_index] = content
                            lines_found += 1
                            # logging.debug(f"Parsed line {line_index + 1}: '{content}'") # Optional debug log
                        else:
                            logging.warning(f"Parsed line number {line_index + 1} is out of expected range (1-{self.num_lines}). Ignoring: '{line}'")
                    except ValueError:
                        logging.warning(f"Could not convert parsed line number '{line_num_str}' to int. Ignoring: '{line}'")
                    except Exception as parse_err:
                         logging.error(f"Error processing matched line '{line}': {parse_err}")
                else:
                    # Log lines that *don't* match the expected format
                    logging.warning(f"AI response line did not match expected number format: '{line}'")
                    # Optional: Handle non-matching lines (e.g., append to previous) - Ignoring for now
                    pass

            logging.debug(f"Parsed translated lines (found {lines_found}): {translated_lines}")
            # --- END MODIFIED PARSING SECTION ---

            # Post-processing / Validation
            if lines_found == 0 and self.num_lines > 0:
                 # If regex failed BUT there was raw text, maybe fall back?
                 logging.warning("Regex failed to parse lines, attempting simple newline split as fallback.")
                 raw_lines_split = raw_translated_text.strip().split('\n')
                 if len(raw_lines_split) == self.num_lines:
                     logging.info("Fallback split matches line count. Using.")
                     translated_lines = [l.strip() for l in raw_lines_split]
                 else:
                     logging.error("Fallback split also failed. AI response did not follow required format.")
                     raise ValueError("AI response did not follow the required numbered format.")

            # Join the cleaned lines back together
            final_text = '\n'.join(translated_lines)
            logging.info(f"AI translation processing finished in {time.time() - start_time:.3f} seconds.")
            logging.debug(f"Final processed AI text:\n---FINAL START---\n{final_text}\n---FINAL END---")

            # Emit the result if still running
            if self.is_running:
                self.translation_complete.emit(final_text)

        except requests.exceptions.RequestException as e:
            # --- THIS IS THE LINE TO FIX ---
            error_msg = f"API Request Error: {e}"
            logging.error(f"AI translation request failed ({provider}): {e}", exc_info=True)
            # Change error_stream to error
            if self.is_running: self.error.emit(error_msg)
            # --- END FIX ---
        except ValueError as e: # Handle specific value errors (parsing, keys, etc.)
            error_msg = f"AI Processing Error: {e}"
            logging.error(f"AI processing error ({provider}): {e}", exc_info=True)
            if self.is_running: self.error.emit(error_msg) # Correctly uses self.error
        except RuntimeError as e:
             error_msg = f"Runtime Error: {e}"
             logging.error(f"AI streaming runtime error ({provider}): {e}", exc_info=True)
             # This block originally raised the error, let's emit instead for consistency
             if self.is_running: self.error.emit(error_msg) # Emit error instead of raising
        except Exception as e:
            error_msg = f"Unexpected Error: {e}"
            logging.error(f"Unexpected error in AI translation ({provider}): {e}", exc_info=True)
            if self.is_running: self.error.emit(error_msg) # Correctly uses self.error
        finally:
            self.is_running = False # Ensure state is false on exit

class ColorBarPicker(QWidget):
    colorChanged = Signal(QColor)

    def __init__(self, initial_color=QColor(0, 0, 255, 255), parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 80) # Adjusted height for value slider
        h, s, v, a = initial_color.getHsvF()
        self.hue = h if h != -1 else 0.0
        self.saturation = s
        self.value = v
        # Store alpha as int 0-255 for consistency with QColorDialog and config saving
        self.alpha = initial_color.alpha()
        self.setMouseTracking(True)
        self.initUI()
        # Set initial values correctly
        self.updateSliders()
        self.updateSlidersBackground()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.hue_bar_widget = QWidget(self)
        self.hue_bar_widget.setFixedHeight(20)
        self.hue_bar_widget.setCursor(Qt.PointingHandCursor)
        self.hue_bar_widget.paintEvent = self.paintHueBar
        self.hue_bar_widget.mousePressEvent = self.hueBarMousePress
        self.hue_bar_widget.mouseMoveEvent = self.hueBarMouseMove
        layout.addWidget(self.hue_bar_widget)

        saturation_layout = QHBoxLayout()
        saturation_layout.addWidget(QLabel("S:"))
        self.saturation_slider = QSlider(Qt.Horizontal, self)
        self.saturation_slider.setRange(0, 100)
        self.saturation_slider.valueChanged.connect(self.updateSaturation)
        saturation_layout.addWidget(self.saturation_slider)
        layout.addLayout(saturation_layout)

        value_layout = QHBoxLayout()
        value_layout.addWidget(QLabel("V:"))
        self.value_slider = QSlider(Qt.Horizontal, self)
        self.value_slider.setRange(0, 100)
        self.value_slider.valueChanged.connect(self.updateValue)
        value_layout.addWidget(self.value_slider)
        layout.addLayout(value_layout)

    def paintHueBar(self, event):
        painter = QPainter(self.hue_bar_widget)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.hue_bar_widget.rect()
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        steps = 6
        for i in range(steps + 1):
            gradient.setColorAt(i / steps, QColor.fromHsvF(i / steps, 1.0, 1.0, 1.0)) # Opaque hue bar
        painter.fillRect(rect, gradient)
        hue_pos_x = int(self.hue * rect.width())
        # Indicator color contrasts with current value
        indicator_color = Qt.white if self.value < 0.5 else Qt.black
        painter.setPen(QPen(indicator_color, 2))
        painter.drawLine(hue_pos_x, rect.top(), hue_pos_x, rect.bottom())

    def updateColorFromQColor(self, color):
        h, s, v, a = color.getHsvF()
        self.hue = h if h != -1 else self.hue # Keep current hue if input has none (e.g., black/white)
        self.saturation = s
        self.value = v
        self.alpha = color.alpha() # Store alpha as int 0-255
        self.updateSliders()
        self.updateSlidersBackground()
        self.hue_bar_widget.update()

    def updateSliders(self):
        self.saturation_slider.blockSignals(True)
        self.value_slider.blockSignals(True)
        self.saturation_slider.setValue(int(self.saturation * 100))
        self.value_slider.setValue(int(self.value * 100))
        self.saturation_slider.blockSignals(False)
        self.value_slider.blockSignals(False)

    def updateSlidersBackground(self):
         # Update slider backgrounds to reflect current color, but opaque for clarity
         sat_start_color = QColor.fromHsvF(self.hue, 0.0, self.value, 1.0) # Opaque
         sat_end_color = QColor.fromHsvF(self.hue, 1.0, self.value, 1.0)   # Opaque
         # Basic slider style (can be customized further by global theme if selector added)
         slider_style = """
             QSlider::groove:horizontal { height: 8px; background: #555; border-radius: 4px; }
             QSlider::handle:horizontal { background: white; border: 1px solid #aaa; width: 14px; height: 14px; border-radius: 7px; margin: -3px 0; }
         """
         sat_style = slider_style + f"QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {sat_start_color.name()}, stop:1 {sat_end_color.name()}); border-radius: 4px; }}"
         self.saturation_slider.setStyleSheet(sat_style)

         val_start_color = QColor.fromHsvF(self.hue, self.saturation, 0.0, 1.0) # Black (Opaque)
         val_end_color = QColor.fromHsvF(self.hue, self.saturation, 1.0, 1.0) # Full value color (Opaque)
         val_style = slider_style + f"QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {val_start_color.name()}, stop:1 {val_end_color.name()}); border-radius: 4px; }}"
         self.value_slider.setStyleSheet(val_style)

    def hueBarMousePress(self, event):
        if event.button() == Qt.LeftButton: self.updateHueFromMouse(event.position())
    def hueBarMouseMove(self, event):
        if event.buttons() & Qt.LeftButton: self.updateHueFromMouse(event.position())

    def updateHueFromMouse(self, pos):
        x = max(0, min(pos.x(), self.hue_bar_widget.width()))
        self.hue = x / self.hue_bar_widget.width()
        self.hue_bar_widget.update()
        self.updateSlidersBackground()
        self.emitColorChange()

    def updateSaturation(self, value):
        self.saturation = value / 100.0
        self.updateSlidersBackground()
        self.emitColorChange()

    def updateValue(self, value):
        self.value = value / 100.0
        self.updateSlidersBackground()
        self.hue_bar_widget.update() # Need to repaint hue bar indicator color
        self.emitColorChange()

    def emitColorChange(self):
        # Emit color including the stored alpha value
        new_color = QColor.fromHsv(int(self.hue * 359), int(self.saturation * 255), int(self.value * 255), self.alpha)
        self.colorChanged.emit(new_color)

    def getColor(self):
        # Return color with correct alpha
        return QColor.fromHsv(int(self.hue * 359), int(self.saturation * 255), int(self.value * 255), self.alpha)

    def setColor(self, color):
        self.updateColorFromQColor(color)
        # Don't emit signal here, called externally usually

class ThemeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Theme Settings")
        self.setMinimumWidth(500)
        # Inherits style from global theme
        self.current_local_theme = json.loads(json.dumps(current_theme)) # Deep copy
        logging.debug(f"ThemeDialog attempting to initialize with local theme: {self.current_local_theme['name']}")
        # --- Add Validation Step ---
        colors_valid = True
        for key, color_str in self.current_local_theme["colors"].items():
            if not (isinstance(color_str, str) and color_str.startswith('#') and len(color_str) == 9 and QColor(color_str).isValid()):
                logging.error(f"ThemeDialog received invalid color format for key '{key}': '{color_str}'. Reverting local theme to default.")
                colors_valid = False
                break
        if not colors_valid:
            self.current_local_theme = json.loads(json.dumps(DEFAULT_THEME)) # Revert local copy
        # --- End Validation ---
        self.layout = QVBoxLayout(self)
#        self.current_local_theme = current_theme.copy()
#        self.layout = QVBoxLayout(self)
        self.color_pickers = {}

        grid_layout = QtWidgets.QGridLayout()
        row, col = 0, 0
        for key, name in self.get_user_friendly_names().items():
            if key not in self.current_local_theme["colors"]: continue # Skip if key missing in theme
            label = QLabel(f"{name}:")
            color_button = QPushButton()
            color_button.setFixedSize(80, 25)
            self.update_button_color(color_button, self.current_local_theme["colors"][key])
            color_button.clicked.connect(lambda k=key, b=color_button: self.pick_color(k, b))

            grid_layout.addWidget(label, row, col * 2)
            grid_layout.addWidget(color_button, row, col * 2 + 1)

            col += 1
            if col >= 2: col = 0; row += 1
            self.color_pickers[key] = color_button

        self.layout.addLayout(grid_layout)
        self.layout.addStretch()

        button_layout = QHBoxLayout()
        reset_btn = QPushButton("Reset to Default")
        save_btn = QPushButton("Save & Apply")
        cancel_btn = QPushButton("Cancel")
        reset_btn.clicked.connect(self.reset_theme)
        save_btn.clicked.connect(self.save_and_apply)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(reset_btn)
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)
        self.layout.addLayout(button_layout)

    def get_user_friendly_names(self):
        # Map internal keys to user-friendly names
        return {
            "bg_main": "Main Background", "bg_groupbox": "Group Box BG", "bg_input": "Input BG",
            "text_light": "Primary Text", "text_accent": "Accent Text", "text_secondary": "Secondary Text",
            "text_button": "Button Text", "border_accent": "Accent Border", "border_light": "Light Border",
            "grad_button_start": "Button Grad Start", "grad_button_end": "Button Grad End",
            "grad_slider_start": "Slider Grad Start", "grad_slider_end": "Slider Grad End",
             "checkbox_checked": "Checkbox Checked", "bg_titlebar": "Group Title BG",
             "bg_tooltip": "Tooltip BG", "text_tooltip": "Tooltip Text", "border_medium": "Medium Border",
             "grad_button_hover_start": "Btn Hover Start", "grad_button_hover_end": "Btn Hover End",
             "grad_button_pressed": "Btn Pressed BG", "progress_chunk_start": "Progress Start",
             "progress_chunk_end": "Progress End", "bg_menu": "Menu BG", "bg_menu_item_sel": "Menu Sel BG",
             "border_menu": "Menu Border", "text_disabled": "Disabled Text"
            # Add more mappings for other keys you want to expose
        }

    def update_button_color(self, button, color_str):
        try:
            color = QColor(color_str)
            if color.isValid():
                # Ensure alpha is visible but not fully opaque for preview
                display_color = QColor(color.red(), color.green(), color.blue(), max(color.alpha(), 150))
                button.setStyleSheet(f"background-color: {display_color.name(QColor.NameFormat.HexArgb)}; border: 1px solid #888;")
            else:
                logging.warning(f"Invalid color string for button: {color_str}")
                button.setStyleSheet("background-color: grey; border: 1px solid #888;")
        except Exception as e:
             logging.error(f"Error setting button color for '{color_str}': {e}")
             button.setStyleSheet("background-color: red; border: 1px solid #888;") # Error indicator

    def pick_color(self, key, button):
        try:
            initial_color = QColor(self.current_local_theme["colors"][key])
            if not initial_color.isValid():
                raise ValueError("Invalid initial color string")
        except Exception:
            logging.warning(f"Invalid initial color for key '{key}', using white.")
            initial_color = QColor("#ffffffff") # Fallback to opaque white

        color_dialog = QColorDialog(initial_color, self)
        color_dialog.setOptions(QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color_dialog.exec():
             color = color_dialog.selectedColor()
             if color.isValid():
                 color_str = color.name(QColor.NameFormat.HexArgb) # e.g., #AARRGGBB
                 self.current_local_theme["colors"][key] = color_str
                 self.update_button_color(button, color_str)

    def reset_theme(self):
        self.current_local_theme = DEFAULT_THEME.copy()
        for key, button in self.color_pickers.items():
            if key in self.current_local_theme["colors"]:
                 self.update_button_color(button, self.current_local_theme["colors"][key])
        QMessageBox.information(self, "Theme Reset", "Theme reset to default. Click 'Save & Apply' to confirm.")

    def save_and_apply(self):
        global current_theme
        current_theme = self.current_local_theme.copy()
        apply_theme()
        # Theme is saved implicitly via ControlWindow's close/save actions
        self.accept()


# --- LiveTranslationWindow Dialog ---
class LiveTranslationWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Live Translation")
        # --- Set Object Name for Styling ---
        self.setObjectName("LiveTranslationWindow")
        # --- END Set Object Name ---
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground) # Allow transparency
        self.setMinimumSize(300, 80)

        self.initUI()
        self.load_geometry()
        self.offset = None

        # +++ Add Opacity Effect and Animation members +++
        self.label_opacity_effect = QGraphicsOpacityEffect(self)
        self.translation_label.setGraphicsEffect(self.label_opacity_effect)
        self.label_fade_anim = QPropertyAnimation(self.label_opacity_effect, b"opacity", self)
        self.label_fade_anim.setDuration(250) # Faster fade for live update
        self.label_fade_anim.setStartValue(0.0)
        self.label_fade_anim.setEndValue(1.0)
        self.label_fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        # +++ END Add +++

    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        self.translation_label = QLabel("Initializing live translation...", self)
        # --- Set Object Name for Styling ---
        self.translation_label.setObjectName("LiveLabel")
        # --- END Set Object Name ---
        self.translation_label.setWordWrap(True)
        self.translation_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.translation_label)
        self.setLayout(layout)

        # Optional shadow effect (can be themed later if needed)
        # shadow = QGraphicsDropShadowEffect(self)
        # shadow.setBlurRadius(15)
        # shadow.setColor(QColor(0, 0, 0, 180))
        # shadow.setOffset(2, 2)
        # self.translation_label.setGraphicsEffect(shadow)

    def updateTranslation(self, text):
        flat_text = text.replace('\n', ' ').strip()
        if not flat_text:
            flat_text = "..." # Show ellipsis if empty
        # --- Text and Font are set here, fade is controlled externally ---
        self.translation_label.setText(flat_text)
        self.translation_label.setFont(choose_font_for_text(flat_text, default_font_family="Roboto", font_size=18)) # Slightly smaller font
        self.adjustSize() # Adjust size based on content
        # --- Fade animation is NOT triggered here directly ---

    def load_geometry(self):
        positions = load_window_positions()
        if 'LiveTranslationWindow' in positions:
            try:
                geo = positions['LiveTranslationWindow']
                if all(k in geo for k in ('x', 'y', 'width', 'height')):
                    self.setGeometry(int(geo['x']), int(geo['y']), int(geo['width']), int(geo['height']))
                else:
                    logging.warning("LiveTranslationWindow geometry in config is incomplete. Using default.")
                    self.resize(350, 100) # Default size if config is bad
            except (ValueError, TypeError) as e:
                 logging.error(f"Error loading LiveTranslationWindow geometry: {e}. Using default.")
                 self.resize(350, 100)
        else:
            self.resize(350, 100) # Default size if not in config

    def save_geometry(self):
#        positions = load_window_positions() # Load existing
#        positions['LiveTranslationWindow'] = {
#            'x': self.x(),
#            'y': self.y(),
#            'width': self.width(),
#            'height': self.height()
#        }
#        # Call main save function
#        save_window_positions(positions)
        logging.debug("ControlWindow.save_geometry called (no immediate save).")
        pass
    # --- Window Dragging Logic ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.position().toPoint()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() == Qt.LeftButton:
            new_pos = self.mapToGlobal(event.position().toPoint() - self.offset)
            screen_geometry = QApplication.primaryScreen().availableGeometry()
            new_pos.setX(max(screen_geometry.left(), min(new_pos.x(), screen_geometry.right() - self.width())))
            new_pos.setY(max(screen_geometry.top(), min(new_pos.y(), screen_geometry.bottom() - self.height())))
            self.move(new_pos)
            event.accept()
        else:
             super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def closeEvent(self, event):
        self.save_geometry()
        event.accept()


# --- IntroDialog ---
class IntroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌌 Overlay Translate")
        self.setMinimumSize(450, 500) # Increased size slightly
        # Make it modal initially
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint | Qt.WindowStaysOnTopHint)
        # Theme applied globally
        self.initUI()
        # Center on parent or screen
        if parent:
            try: # Ensure parent geometry is valid
                parent_geo = parent.geometry()
                if parent_geo.isValid():
                    self.move(parent_geo.center() - self.rect().center())
                else: # Fallback if parent geo invalid
                     self.move(QApplication.primaryScreen().availableGeometry().center() - self.rect().center())
            except Exception: # Fallback to screen center on any error
                self.move(QApplication.primaryScreen().availableGeometry().center() - self.rect().center())
        else:
            self.move(QApplication.primaryScreen().availableGeometry().center() - self.rect().center())
        self.raise_()
        self.activateWindow()


    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15) # Add spacing

        # Use RichText for better formatting - colors will come from theme
        intro_text = """
        <h2 style='text-align: center; margin-bottom: 15px; font-weight: 600;'>🌌 Welcome to Overlay Translate</h2>
        <p style='line-height: 1.6; font-size: 15px;'>
            ⚡️ Experience seamless screen text capture and translation with a futuristic edge.
        </p>
        <br/>
        <h3 style='font-weight: 600;'>🔮 Features:</h3>
        <ul style='line-height: 1.7; margin-left: 20px; font-size: 14px;'>
            <li>📷 Instant text capture</li>
            <li>🎥 Real-time translation streams</li>
            <li>🌍 Offline multilingual support</li>
            <li>🖥️ Sleek, modern interface</li>
            <li>💬 AI-powered chat</li>
            <li>💾 Save captures effortlessly</li>
            <li>⚙️ Customizable settings</li>
        </ul>
        <br/>
        <p style='text-align: center; font-size: 16px; font-weight: bold;'>
            Dive into the future of translation! 🚀
        </p>
        """
        intro_label = QLabel(intro_text)
        intro_label.setWordWrap(True)
        intro_label.setTextFormat(Qt.RichText) # Important for HTML styles
        intro_label.setAlignment(Qt.AlignLeft) # Align list left

        close_button = QPushButton("Launch")
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "launch.svg")
        if os.path.exists(icon_path):
            close_button.setIcon(QIcon(icon_path))
            close_button.setIconSize(QtCore.QSize(20, 20)) # Set icon size
        else:
            logging.warning(f"Launch icon not found at: {icon_path}")

        close_button.clicked.connect(self.accept) # Use accept() for standard dialog closing

        # Add a subtle shadow to the button
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        # +++ CORRECTED COLOR SETTING +++
        try:
            accent_color = QColor(current_theme["colors"].get("text_accent", "#00ffcc"))
            if accent_color.isValid():
                shadow_color = accent_color.lighter(110) # Get lighter color
                shadow_color.setAlpha(100) # Set alpha (0-255)
                shadow.setColor(shadow_color) # Set the QColor object
            else:
                # Fallback if accent color is invalid
                shadow.setColor(QColor(0, 255, 204, 100))
        except Exception: # Catch potential errors getting/parsing color
             shadow.setColor(QColor(0, 255, 204, 100)) # Default fallback
        # +++ END CORRECTION +++
        shadow.setOffset(0, 2) # Small vertical offset
        close_button.setGraphicsEffect(shadow)

        layout.addWidget(intro_label)
        layout.addStretch(1) # Push button to bottom
        layout.addWidget(close_button)
        self.setLayout(layout)

        # Fade-in Animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity", self) # Parent animation to self
        self.animation.setDuration(800)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.animation.start()

# --- DraggableResizableWidget ---
# (Kept as is)
class DraggableResizableWidget(QWidget):
    def __init__(self, widget, parent=None):
        super().__init__(parent)
        self.widget = widget
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(widget)
        self.setMinimumSize(50, 50)

        self.dragging = False
        self.resizing = False
        self.drag_start_pos = None
        self.resize_start_pos = None
        self.original_pos = None
        self.original_size = None
        self.is_in_design_mode = False # Controlled externally

        self.handle_size = 10
        self.drag_handle_rect = QRect() # Initialized in paintEvent
        self.resize_handle_rect = QRect() # Initialized in paintEvent

        self.setMouseTracking(True) # Needed for hover cursors

    def set_design_mode(self, enabled):
        self.is_in_design_mode = enabled
        self.update() # Trigger repaint

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.is_in_design_mode:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Dashed border around the widget
            pen = QPen(QColor(0, 255, 204, 150), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush) # No fill for the border rectangle
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1)) # Adjust to be inside bounds

            # Drag handle (Top-Left)
            painter.setBrush(QColor(0, 255, 204, 180))
            painter.setPen(Qt.NoPen)
            self.drag_handle_rect = QRect(0, 0, self.handle_size, self.handle_size)
            painter.drawRect(self.drag_handle_rect)

            # Resize handle (Bottom-Right)
            self.resize_handle_rect = QRect(self.width() - self.handle_size, self.height() - self.handle_size, self.handle_size, self.handle_size)
            painter.drawRect(self.resize_handle_rect)

    def mousePressEvent(self, event):
        if not self.is_in_design_mode:
            # Pass event to child widget if not in design mode
            child_pos = self.widget.mapFrom(self, event.position().toPoint())
            child_event = QtGui.QMouseEvent(event.type(), child_pos, event.button(), event.buttons(), event.modifiers())
            QApplication.sendEvent(self.widget, child_event)
            return

        if event.button() == Qt.LeftButton:
            if self.drag_handle_rect.contains(event.position().toPoint()):
                self.dragging = True
                self.drag_start_pos = event.globalPosition().toPoint()
                self.original_pos = self.pos()
                self.setCursor(Qt.SizeAllCursor)
                event.accept()
            elif self.resize_handle_rect.contains(event.position().toPoint()):
                self.resizing = True
                self.resize_start_pos = event.globalPosition().toPoint()
                self.original_size = self.size()
                self.setCursor(Qt.SizeFDiagCursor)
                event.accept()
            else:
                event.ignore()

    def mouseMoveEvent(self, event):
        if not self.is_in_design_mode:
             child_pos = self.widget.mapFrom(self, event.position().toPoint())
             child_event = QtGui.QMouseEvent(event.type(), child_pos, event.button(), event.buttons(), event.modifiers())
             QApplication.sendEvent(self.widget, child_event)
             return

        if self.dragging and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self.drag_start_pos
            new_pos = self.original_pos + delta
            parent_rect = self.parentWidget().rect() if self.parentWidget() else QRect()
            if not parent_rect.isEmpty():
                 new_pos.setX(max(0, min(new_pos.x(), parent_rect.width() - self.width())))
                 new_pos.setY(max(0, min(new_pos.y(), parent_rect.height() - self.height())))
            self.move(new_pos)
            event.accept()

        elif self.resizing and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self.resize_start_pos
            new_width = max(self.minimumWidth(), self.original_size.width() + delta.x())
            new_height = max(self.minimumHeight(), self.original_size.height() + delta.y())
            parent_rect = self.parentWidget().rect() if self.parentWidget() else QRect()
            if not parent_rect.isEmpty():
                if self.x() + new_width > parent_rect.width():
                    new_width = parent_rect.width() - self.x()
                if self.y() + new_height > parent_rect.height():
                    new_height = parent_rect.height() - self.y()
            self.resize(new_width, new_height)
            event.accept()
        else:
             if self.is_in_design_mode:
                 if self.drag_handle_rect.contains(event.position().toPoint()) or self.resize_handle_rect.contains(event.position().toPoint()):
                     self.setCursor(Qt.SizeAllCursor if self.drag_handle_rect.contains(event.position().toPoint()) else Qt.SizeFDiagCursor)
                 else:
                     self.unsetCursor()
             event.ignore()

    def mouseReleaseEvent(self, event):
        if not self.is_in_design_mode:
            child_pos = self.widget.mapFrom(self, event.position().toPoint())
            child_event = QtGui.QMouseEvent(event.type(), child_pos, event.button(), event.buttons(), event.modifiers())
            QApplication.sendEvent(self.widget, child_event)
            return

        if event.button() == Qt.LeftButton:
            if self.dragging:
                self.dragging = False
                self.unsetCursor()
                event.accept()
            elif self.resizing:
                self.resizing = False
                self.unsetCursor()
                event.accept()
            else:
                event.ignore()
        else:
             event.ignore()

# --- ControlWindow ---
class ControlWindow(QMainWindow):
    translation_error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self.live_translation_popout = None
        self.chat_window = None
        self.source_language = 'auto' # Default source
        self.target_language = 'en' # Default target
        self.tray_icon = None
        self.default_font_size = 20 # Default for live display/viewer initial
        self.default_font_type = "default" # Font category ('default', 'zh', 'ja', 'ko')
        self.translate_with_ai_enabled = False
        self.capture_widget = None # Initialize later
        self.snipping_tool = None # Initialize later
        self.font_size = 16 # Font size for live label in *this* window
        self.translation_worker = None # Holder for the current worker
        self.is_live_capturing = False # State flag for live capture
        self.flask_process = None # To hold the Flask server process if run externally
        self.flask_thread = None # To hold the Flask server thread if run internally

        # Load AI config early
        self.load_ai_api_config()

        # Show intro dialog first
        self.showIntroDialog()

        # Now initialize UI and CaptureWidget
        self.capture_widget = CaptureWidget(control_window=self)
        self.snipping_tool = SnippingTool(self.capture_widget)

        self.initUI() # Initialize main UI elements
        # Theme is applied after initUI in the main execution block

        self.setupGlobalShortcuts()
        self.load_geometry() # Load main window position
        ensure_support_folder() # Ensure support folder exists

        # Connect error signal
        self.translation_error_occurred.connect(self.displayTranslationError)

    def showIntroDialog(self):
        intro_dialog = IntroDialog(self)
        intro_dialog.exec()

    def load_ai_api_config(self):
        global ai_api_config
        positions = load_window_positions()
        if 'ai_api_config' in positions:
            loaded_config = positions['ai_api_config']
            ai_api_config["provider"] = loaded_config.get("provider", None)
            ai_api_config["endpoint"] = loaded_config.get("endpoint", None)
            logging.info(f"Loaded AI API Config: Provider={ai_api_config['provider']}, Endpoint={ai_api_config['endpoint']}")
        else:
            logging.info("No AI API config found in settings file.")

    def initUI(self):
        self.setWindowTitle('Overlay Translate Control')
        flags = Qt.Window | Qt.WindowStaysOnTopHint | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint
        self.setWindowFlags(flags)
        # self.setStyleSheet(...) # REMOVED - Applied globally

        # --- Central Widget and Layout ---
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # --- Capture Controls Group ---
        capture_group = QGroupBox("Capture Controls")
        capture_layout = QHBoxLayout()

        self.capture_btn = self.createButton('Capture (F1)', self.captureScreen, '#4a90e2', '#5aa1f2', '#357abd', 'capture.svg', "Capture selected area and translate")
        self.live_capture_btn = self.createButton('Live (F3)', self.toggleLiveCapture, '#2ecc71', '#3edf81', '#27ae60', 'live.svg', "Toggle continuous live translation")
        self.snip_btn = self.createButton('Snip (F4)', self.activateSnippingTool, '#e67e22', '#f68f32', '#d35400', 'snip.svg', "Select a new area with snipping tool")

        capture_layout.addWidget(self.capture_btn)
        capture_layout.addWidget(self.live_capture_btn)
        capture_layout.addWidget(self.snip_btn)
        capture_group.setLayout(capture_layout)
        main_layout.addWidget(capture_group)

        # --- Live Translation Display (in Control Window) ---
        live_display_group = QGroupBox("Live Translation Preview")
        live_display_layout = QVBoxLayout()

        self.live_translation_label = QLabel("Live translation disabled.", self)
        self.live_translation_label.setWordWrap(True)
        self.live_translation_label.setAlignment(Qt.AlignCenter)
        # Apply style using object name for potential override if needed
        self.live_translation_label.setObjectName("ControlWindowLiveLabel")
        # Base style for the label (will be styled by the global theme)
        self.live_translation_label.setStyleSheet("""
            QLabel#ControlWindowLiveLabel {
                /* Let theme handle background, border, colors */
                border-radius: 10px; /* Keep radius */
                padding: 15px;
                font-size: 16px; /* Default size for preview */
                min-height: 50px; /* Ensure it has some height */
            }
        """)
        self.live_translation_label.setVisible(True)

        # Opacity effect for fade-in
        self.label_opacity_effect = QGraphicsOpacityEffect(self.live_translation_label)
        self.live_translation_label.setGraphicsEffect(self.label_opacity_effect)
        self.label_fade_anim = QPropertyAnimation(self.label_opacity_effect, b"opacity", self)
        self.label_fade_anim.setDuration(400)
        self.label_fade_anim.setStartValue(0.0)
        self.label_fade_anim.setEndValue(1.0)
        self.label_fade_anim.setEasingCurve(QEasingCurve.InOutQuad)

        # Font Size Controls for Live Preview
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("Preview Size:", self))
        self.increase_font_btn = self.createButton('+', self.increaseFontSize, '#9b59b6', '#ab69c6', '#8e44ad', 'zoom_in.svg', "Increase preview font size", fixed_size=QtCore.QSize(40, 40))
        self.decrease_font_btn = self.createButton('-', self.decreaseFontSize, '#e74c3c', '#f75c4c', '#c0392b', 'zoom_out.svg', "Decrease preview font size", fixed_size=QtCore.QSize(40, 40))
        font_layout.addStretch(1)
        font_layout.addWidget(self.decrease_font_btn)
        font_layout.addWidget(self.increase_font_btn)

        live_display_layout.addWidget(self.live_translation_label)
        live_display_layout.addLayout(font_layout)
        live_display_group.setLayout(live_display_layout)
        main_layout.addWidget(live_display_group)

        # --- Settings Group ---
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(10)

        # Click-Through Toggle
        self.toggle_btn = self.createButton('Make Overlay Click-Through (F2)', self.capture_widget.toggleClickThrough, '#f1c40f', '#f3d752', '#c8a20e', 'click.svg', "Toggle if mouse clicks pass through the overlay")
        settings_layout.addWidget(self.toggle_btn)

        # Opacity Slider
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Overlay Opacity:", self))
        self.opacity_slider = QSlider(Qt.Horizontal, self)
        self.opacity_slider.setRange(10, 100) # Range from 10% (MIN_OPACITY) to 100%

        loaded_opacity = 0.8 # Default
        positions = load_window_positions()
        if 'CaptureWidget' in positions:
             loaded_opacity = positions['CaptureWidget'].get('opacity', 0.8)
        self.opacity_slider.setValue(int(loaded_opacity * 100))

        if self.capture_widget:
             self.capture_widget.setWindowOpacity(loaded_opacity)
             self.capture_widget.updateClickThroughState()

        self.opacity_slider.valueChanged.connect(self.adjustCaptureWidgetOpacity)
        opacity_layout.addWidget(self.opacity_slider)
        settings_layout.addLayout(opacity_layout)

        # Translate with AI Toggle
        self.translate_with_ai_toggle = QPushButton('Use AI Translation: OFF', self)
        self.translate_with_ai_toggle.setCheckable(True)
        self.translate_with_ai_toggle.setChecked(self.translate_with_ai_enabled)
        self.update_ai_toggle_style() # Set initial style
        self.translate_with_ai_toggle.toggled.connect(self.toggleTranslateWithAI)
        self.translate_with_ai_toggle.setToolTip("Use configured AI API for translations (requires setup)")
        settings_layout.addWidget(self.translate_with_ai_toggle)

        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)

        # --- Progress Bar ---
        self.translation_progress_bar = QProgressBar(self)
        self.translation_progress_bar.setRange(0, 100)
        self.translation_progress_bar.setValue(0)
        self.translation_progress_bar.setTextVisible(True)
        self.translation_progress_bar.setFormat("OCR/Translate: %p%")
        self.translation_progress_bar.setVisible(False) # Hide initially
        main_layout.addWidget(self.translation_progress_bar)

        # --- Menu Bar ---
        self.setMenuBar(self.createMenuBar())

        # --- Show Capture Widget ---
        if self.capture_widget:
            self.capture_widget.show()
        else:
            logging.error("CaptureWidget not initialized before showing!")
            QMessageBox.critical(self, "Startup Error", "Failed to initialize capture overlay.")

        # --- Live Capture Timer ---
        self.live_capture_timer = QTimer(self)
        self.live_capture_timer.timeout.connect(self.captureScreenForLiveTranslation)
        self.live_capture_timer.setInterval(1200) # Interval in milliseconds

        # --- Tray Icon ---
        self.initTrayIcon()

        # --- Load Initial Settings ---
        positions = load_window_positions() # Reload to ensure theme is considered
        # Font settings
        if 'font_settings' in positions:
            fs = positions['font_settings']
            self.default_font_size = fs.get('size', 20)
            self.default_font_type = fs.get('type', 'default')
            self.capture_widget.default_font_size = self.default_font_size
            self.capture_widget.default_font_type = self.default_font_type
            logging.info(f"Loaded font settings: Size={self.default_font_size}, Type={self.default_font_type}")
        # AI Toggle State
        if 'settings' in positions:
            s = positions['settings']
            self.translate_with_ai_enabled = s.get('translate_with_ai', False)
            self.translate_with_ai_toggle.setChecked(self.translate_with_ai_enabled)
            self.update_ai_toggle_style()
            logging.info(f"Loaded AI toggle state: {self.translate_with_ai_enabled}")
        # Opacity already loaded and applied above

    def startBackgroundAnimation(self):
        # Simple opacity pulse animation for the main window (optional)
        self.bg_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.bg_anim.setDuration(5000) # 5 seconds cycle
        self.bg_anim.setStartValue(0.95)
        self.bg_anim.setKeyValueAt(0.5, 1.0)
        self.bg_anim.setEndValue(0.95)
        self.bg_anim.setLoopCount(-1) # Loop indefinitely
        self.bg_anim.setEasingCurve(QEasingCurve.InOutSine)
        # self.bg_anim.start() # Uncomment to enable

    def createMenuBar(self):
        menu_bar = QtWidgets.QMenuBar(self)
        # Styles handled by global theme application

        # --- File Menu ---
        file_menu = menu_bar.addMenu("&File")
        tray_action = file_menu.addAction("Minimize to Tray")
        tray_action.triggered.connect(self.minimizeToTray)
        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.closeApplication) # Connect to proper close method
        exit_action.setShortcut(QKeySequence.Quit) # Standard shortcut (Ctrl+Q or Cmd+Q)

        # --- Settings Menu ---
        settings_menu = menu_bar.addMenu("&Settings")
        lang_menu = settings_menu.addMenu("Translation Languages")
        src_lang_action = lang_menu.addAction("Set Source Language...")
        src_lang_action.triggered.connect(self.selectSourceLanguage)
        tgt_lang_action = lang_menu.addAction("Set Target Language...")
        tgt_lang_action.triggered.connect(self.selectTargetLanguage)

        font_menu = settings_menu.addMenu("Translation Font")
        font_size_action = font_menu.addAction("Set Default Font Size...")
        font_size_action.triggered.connect(self.setDefaultFontSize)
        font_type_action = font_menu.addAction("Set Default Font Type...")
        font_type_action.triggered.connect(self.setDefaultFontType)

        settings_menu.addSeparator()

        ai_menu = settings_menu.addMenu("AI Configuration")
        config_ai_action = ai_menu.addAction("Configure AI Provider...")
        config_ai_action.triggered.connect(self.configureAIAPI)
        toggle_ai_action = ai_menu.addAction("Toggle AI Translation")
        toggle_ai_action.setCheckable(True)
        toggle_ai_action.setChecked(self.translate_with_ai_enabled)
        toggle_ai_action.triggered.connect(self.translate_with_ai_toggle.toggle) # Link to button's toggle

        settings_menu.addSeparator()
        server_action = settings_menu.addAction("Open Translation Server UI")
        server_action.triggered.connect(self.openServer)

        settings_menu.addSeparator() # Add separator before theme
        theme_action = settings_menu.addAction("Theme Settings...")
        theme_action.triggered.connect(self.openThemeDialog)

        # --- Tools Menu ---
        tools_menu = menu_bar.addMenu("&Tools")
        chat_action = tools_menu.addAction("Open AI Chat")
        chat_action.triggered.connect(self.openChatWindow)
        chat_action.setShortcut(QKeySequence("Ctrl+T")) # Example shortcut

        live_popout_action = tools_menu.addAction("Pop Out Live Translation")
        live_popout_action.triggered.connect(self.popOutLiveTranslation)

        # --- Help Menu ---
        help_menu = menu_bar.addMenu("&Help")
        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self.showAboutDialog)

        # --- MODIFICATION 4: Menu Item Change ---
        # log_action = help_menu.addAction("Open Log File") # REMOVED
        # log_action.triggered.connect(self.openLogFile) # REMOVED
        folder_action = help_menu.addAction("Open Support Folder") # ADDED
        folder_action.triggered.connect(self.openSupportFolder) # ADDED
        # --- END MODIFICATION 4 ---

        return menu_bar

    # --- MODIFICATION 4: Add openSupportFolder method ---
    def openSupportFolder(self):
        """Opens the Support folder in the default file explorer."""
        folder_path = SUPPORT_FOLDER
        logging.info(f"Opening Support Folder: {folder_path}")
        try:
            if not os.path.exists(folder_path):
                logging.warning(f"Support folder does not exist at {folder_path}. Attempting to create.")
                ensure_support_folder()
                if not os.path.exists(folder_path):
                    QMessageBox.warning(self, "Folder Not Found", f"The Support folder could not be found or created at:\n{folder_path}")
                    return

            system = platform.system()
            if system == "Windows":
                # Use os.startfile for better association handling on Windows
                os.startfile(folder_path)
            elif system == "Darwin": # macOS
                subprocess.Popen(["open", folder_path])
            else: # Linux and other Unix-like
                subprocess.Popen(["xdg-open", folder_path])
        except FileNotFoundError:
             QMessageBox.warning(self, "File Explorer Error", f"Could not find the file explorer application to open:\n{folder_path}")
        except Exception as e:
             logging.error(f"Failed to open support folder '{folder_path}': {e}", exc_info=True)
             QMessageBox.warning(self, "Error", f"Could not open the Support folder.\nError: {e}")
    # --- END MODIFICATION 4 ---

    def openThemeDialog(self):
        dialog = ThemeDialog(self)
        dialog.exec()
        # Theme is applied within the dialog's save_and_apply method

    def createButton(self, text, callback, color, hover, pressed, icon_name, tooltip="", fixed_size=None):
        button = QPushButton(text, self)
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", icon_name)
        if os.path.exists(icon_path):
            button.setIcon(QIcon(icon_path))
            button.setIconSize(QtCore.QSize(18, 18)) # Adjust icon size
        else:
            logging.warning(f"Icon not found at {icon_path}, using text label: {text}")

        button.clicked.connect(callback)
        button.setToolTip(tooltip) # Add tooltip

        # Apply specific override styles (these might get overridden by theme if not specific enough)
        # It's better to let the theme handle the base style and only override here if essential.
        # For now, keep it to ensure buttons look distinct, but theme should ideally control this.
        button.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {color}, stop:1 {pressed});
                /* Inherit color, border-radius, padding, font-size, font-weight, border from theme */
                min-height: 35px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {hover}, stop:1 {color});
            }}
            QPushButton:pressed {{
                background: {pressed};
                /* Inherit padding adjustments from theme */
            }}
            QPushButton:disabled {{
                 background: rgba(120, 120, 120, 100);
                 /* Inherit disabled text color from theme */
            }}
        """)

        if fixed_size:
            button.setFixedSize(fixed_size)

        # Add shadow effect (optional)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(1, 1)
        button.setGraphicsEffect(shadow)

        return button

    def update_ai_toggle_style(self):
        """Updates the AI toggle button's style based on its checked state."""
        base_style = """
            QPushButton {{ /* Inherit basic props from global theme */
                min-height: 35px;
            }}
            QPushButton:pressed {{ /* Inherit press effect from global theme */ }}
        """
        if self.translate_with_ai_toggle.isChecked():
            self.translate_with_ai_toggle.setText('Use AI Translation: ON')
            self.translate_with_ai_toggle.setStyleSheet(base_style + """
                QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2ecc71, stop:1 #27ae60); } /* Green gradient */
                QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3edf81, stop:1 #38bf71); }
                QPushButton:pressed { background: #27ae60; }
            """)
        else:
            self.translate_with_ai_toggle.setText('Use AI Translation: OFF')
            self.translate_with_ai_toggle.setStyleSheet(base_style + """
                 QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e74c3c, stop:1 #c0392b); } /* Red gradient */
                 QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f75c4c, stop:1 #d1483b); }
                 QPushButton:pressed { background: #c0392b; }
            """)

    def toggleTranslateWithAI(self, checked):
        logging.debug(f"AI Toggle changed: {checked}")
        if checked:
            if self.is_live_capturing:
                QMessageBox.warning(self, "Live Capture Active", "AI translation is disabled during live capture.")
                self.translate_with_ai_toggle.setChecked(False)
                return
            if not ai_api_config.get("provider"):
                QMessageBox.warning(self, "AI Not Configured", "Please configure an AI API provider first.")
                self.translate_with_ai_toggle.setChecked(False)
                return

        self.translate_with_ai_enabled = checked
        self.update_ai_toggle_style()
        logging.info(f"Translate with AI {'enabled' if checked else 'disabled'}")
        self.saveAppSettings()

    def toggleLiveCapture(self):
        if self.is_live_capturing:
            self.live_capture_timer.stop()
            self.is_live_capturing = False
            self.live_capture_btn.setText('Live (F3)')
            icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "live.svg")
            if os.path.exists(icon_path): self.live_capture_btn.setIcon(QIcon(icon_path))
            self.live_translation_label.setText("Live translation disabled.")
            self.live_capture_btn.setToolTip("Toggle continuous live translation")
            # Restore original button style (or specific 'off' style using theme logic)
            # This just re-applies the 'createButton' specific override for simplicity here
            # Ideally, the theme change would handle this via selectors if needed
            self.live_capture_btn.setStyleSheet(self.createButton(
                 '', lambda:None, '#2ecc71', '#3edf81', '#27ae60', '', tooltip=""
            ).styleSheet())

            if self.translation_worker and self.translation_worker.isRunning():
                self.translation_worker.stop()
            logging.info("Live capture stopped.")
        else:
            if self.translate_with_ai_enabled:
                 QMessageBox.information(self, "AI Disabled", "AI translation is automatically disabled during live capture.")
                 self.translate_with_ai_toggle.setChecked(False)

            if not self.capture_widget or not self.capture_widget.isVisible():
                 QMessageBox.warning(self, "Overlay Hidden", "Please ensure the capture overlay is visible.")
                 return

            self.live_capture_timer.start()
            self.is_live_capturing = True
            self.live_capture_btn.setText('Stop (F3)')
            icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "stop.svg")
            if os.path.exists(icon_path): self.live_capture_btn.setIcon(QIcon(icon_path))
            self.live_translation_label.setText("Live capture active...")
            self.live_capture_btn.setToolTip("Stop continuous live translation")
            self.live_capture_btn.setStyleSheet(self.createButton(
                  '', lambda:None, '#e74c3c', '#f75c4c', '#c0392b', '', tooltip=""
             ).styleSheet()) # Apply 'stop' style override

            logging.info("Live capture started.")

    def captureScreen(self):
        if not self.capture_widget or not self.capture_widget.isVisible():
            QMessageBox.warning(self, "Overlay Hidden", "Please ensure the capture overlay is visible.")
            return

        self.translation_progress_bar.setVisible(True)
        self.translation_progress_bar.setValue(0)
        self.translation_progress_bar.setFormat("Capturing...")
        QApplication.processEvents()

        screenshot = None
        fileName = ""
        try:
            overlay_geometry = self.capture_widget.geometry()
            screen = QApplication.primaryScreen()
            if not screen:
                raise Exception("Could not get primary screen.")

            logging.debug(f"Grabbing screen area (no hide): {overlay_geometry}")
            window_id = getattr(Qt, 'WId', 0)
            screenshot = screen.grabWindow(window_id, overlay_geometry.x(), overlay_geometry.y(), overlay_geometry.width(), overlay_geometry.height())

            if screenshot.isNull():
                raise Exception("Failed to grab screenshot (returned null pixmap).")

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            ensure_support_folder()
            fileName = os.path.join(SUPPORT_FOLDER, f"capture_{timestamp}.png")

            if not screenshot.save(fileName, "PNG", quality=95):
                raise Exception(f"Failed to save screenshot to {fileName}.")

            if not os.path.exists(fileName) or os.path.getsize(fileName) == 0:
                time.sleep(0.1)
                if not os.path.exists(fileName) or os.path.getsize(fileName) == 0:
                    raise Exception(f"Screenshot file is empty or non-existent after saving: {fileName}")

            try:
                with Image.open(fileName) as img:
                    img.verify()
                logging.debug(f"Screenshot verified: {fileName}")
            except Exception as img_err:
                raise Exception(f"Screenshot file validation failed: {img_err}")

            logging.info(f"Screen captured successfully: {fileName}")
            self.capture_widget.current_capture_path = fileName

            self.translation_progress_bar.setFormat("Translating... %p%")
            self.translation_progress_bar.setValue(10)
            self.startTranslationWorker(fileName, live=False)

        except Exception as e:
            logging.error(f"Screen grab failed: {e}", exc_info=True)
            self.translation_progress_bar.setFormat("Capture Failed")
            self.translation_progress_bar.setValue(0)
            QMessageBox.critical(self, "Capture Error", f"Screen capture failed.\n\nError: {e}")

        finally:
            if screenshot:
                del screenshot

    def captureScreenForLiveTranslation(self):
        if not self.capture_widget or not self.capture_widget.isVisible():
            logging.warning("Live capture skipped: Overlay widget not ready.")
            return

        screenshot = None
        tempFile = ""
        try:
            overlay_geometry = self.capture_widget.geometry()
            screen = QApplication.primaryScreen()
            if not screen:
                raise Exception("Could not get primary screen for live capture.")

            logging.debug(f"Grabbing screen area for live (no hide): {overlay_geometry}")
            window_id = getattr(Qt, 'WId', 0)
            screenshot = screen.grabWindow(window_id, overlay_geometry.x(), overlay_geometry.y(), overlay_geometry.width(), overlay_geometry.height())

            if screenshot.isNull():
                raise Exception("Failed to grab live screenshot (null pixmap).")

            # Use support folder for temporary live file too for consistency
            ensure_support_folder()
            tempFile = os.path.join(SUPPORT_FOLDER, 'live_capture.png')

            if not screenshot.save(tempFile, "PNG", quality=-1):
                raise Exception("Failed to save live screenshot.")

            if not os.path.exists(tempFile):
                raise Exception("Live screenshot file does not exist after saving.")

            if self.translation_worker is None or not self.translation_worker.isRunning():
                self.startTranslationWorker(tempFile, live=True)
            else:
                logging.debug("Skipping live translation start: Previous worker still running.")

        except Exception as e:
            error_text = f"Live Capture Error: {e}"
            logging.error(f"Live capture failed: {e}", exc_info=True)
            if self.live_translation_popout and self.live_translation_popout.isVisible():
                self.live_translation_popout.updateTranslation(error_text[:100])
            else:
                self.live_translation_label.setText(error_text[:100])

        finally:
            if screenshot:
                del screenshot

    def startTranslationWorker(self, fileName, live=False):
        if self.translation_worker and self.translation_worker.isRunning():
            logging.warning("Previous translation worker running. Stopping and waiting...")
            self.translation_worker.stop()
            if not self.translation_worker.wait(1500):
                 logging.error("Previous translation worker did not stop in time!")

        use_ai = self.translate_with_ai_enabled and not live
        contrast = self.capture_widget.contrast_factor

        logging.info(f"Starting TranslationWorker (Live: {live}, AI: {use_ai}) for: {os.path.basename(fileName)}")

        if not live:
            self.capture_widget.current_capture_path = fileName
            logging.debug(f"Set capture_widget.current_capture_path = {fileName}")

        self.translation_worker = TranslationWorker(
            fileName, self.source_language, self.target_language,
            self.capture_widget.fonts, use_ai, contrast, live, self
        )
        self.translation_worker.translation_complete.connect(self.handleTranslationResult, Qt.QueuedConnection)
        self.translation_worker.error.connect(self.handleTranslationError, Qt.QueuedConnection)
        self.translation_worker.finished.connect(self.onTranslationWorkerFinished, Qt.QueuedConnection)

        if not live:
             if not self.translation_progress_bar.isVisible():
                 self.translation_progress_bar.setVisible(True)
             self.translation_progress_bar.setFormat("Translating... %p%")
             self.translation_progress_bar.setValue(15)
        else:
             # Initial text for live processing
             processing_text = "Processing..."
             if self.live_translation_popout and self.live_translation_popout.isVisible():
                 self.live_translation_popout.updateTranslation(processing_text)
             else:
                 self.live_translation_label.setText(processing_text)
                 # Don't fade *this* update, wait for actual result fade

        self.translation_worker.start()

    def handleTranslationResult(self, result):
        """Handles the dictionary emitted by translation_complete."""
        if not isinstance(result, dict):
            logging.error(f"Received invalid result type: {type(result)}")
            self.handleTranslationError("Internal error: Invalid result format.")
            return

        is_live = result.get('live', False)
        error_message = result.get('error_message', '')
        translated_text = result.get('translated_text', '')
        processed_file_name = result.get('file_name', '') # Path to the input image for the worker

        logging.info(f"Handling translation result (Live: {is_live}, File: {os.path.basename(processed_file_name)})")
        logging.debug(f"Result Data: Error='{error_message}', Text='{translated_text[:50]}...'")

        if error_message:
            logging.warning(f"Handling result with error message: {error_message}")
            self.handleTranslationError(f"Processing Error: {error_message}")
            return # Stop processing this result

        # --- Success ---
        if is_live:
            # Update live display (popout or internal label)
            compact_text = translated_text.replace('\n', ' ').strip()
            if not compact_text: compact_text = "(No text detected)"
            logging.debug(f"Updating live display with: '{compact_text}'")

            target_label = None
            target_opacity_effect = None
            target_fade_anim = None

            if self.live_translation_popout and self.live_translation_popout.isVisible():
                # --- Update Pop-out Window ---
                target_label = self.live_translation_popout.translation_label
                target_opacity_effect = self.live_translation_popout.label_opacity_effect
                target_fade_anim = self.live_translation_popout.label_fade_anim
                # Update popout text and font directly
                self.live_translation_popout.updateTranslation(compact_text)

            else:
                # --- Update Internal Label ---
                target_label = self.live_translation_label
                target_opacity_effect = self.label_opacity_effect
                target_fade_anim = self.label_fade_anim
                # Update text and font directly before fading
                target_label.setText(compact_text)
                target_label.setFont(choose_font_for_text(compact_text, font_size=self.font_size)) # Update font too

            # --- Apply Fade Animation (Common logic) ---
            if target_label and target_fade_anim and target_opacity_effect:
                target_fade_anim.stop()
                target_opacity_effect.setOpacity(0.0)
                target_fade_anim.start()
            elif target_label: # Fallback
                 target_label.setGraphicsEffect(None)
                 target_label.setVisible(True)
            # --- END Fade Animation Logic ---

        else:
            # Handle non-live result (display in viewer)
            logging.info("Processing non-live result for viewer.")
            if self.translation_progress_bar.isVisible():
                 self.translation_progress_bar.setValue(100)
                 self.translation_progress_bar.setFormat("Complete!")

            # --- MODIFICATION 2: Save Metadata ---
            try:
                original_image_path = self.capture_widget.current_capture_path
                if original_image_path and os.path.exists(original_image_path):
                    # Create corresponding .txt filename
                    txt_filename = os.path.splitext(os.path.basename(original_image_path))[0] + ".txt"
                    txt_filepath = os.path.join(SUPPORT_FOLDER, txt_filename)

                    # Get data from result
                    timestamp_str = result.get('timestamp', datetime.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
                    original_text = result.get('original_text', 'N/A')
                    translated_text_final = result.get('translated_text', 'N/A')

                    # Prepare content
                    metadata_content = (
                        f"Timestamp: {timestamp_str}\n"
                        f"Original File: {os.path.basename(original_image_path)}\n"
                        f"Source Language: {self.source_language}\n"
                        f"Target Language: {self.target_language}\n"
                        f"AI Translation Used: {'Yes' if self.translate_with_ai_enabled else 'No'}\n"
                        f"---------------------\n"
                        f"Original Text:\n"
                        f"---------------------\n"
                        f"{original_text}\n"
                        f"---------------------\n"
                        f"Translated Text:\n"
                        f"---------------------\n"
                        f"{translated_text_final}\n"
                    )

                    # Write to file
                    with open(txt_filepath, 'w', encoding='utf-8') as f:
                        f.write(metadata_content)
                    logging.info(f"Saved capture metadata to: {txt_filepath}")
                else:
                    logging.warning(f"Could not save metadata: Original image path invalid or missing ('{original_image_path}')")
            except Exception as meta_err:
                logging.error(f"Failed to save metadata text file: {meta_err}", exc_info=True)
            # --- END MODIFICATION 2 ---

            if self.capture_widget:
                 viewer_file_path = self.capture_widget.current_capture_path # Use the path stored in capture widget
                 logging.debug(f"Calling capture_widget.displayTranslatedImage with path: {viewer_file_path}")
                 if not viewer_file_path or not os.path.exists(viewer_file_path):
                      logging.error(f"Viewer Error: Processed file path '{viewer_file_path}' is invalid.")
                      QMessageBox.critical(self, "Viewer Error", "Cannot display result: Invalid image path.")
                 else:
                     self.capture_widget.displayTranslatedImage(result, viewer_file_path, self.target_language) # Pass target language
            else:
                 logging.error("Cannot display translated image: CaptureWidget is None.")
                 QMessageBox.critical(self, "Error", "Cannot display result, capture overlay not available.")

            if self.translation_progress_bar.isVisible():
                 QTimer.singleShot(2000, lambda: self.translation_progress_bar.setVisible(False))


    def handleTranslationError(self, error_message):
        """Handles errors emitted from the TranslationWorker."""
        logging.error(f"Translation Worker Error: {error_message}")
        self.translation_error_occurred.emit(error_message) # Emit signal for central handling


    def displayTranslationError(self, error_message):
        """Slot to display translation errors centrally."""
        is_currently_live = self.is_live_capturing

        if is_currently_live:
             error_text = f"Error: {error_message}"
             if self.live_translation_popout and self.live_translation_popout.isVisible():
                 self.live_translation_popout.updateTranslation(error_text[:100])
             else:
                 self.live_translation_label.setText(error_text[:100])
        else:
             if self.translation_progress_bar.isVisible():
                 self.translation_progress_bar.setFormat("Error")
                 self.translation_progress_bar.setValue(0)
             QMessageBox.warning(self, "Translation Error", f"An error occurred:\n\n{error_message}")
             if self.translation_progress_bar.isVisible():
                 QTimer.singleShot(3000, lambda: self.translation_progress_bar.setVisible(False))


    def onTranslationWorkerFinished(self):
        """Slot called when the worker thread finishes execution."""
        logging.debug("TranslationWorker thread finished.")
        if not self.is_live_capturing and self.translation_progress_bar.isVisible():
             if self.translation_progress_bar.value() < 100 or "Error" in self.translation_progress_bar.format():
                 QTimer.singleShot(2000, lambda: self.translation_progress_bar.setVisible(False))

        self.translation_worker = None


    def initTrayIcon(self):
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.png") # Ensure icon exists
        if not os.path.exists(icon_path):
             logging.error(f"Tray icon not found at {icon_path}. Tray functionality disabled.")
             return

        self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self)
        self.tray_icon.setToolTip("Overlay Translate")

        tray_menu = QMenu(self)

        restore_action = tray_menu.addAction("Show Controls")
        restore_action.triggered.connect(self.restoreFromTray)
        capture_action = tray_menu.addAction("Capture (F1)")
        capture_action.triggered.connect(self.captureScreen)
        snip_action = tray_menu.addAction("Snip (F4)")
        snip_action.triggered.connect(self.activateSnippingTool)
        tray_menu.addSeparator()
        exit_action = tray_menu.addAction("Exit")
        exit_action.triggered.connect(self.closeApplication)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.trayIconActivated)
        self.tray_icon.show()
        logging.info("System tray icon initialized.")

    def trayIconActivated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
             self.restoreFromTray()

    def minimizeToTray(self):
        self.hide()
        if self.capture_widget:
            self.capture_widget.hide()
        if self.live_translation_popout and self.live_translation_popout.isVisible():
            self.live_translation_popout.hide()

        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                "Overlay Translate",
                "Minimized to tray. Click icon to restore.",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
        logging.info("Application minimized to tray.")

    def restoreFromTray(self):
        self.show()
        if self.capture_widget:
             self.capture_widget.show()
        if self.live_translation_popout and not self.live_translation_popout.isVisible():
             # Check if it needs to be shown based on whether it was popped out before minimizing
             # Maybe needs a flag or check if self.live_translation_popout is not None
             if self.live_translation_popout: # If instance exists, show it
                self.live_translation_popout.show()


        self.raise_()
        self.activateWindow()
        logging.info("Application restored from tray.")


    def closeApplication(self):
        logging.info("Close application requested.")
        # --- Existing cleanup logic ---
        if self.is_live_capturing:
            self.live_capture_timer.stop()
            logging.debug("Stopped live capture timer.")
        if self.translation_worker and self.translation_worker.isRunning():
            logging.debug("Stopping active translation worker...")
            self.translation_worker.stop()
            # Give the worker a bit more time to finish writing potentially
            self.translation_worker.wait(1500)
            if self.translation_worker.isRunning():
                logging.warning("Translation worker did not stop gracefully.")
        if self.chat_window and self.chat_window.isVisible():
            logging.debug("Closing chat window...")
            self.chat_window.close() # Triggers its save_geometry via closeEvent
        if self.live_translation_popout and self.live_translation_popout.isVisible():
            logging.debug("Closing live translation popout...")
            self.live_translation_popout.close() # Triggers its save_geometry via closeEvent

        # --- IMPORTANT: Close Capture Widget LAST before final save ---
        # Capture widget geometry/opacity needs to be read before it's closed
        capture_widget_state = {}
        if self.capture_widget:
            logging.debug("Reading capture widget state before closing...")
            capture_widget_state = {
                'x': self.capture_widget.x(),
                'y': self.capture_widget.y(),
                'width': self.capture_widget.width(),
                'height': self.capture_widget.height(),
                'opacity': self.capture_widget.windowOpacity()
            }
            logging.debug("Cleaning up and closing capture widget...")
            self.capture_widget.cleanup() # Shuts down Flask, cleans temp files
            self.capture_widget.close() # Triggers its closeEvent

        if self.tray_icon:
            self.tray_icon.hide()
            logging.debug("Hid tray icon.")
        # --- End Existing cleanup ---

        # --- Centralized Save on Exit ---
        logging.info("Gathering final state and saving settings...")
        try:
            # Load positions only, don't reprocess theme
            final_positions = load_window_positions(process_theme=False) # <--- Set process_theme=False
            # ... (rest of the state gathering) ...
            # Theme (Use the current global theme which is already correct)
            final_positions['theme'] = current_theme
            save_window_positions(final_positions)

        except Exception as save_err:
            logging.error(f"Error during final save operation: {save_err}", exc_info=True)
            # Optionally notify user non-blockingly if possible
            if self.tray_icon and self.tray_icon.isVisible():
                 self.tray_icon.showMessage("Save Error", "Failed to save settings on exit.", QSystemTrayIcon.MessageIcon.Warning, 3000)

        # --- Shutdown logging --- (Keep this before folder manipulation)
        logging.info("Shutting down logging handlers...")
        logger_instance = logging.getLogger()
        handlers = logger_instance.handlers[:] # Iterate over a copy
        for handler in handlers:
            try:
                if isinstance(handler, logging.FileHandler): # Be specific if needed
                    handler.close()
                    logger_instance.removeHandler(handler)
                    logging.debug(f"Closed and removed handler: {handler.name if hasattr(handler,'name') else handler}")
            except Exception as log_close_err:
                print(f"Error closing/removing log handler: {log_close_err}") # Use print as logger might be closed

        # --- Support Folder Cleanup Options --- (Keep as is)
        if os.path.exists(SUPPORT_FOLDER):
            # Now it's safe to show the dialog and potentially delete the folder
            print(f"Prompting user for Support folder cleanup options for: {SUPPORT_FOLDER}") # Use print

            msgBox = QMessageBox(self)
            # ... (Rest of the QMessageBox setup and logic remains the same) ...
            msgBox.setWindowTitle("Clean Up Support Folder?")
            msgBox.setText(f"The Support folder contains logs, captures, and metadata:\n\n{SUPPORT_FOLDER}\n\nWhat would you like to do?")
            msgBox.setIcon(QMessageBox.Icon.Question)

            zipDeleteButton = msgBox.addButton("Zip & Delete", QMessageBox.ButtonRole.ActionRole)
            deleteButton = msgBox.addButton("Delete Folder", QMessageBox.ButtonRole.DestructiveRole)
            keepButton = msgBox.addButton("Just Close", QMessageBox.ButtonRole.AcceptRole) # Changed to AcceptRole

            msgBox.setDefaultButton(keepButton) # Default to keeping the folder
            msgBox.exec()
            clickedBtn = msgBox.clickedButton()

            # --- Zip / Delete / Keep logic (no changes needed here) ---
            if clickedBtn == zipDeleteButton:
                print("User chose to Zip and Delete the Support folder.") # Use print
                zip_success = False
                zip_filename = ""
                try:
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    zip_filename = os.path.join(os.path.expanduser("~"), "Desktop", f"OverlayTranslate_Support_{timestamp}.zip")
                    print(f"Creating zip archive: {zip_filename}")
                    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(SUPPORT_FOLDER):
                            relative_root = os.path.relpath(root, SUPPORT_FOLDER)
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.join(relative_root, file)
                                if os.path.abspath(file_path) != os.path.abspath(zip_filename):
                                    zipf.write(file_path, arcname)
                    zip_success = True
                    print(f"Successfully created zip archive: {zip_filename}")
                    QMessageBox.information(self, "Zip Created", f"Support folder archived to:\n{zip_filename}")
                except Exception as e:
                    print(f"ERROR: Failed to create zip archive of {SUPPORT_FOLDER}: {e}")
                    QMessageBox.critical(self, "Zip Error", f"Could not create zip archive.\nError: {e}\n\nThe Support folder will NOT be deleted.")

                if zip_success:
                    print(f"Attempting to delete original Support folder: {SUPPORT_FOLDER}")
                    try:
                        shutil.rmtree(SUPPORT_FOLDER, ignore_errors=False)
                        print(f"Support folder deleted successfully after zipping.")
                    except Exception as e:
                        print(f"ERROR: Failed to delete Support folder {SUPPORT_FOLDER} after zipping: {e}")
                        QMessageBox.warning(self, "Cleanup Error", f"Could not delete the original Support folder after zipping:\n{e}")

            elif clickedBtn == deleteButton:
                print(f"User chose to Delete the Support folder: {SUPPORT_FOLDER}")
                try:
                    shutil.rmtree(SUPPORT_FOLDER, ignore_errors=False)
                    print(f"Support folder deleted successfully.")
                    QMessageBox.information(self, "Folder Deleted", "Support folder has been deleted.")
                except Exception as e:
                    print(f"ERROR: Failed to delete Support folder {SUPPORT_FOLDER}: {e}")
                    QMessageBox.warning(self, "Cleanup Error", f"Could not delete the Support folder:\n{e}")

            elif clickedBtn == keepButton:
                print("User chose to keep the Support folder.")

            else:
                 # This case handles closing the dialog without choosing an action
                 print("Support folder cleanup dialog closed or cancelled. Folder kept.")

        else:
            print("Support folder does not exist, skipping cleanup prompt.") # Use print

        print("Exiting application.") # Use print
        QApplication.quit()

    def load_geometry(self):
        positions = load_window_positions()
        if 'ControlWindow' in positions:
            try:
                geometry = positions['ControlWindow']
                if all(k in geometry for k in ('x', 'y', 'width', 'height')):
                    self.setGeometry(int(geometry['x']), int(geometry['y']), int(geometry['width']), int(geometry['height']))
                    logging.debug(f"Loaded ControlWindow geometry: {geometry}")
                else:
                    logging.warning("ControlWindow geometry incomplete. Using default.")
                    self.resize(500, 650)
            except (ValueError, TypeError) as e:
                 logging.error(f"Error loading ControlWindow geometry: {e}. Using default.")
                 self.resize(500, 650)
        else:
            self.resize(500, 650)

    def save_geometry(self):
#        positions = load_window_positions() # Load existing settings
        # Update only the relevant geometry part
#        positions['ControlWindow'] = {
#            'x': self.x(), 'y': self.y(),
#            'width': self.width(), 'height': self.height()
#        }
        # Call the main save function which includes the current theme
#        save_window_positions(positions)
        logging.debug("ControlWindow.save_geometry called (no immediate save).")
        pass

    def saveAppSettings(self):
#        positions = load_window_positions() # Load existing
#        if 'settings' not in positions:
#            positions['settings'] = {}
#        positions['settings']['translate_with_ai'] = self.translate_with_ai_enabled
#        # Call main save function
#        save_window_positions(positions)
#        logging.debug("Saved application settings.")
        logging.debug("ControlWindow.saveAppSettings called (no immediate save).")
        pass
    def closeEvent(self, event):
        # Minimize to tray instead of closing by default
        event.ignore()
        self.minimizeToTray()

    def activateSnippingTool(self):
        if not self.snipping_tool:
             logging.error("Snipping tool not initialized.")
             return
        if self.capture_widget:
            self.capture_widget.hide()
        self.snipping_tool.show()
        logging.debug("Activated snipping tool.")

    def openChatWindow(self):
        logging.debug("Request to open ChatWindow")
        if not ai_api_config.get("provider"):
            QMessageBox.warning(self, "AI Not Configured", "AI Chat requires configuration.")
            return

        if self.chat_window is None or not self.chat_window.isVisible():
            try:
                self.chat_window = ChatWindow(parent=self)
                positions = load_window_positions()
                if 'ChatWindow' in positions:
                    try:
                        geo = positions['ChatWindow']
                        if all(k in geo for k in ('x', 'y', 'width', 'height')):
                             self.chat_window.setGeometry(geo['x'], geo['y'], geo['width'], geo['height'])
                    except Exception as e:
                        logging.error(f"Failed to load ChatWindow geometry: {e}")
                self.chat_window.show()
                logging.debug("ChatWindow shown.")
            except Exception as e:
                logging.error(f"Failed to create or show ChatWindow: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Could not open AI Chat window:\n{e}")
        else:
            self.chat_window.raise_()
            self.chat_window.activateWindow()
            logging.debug("ChatWindow already open, activated.")

    def increaseFontSize(self):
        self.font_size = min(self.font_size + 2, 36)
        # Use theme-aware update if possible, otherwise simple stylesheet update
        self.live_translation_label.setStyleSheet(f"QLabel#ControlWindowLiveLabel {{ font-size: {self.font_size}px; /* Other styles from theme */ }}") # Example
        logging.debug(f"Live preview font size increased to {self.font_size}px")

    def decreaseFontSize(self):
        self.font_size = max(self.font_size - 2, 10)
        self.live_translation_label.setStyleSheet(f"QLabel#ControlWindowLiveLabel {{ font-size: {self.font_size}px; /* Other styles from theme */ }}") # Example
        logging.debug(f"Live preview font size decreased to {self.font_size}px")

    def popOutLiveTranslation(self):
        if self.live_translation_popout is None or not self.live_translation_popout.isVisible():
            logging.debug("Popping out live translation.")
            self.live_translation_popout = LiveTranslationWindow(self)
            current_text = self.live_translation_label.text()
            if current_text in ["Live translation disabled.", "Live capture active...", "Processing..."]:
                 self.live_translation_popout.updateTranslation("Waiting for live data...")
            else:
                 self.live_translation_popout.updateTranslation(current_text)
            self.live_translation_popout.show()
            self.live_translation_label.setText("Live view popped out.")
        else:
            logging.debug("Closing live translation popout.")
            self.live_translation_popout.close()
            self.live_translation_popout = None
            if self.is_live_capturing:
                 self.live_translation_label.setText("Live capture active...")
            else:
                 self.live_translation_label.setText("Live translation disabled.")

    def configureAIAPI(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Configure AI API Provider")
        dialog.setModal(True)
        # dialog.setStyleSheet(...) # Inherits global style
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        api_group = QGroupBox("Select AI Provider")
        api_layout = QVBoxLayout()
        api_layout.setSpacing(10)

        self.no_api_checkbox = QCheckBox("None (Disable AI Features)")
        self.no_api_checkbox.setChecked(ai_api_config["provider"] is None)
        api_layout.addWidget(self.no_api_checkbox)
        api_layout.addWidget(QLabel("------------------------------------"))

        self.openai_checkbox = QCheckBox("OpenAI (api.openai.com)")
        self.openai_checkbox.setChecked(ai_api_config["provider"] == "OpenAI")
        openai_key_layout = QHBoxLayout()
        openai_key_layout.addWidget(QLabel("API Key:"))
        self.openai_key_input = QLineEdit()
        self.openai_key_input.setEchoMode(QLineEdit.Password)
        self.openai_key_input.setPlaceholderText("Enter OpenAI API Key")
        try:
             key = keyring.get_password("OverlayTranslate", "OpenAI")
             if key: self.openai_key_input.setText(key)
        except Exception as e: logging.warning(f"Could not get OpenAI key from keyring: {e}")
        openai_key_layout.addWidget(self.openai_key_input)

        self.ollama_checkbox = QCheckBox("Ollama (Local)")
        self.ollama_checkbox.setChecked(ai_api_config["provider"] == "Ollama")
        ollama_endpoint_layout = QHBoxLayout()
        ollama_endpoint_layout.addWidget(QLabel("Endpoint:"))
        default_ollama_endpoint = "http://localhost:11434/api/chat"
        current_ollama_endpoint = ai_api_config["endpoint"] if ai_api_config["provider"] == "Ollama" else default_ollama_endpoint
        self.ollama_endpoint_input = QLineEdit(current_ollama_endpoint)
        self.ollama_endpoint_input.setPlaceholderText(default_ollama_endpoint)
        ollama_endpoint_layout.addWidget(self.ollama_endpoint_input)

        self.lmstudio_checkbox = QCheckBox("LM Studio (Local)")
        self.lmstudio_checkbox.setChecked(ai_api_config["provider"] == "LM Studio")
        lmstudio_key_layout = QHBoxLayout()
        lmstudio_key_layout.addWidget(QLabel("API Key (Optional):"))
        self.lmstudio_key_input = QLineEdit()
        self.lmstudio_key_input.setEchoMode(QLineEdit.Password)
        self.lmstudio_key_input.setPlaceholderText("Enter LM Studio API Key (if needed)")
        try:
             key = keyring.get_password("OverlayTranslate", "LM Studio")
             if key: self.lmstudio_key_input.setText(key)
        except Exception as e: logging.warning(f"Could not get LM Studio key from keyring: {e}")
        lmstudio_key_layout.addWidget(self.lmstudio_key_input)

        api_layout.addWidget(self.openai_checkbox)
        api_layout.addLayout(openai_key_layout)
        api_layout.addWidget(QLabel("------------------------------------"))
        api_layout.addWidget(self.ollama_checkbox)
        api_layout.addLayout(ollama_endpoint_layout)
        api_layout.addWidget(QLabel("------------------------------------"))
        api_layout.addWidget(self.lmstudio_checkbox)
        api_layout.addLayout(lmstudio_key_layout)
        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        self.checkbox_group = QtWidgets.QButtonGroup(dialog)
        self.checkbox_group.addButton(self.no_api_checkbox, 0)
        self.checkbox_group.addButton(self.openai_checkbox, 1)
        self.checkbox_group.addButton(self.ollama_checkbox, 2)
        self.checkbox_group.addButton(self.lmstudio_checkbox, 3)

        button_box = QHBoxLayout()
        save_btn = QPushButton("Save Configuration")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(lambda: self.save_api_settings(dialog))
        cancel_btn.clicked.connect(dialog.reject)
        button_box.addStretch(1)
        button_box.addWidget(cancel_btn)
        button_box.addWidget(save_btn)
        layout.addLayout(button_box)

        dialog.setLayout(layout)
        dialog.exec()

    def save_api_settings(self, dialog):
        global ai_api_config
        selected_id = self.checkbox_group.checkedId()
        provider_name = "None"
        success = False
        error_msg = ""

        try:
            if selected_id == 0: # None
                ai_api_config.update({"provider": None, "endpoint": None})
                for provider in ["OpenAI", "Ollama", "LM Studio"]:
                     try: keyring.delete_password("OverlayTranslate", provider)
                     except Exception: pass
                provider_name = "None"
                success = True
            elif selected_id == 1: # OpenAI
                api_key = self.openai_key_input.text().strip()
                if not api_key: raise ValueError("OpenAI requires an API Key.")
                endpoint = "https://api.openai.com/v1/chat/completions"
                keyring.set_password("OverlayTranslate", "OpenAI", api_key)
                ai_api_config.update({"provider": "OpenAI", "endpoint": endpoint})
                provider_name = "OpenAI"
                success = True
            elif selected_id == 2: # Ollama
                endpoint = self.ollama_endpoint_input.text().strip()
                if not endpoint: raise ValueError("Ollama requires an Endpoint URL.")
                if not (endpoint.startswith("http://") or endpoint.startswith("https://")) or not ('/api/chat' in endpoint or '/api/generate' in endpoint):
                     raise ValueError("Invalid Ollama endpoint format. Use http://host:port/api/chat or /api/generate")
                try: keyring.delete_password("OverlayTranslate", "Ollama")
                except Exception: pass
                ai_api_config.update({"provider": "Ollama", "endpoint": endpoint})
                provider_name = "Ollama"
                success = True
            elif selected_id == 3: # LM Studio
                api_key = self.lmstudio_key_input.text().strip()
                endpoint = "http://localhost:1234/v1/chat/completions"
                if api_key: keyring.set_password("OverlayTranslate", "LM Studio", api_key)
                else:
                    try: keyring.delete_password("OverlayTranslate", "LM Studio")
                    except Exception: pass
                ai_api_config.update({"provider": "LM Studio", "endpoint": endpoint})
                provider_name = "LM Studio"
                success = True
            else: raise ValueError("No provider selected.")
        except ValueError as ve:
             error_msg = str(ve)
             QMessageBox.warning(dialog, "Configuration Error", error_msg)
        except Exception as e:
             error_msg = f"An unexpected error occurred: {e}"
             logging.error(f"Error saving API settings: {e}", exc_info=True)
             QMessageBox.critical(dialog, "Error", error_msg)

        if success:
            logging.info(f"AI API configured: Provider={provider_name}, Endpoint={ai_api_config.get('endpoint')}")
            QMessageBox.information(dialog, "Configuration Saved", f"AI Provider set to: {provider_name}")
            self.saveAPISettingsToFile() # Persist changes
            if ai_api_config["provider"] is None and self.translate_with_ai_enabled:
                self.translate_with_ai_toggle.setChecked(False)
            dialog.accept()

    def saveAPISettingsToFile(self):
#        positions = load_window_positions() # Load existing
#        positions['ai_api_config'] = {
#            "provider": ai_api_config.get("provider"),
#            "endpoint": ai_api_config.get("endpoint")
#        }
#        # Call main save function
#        save_window_positions(positions)
        logging.debug("ControlWindow.saveAPISettingsToFile called (no immediate save).")
    pass

    def setDefaultFontSize(self):
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Set Default Font Size")
        dialog.setLabelText("Enter default font size for translated text overlay (e.g., 10-72):")
        dialog.setInputMode(QInputDialog.InputMode.IntInput)
        dialog.setIntValue(self.default_font_size)
        dialog.setIntMinimum(8)
        dialog.setIntMaximum(72)
        # dialog.setStyleSheet(...) # Inherits global style
        ok = dialog.exec()
        if ok:
            size = dialog.intValue()
            self.default_font_size = size
            if self.capture_widget:
                self.capture_widget.default_font_size = size
            logging.info(f"Default translation font size set to: {size}")
            self.saveFontSettings()
        else:
            logging.debug("Font size selection cancelled.")

    def setDefaultFontType(self):
        font_options = {
            "Roboto (Default Latin)": "default",
            "Arial (Fallback)": "Arial",
            "Microsoft YaHei (Chinese)": "zh",
            "MS Gothic (Japanese)": "ja",
            "Malgun Gothic (Korean)": "ko"
        }
        current_key = next((key for key, value in font_options.items() if value == self.default_font_type), "Roboto (Default Latin)")

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Set Default Font Category")
        dialog.setLabelText("Choose default font category for translated text:")
        dialog.setComboBoxItems(list(font_options.keys()))
        dialog.setTextValue(current_key)
        # dialog.setStyleSheet(...) # Inherits global style
        ok = dialog.exec()
        if ok:
            font_display_name = dialog.textValue()
            if font_display_name in font_options:
                self.default_font_type = font_options[font_display_name]
                if self.capture_widget:
                    self.capture_widget.default_font_type = self.default_font_type
                logging.info(f"Default translation font type set to: {self.default_font_type} ({font_display_name})")
                self.saveFontSettings()
            else:
                 logging.warning(f"Invalid font type selected: {font_display_name}")
        else:
             logging.debug("Font type selection cancelled.")

    def saveFontSettings(self):
#        positions = load_window_positions() # Load existing
#        positions['font_settings'] = {
#            'size': self.default_font_size,
#            'type': self.default_font_type
#        }
#        # Call main save function
#        save_window_positions(positions)
#        logging.debug("Saved font settings.")
        logging.debug("ControlWindow.saveFontSettings called (no immediate save).")
    pass

    def adjustCaptureWidgetOpacity(self, value):
        if self.capture_widget:
            opacity = max(MIN_OPACITY, value / 100.0)
            self.capture_widget.setWindowOpacity(opacity)
            self.capture_widget.updateClickThroughState()

            positions = load_window_positions()
            if 'CaptureWidget' not in positions: positions['CaptureWidget'] = {}
            positions['CaptureWidget']['opacity'] = opacity
            save_window_positions(positions)
            logging.debug(f"Capture widget opacity set to {opacity:.2f}")

    def selectSourceLanguage(self):
        languages = {
             "Auto Detect": "auto", "English": "en", "Spanish": "es", "French": "fr",
             "German": "de", "Italian": "it", "Portuguese": "pt", "Russian": "ru",
             "Chinese (Simplified)": "ch", # Paddle uses 'ch'
             "Japanese": "ja", "Korean": "ko"
         }
        current_name = next((name for name, code in languages.items() if code == self.source_language), "Auto Detect")
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Select Source Language")
        dialog.setLabelText("Choose source language for OCR and Translation:")
        dialog.setComboBoxItems(list(languages.keys()))
        dialog.setTextValue(current_name)
        # dialog.setStyleSheet(...) # Inherits global style
        ok = dialog.exec()
        if ok:
            selected_name = dialog.textValue()
            if selected_name in languages:
                new_lang_code = languages[selected_name]
                if self.source_language != new_lang_code:
                    self.source_language = new_lang_code
                    logging.info(f"Source language set to: {self.source_language} ({selected_name})")
                    if self.source_language != 'auto':
                        QMessageBox.information(self, "Updating OCR", f"Updating OCR engine for {selected_name}...")
                        QApplication.processEvents()
                        initialize_paddle_ocr(self.source_language) # Re-initialize OCR
                        QMessageBox.information(self, "Update Complete", "OCR engine updated.")
                    else:
                        # If switching back to Auto, re-initialize with 'en' as default
                        # Or maintain a separate 'base' OCR instance? Keep it simple: re-init 'en'.
                        QMessageBox.information(self, "Updating OCR", "Switching OCR to base language detection mode (English base)...")
                        QApplication.processEvents()
                        initialize_paddle_ocr('en') # Re-initialize OCR for 'auto'
                        QMessageBox.information(self, "Update Complete", "OCR engine updated for auto-detection.")


            else:
                 logging.warning(f"Invalid source language selected: {selected_name}")
        else:
             logging.debug("Source language selection cancelled.")

    def selectTargetLanguage(self):
        languages = {
            "English": "en", "Spanish": "es", "French": "fr", "German": "de",
            "Italian": "it", "Portuguese": "pt", "Russian": "ru",
            "Chinese (Simplified)": "zh",
            "Japanese": "ja", "Korean": "ko"
        }
        current_name = next((name for name, code in languages.items() if code == self.target_language), "English")
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Select Target Language")
        dialog.setLabelText("Choose target language for Translation:")
        dialog.setComboBoxItems(list(languages.keys()))
        dialog.setTextValue(current_name)
        # dialog.setStyleSheet(...) # Inherits global style
        ok = dialog.exec()
        if ok:
            selected_name = dialog.textValue()
            if selected_name in languages:
                self.target_language = languages[selected_name]
                logging.info(f"Target language set to: {self.target_language} ({selected_name})")
                # Update target language in capture widget if needed (though not strictly necessary currently)
                if self.capture_widget:
                    self.capture_widget.target_language = self.target_language
            else:
                 logging.warning(f"Invalid target language selected: {selected_name}")
        else:
             logging.debug("Target language selection cancelled.")

    def openServer(self):
        url = "http://127.0.0.1:5000"
        logging.info(f"Opening web browser to: {url}")
        try:
            webbrowser.open(url)
        except Exception as e:
            logging.error(f"Failed to open web browser: {e}")
            QMessageBox.warning(self, "Error", f"Could not open web browser.\nPlease manually navigate to {url}")

    def setupGlobalShortcuts(self):
        try:
            if self.capture_widget:
                 QShortcut(QKeySequence("F1"), self, self.captureScreen)
                 QShortcut(QKeySequence("F2"), self, self.capture_widget.toggleClickThrough)
                 QShortcut(QKeySequence("F3"), self, self.toggleLiveCapture)
                 QShortcut(QKeySequence("F4"), self, self.activateSnippingTool)
                 logging.info("Global shortcuts (F1, F2, F3, F4) registered.")
            else:
                 logging.error("Failed to register F2 shortcut: CaptureWidget not initialized.")
                 QShortcut(QKeySequence("F1"), self, self.captureScreen)
                 QShortcut(QKeySequence("F3"), self, self.toggleLiveCapture)
                 QShortcut(QKeySequence("F4"), self, self.activateSnippingTool)
                 logging.info("Global shortcuts (F1, F3, F4) registered.")
        except Exception as e:
            logging.error(f"Failed to register global shortcuts: {e}")
            QMessageBox.warning(self, "Shortcut Error", "Could not register global hotkeys (F1-F4).")

    def showAboutDialog(self):
         about_text = """
         <b>Overlay Translate</b> - Version 1.2.1
         <p>Seamless screen capture and translation.</p>
         <p>Features:</p>
         <ul>
             <li>Screen Region Capture & Snip Tool</li>
             <li>Live Translation Mode</li>
             <li>Offline Translation (via Argos Translate server)</li>
             <li>AI Translation (OpenAI, Ollama, LM Studio)</li>
             <li>AI Chat Interface</li>
             <li>Customizable Overlay & Theme</li>
             <li>Support Folder with Logs & Metadata</li>
         </ul>
         <p>Powered by PaddleOCR, Argos Translate, and various AI APIs.</p>
         <br/>
         <p>(c) 2024 - Your Name/Organization</p>
         """
         QMessageBox.about(self, "About Overlay Translate", about_text)

    def openLogFile(self): # Kept for reference, but not used in menu
        log_path = LOG_FILE_PATH
        try:
            if platform.system() == "Windows":
                os.startfile(log_path)
            elif platform.system() == "Darwin": # macOS
                subprocess.Popen(["open", log_path])
            else: # Linux
                subprocess.Popen(["xdg-open", log_path])
        except FileNotFoundError:
             QMessageBox.warning(self, "Log File Not Found", f"The log file was not found at:\n{log_path}")
        except Exception as e:
             logging.error(f"Failed to open log file '{log_path}': {e}")
             QMessageBox.warning(self, "Error", f"Could not open the log file.\nError: {e}")


# --- CaptureWidget ---
class CaptureWidget(QWidget):
    def __init__(self, parent=None, control_window=None):
        super().__init__(parent)
        if control_window is None:
             logging.error("CaptureWidget initialized without ControlWindow!")
             raise ValueError("ControlWindow reference is required for CaptureWidget.")

        self.control_window = control_window
        self.target_language = control_window.target_language # Initialize target language
        self.fonts = {}
        self.threshold = 5
        self.contrast_factor = 1.0 # TODO: Add UI control for this?
        # Use support folder for temporary directory
        self.tempDir = os.path.join(SUPPORT_FOLDER, "temp")
        try:
             if not os.path.exists(self.tempDir):
                 os.makedirs(self.tempDir)
             logging.info(f"Using temporary directory: {self.tempDir}")
        except OSError as e:
             logging.error(f"Failed to create temporary directory {self.tempDir}: {e}. Falling back.")
             self.tempDir = tempfile.mkdtemp(prefix="OverlayTranslate_") # Fallback


        self.original_text = ""
        self.translated_text = ""
        self.current_capture_path = "" # Path of the *original* PNG saved in SUPPORT_FOLDER
        self.resizing = False
        self.dragging = False
        self.offset = QPoint()
        self.borderRadius = 15
        self.translation_worker = None
        self.default_font_size = control_window.default_font_size # Get initial from control
        self.default_font_type = control_window.default_font_type # Get initial from control
        self.force_click_through = False

        self.flask_thread = None
        self.flask_running = False
        self.flask_server_ready = threading.Event()

        self.initUI()
        self.populate_fonts()
        self.start_flask_server()
        self.load_geometry()

    def initUI(self):
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMouseTracking(True)
        # Styles applied by global theme

        # Set initial click-through state
        self.updateClickThroughState()

    def populate_fonts(self):
        self.fonts = {
            "default": get_system_font_path("default"),
            "Arial": get_system_font_path("Arial"),
            "zh": get_system_font_path("zh"),
            "ja": get_system_font_path("ja"),
            "ko": get_system_font_path("ko")
        }
        logging.debug(f"Populated fonts: {self.fonts}")

    def start_flask_server(self):
        if self.flask_running:
            logging.warning("Flask server already running.")
            return

        def run_flask():
            try:
                logging.info("Starting Flask server thread...")
                self.flask_running = True
                # Pass logger to Flask app context if possible/needed, or ensure Flask logs separately
                flask_app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
            except OSError as e:
                 if "address already in use" in str(e).lower():
                     logging.warning(f"Flask server port 5000 already in use. Assuming external server.")
                     # Don't set flask_running to false, but signal ready state
                     self.flask_server_ready.set()
                     if self.control_window:
                          QtCore.QMetaObject.invokeMethod(self.control_window, "displayTranslationError", Qt.QueuedConnection, QtCore.Q_ARG(str, "Port 5000 in use. Using existing server?"))
                 else:
                     logging.error(f"Flask server thread failed: {e}", exc_info=True)
                     self.flask_running = False
                     self.flask_server_ready.set() # Signal failure/completion
                     if self.control_window:
                         QtCore.QMetaObject.invokeMethod(self.control_window, "displayTranslationError", Qt.QueuedConnection, QtCore.Q_ARG(str, f"Failed to start translation server: {e}"))
            except Exception as e:
                logging.error(f"Flask server thread failed: {e}", exc_info=True)
                self.flask_running = False
                self.flask_server_ready.set() # Signal failure/completion
                if self.control_window:
                    QtCore.QMetaObject.invokeMethod(self.control_window, "displayTranslationError", Qt.QueuedConnection, QtCore.Q_ARG(str, f"Failed to start translation server: {e}"))
            finally:
                logging.info("Flask server thread finished.")
                self.flask_running = False # Set to false on any exit
                if not self.flask_server_ready.is_set():
                    self.flask_server_ready.set() # Ensure event is always set on exit

        self.flask_thread = Thread(target=run_flask, name="FlaskServerThread", daemon=True)
        self.flask_thread.start()

        checker_thread = Thread(target=self.check_flask_server_readiness, name="FlaskReadyCheckThread", daemon=True)
        checker_thread.start()

    def check_flask_server_readiness(self):
        start_time = time.time()
        timeout = 10 # Check for 10 seconds
        server_ready = False
        while time.time() - start_time < timeout and not server_ready and self.flask_running:
            try:
                response = requests.get("http://127.0.0.1:5000/api/languages", timeout=1)
                if response.status_code == 200:
                    logging.info("Flask server is ready.")
                    server_ready = True
                    self.flask_server_ready.set() # Signal success
                    return
            except requests.ConnectionError: logging.debug("Flask server not ready yet (connection refused)...")
            except requests.Timeout: logging.debug("Flask server readiness check timed out, retrying...")
            except Exception as e: logging.error(f"Error checking Flask server readiness: {e}")

            if not server_ready: time.sleep(0.5)

        # Ensure the event is set even if loop finishes without success/error
        if not self.flask_server_ready.is_set():
            if not self.flask_running:
                 logging.error("Flask server thread terminated before readiness check completed.")
                 if self.control_window:
                     QtCore.QMetaObject.invokeMethod(self.control_window, "displayTranslationError", Qt.QueuedConnection, QtCore.Q_ARG(str, "Translation server stopped prematurely."))
            elif not server_ready:
                 logging.error(f"Flask server did not become ready within {timeout} seconds.")
                 if self.control_window:
                      QtCore.QMetaObject.invokeMethod(self.control_window, "displayTranslationError", Qt.QueuedConnection, QtCore.Q_ARG(str, "Translation server failed to start (timeout)."))
            self.flask_server_ready.set() # Set event on timeout or thread stop


    def shutdown_flask_server(self):
        if not self.flask_running:
            logging.info("Flask server is not running (or assumed external).")
            return

        logging.info("Requesting Flask server shutdown via HTTP...")
        shutdown_url = "http://127.0.0.1:5000/shutdown"
        try:
            requests.post(shutdown_url, timeout=2)
            logging.info("Flask server shutdown request sent successfully.")
        except requests.exceptions.ConnectionError:
             logging.info("Flask server connection closed during shutdown request (likely successful).")
        except requests.Timeout:
             logging.warning("Flask server shutdown request timed out.")
        except Exception as e:
            logging.error(f"Failed to send shutdown request to Flask server ({shutdown_url}): {e}")

        if self.flask_thread and self.flask_thread.is_alive():
            logging.debug("Flask server thread joining (short timeout)...")
            self.flask_thread.join(timeout=0.5)
            if self.flask_thread.is_alive():
                logging.warning("Flask server thread did not terminate quickly. Proceeding with exit.")
            else:
                logging.info("Flask server thread joined successfully.")
        else:
             logging.debug("Flask server thread was already finished.")
        self.flask_running = False

    def cleanup(self):
        logging.info("Cleaning up CaptureWidget resources...")
        self.shutdown_flask_server()
        # Clean up temporary files within the support/temp folder
        if hasattr(self, 'tempDir') and os.path.exists(self.tempDir):
            logging.info(f"Cleaning up temporary directory: {self.tempDir}")
            for filename in os.listdir(self.tempDir):
                file_path = os.path.join(self.tempDir, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                        logging.debug(f"Removed temp file: {file_path}")
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                        logging.debug(f"Removed temp subdir: {file_path}")
                except Exception as e:
                    logging.error(f"Failed to delete temp item {file_path}: {e}")
            # Optionally remove the temp dir itself if empty, or keep it
            # try:
            #     os.rmdir(self.tempDir)
            #     logging.info(f"Removed empty temporary directory: {self.tempDir}")
            # except OSError:
            #     logging.warning(f"Temporary directory {self.tempDir} not empty, leaving.")


    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Use themed colors for the overlay background and border
        bg_color = QColor(current_theme["colors"].get("bg_groupbox", "rgba(30,30,30,150)"))
        bg_color.setAlpha(int(bg_color.alpha() * 0.6)) # Make it slightly more transparent than groupbox
        border_color = QColor(current_theme["colors"].get("border_accent", "#00ffcc"))

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 2))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), self.borderRadius, self.borderRadius)

        # Draw resize handle indicator (using theme accent color)
        painter.setBrush(QBrush(border_color))
        handle_size = self.borderRadius
        handle_rect = QRect(self.width() - handle_size, self.height() - handle_size, handle_size, handle_size)
        painter.drawRect(handle_rect)

    # --- MODIFICATION 3: Accept target_language ---
    def displayTranslatedImage(self, result, original_file_path, target_language_code):
        logging.info("Attempting to display TranslatedImageViewer...")
        logging.debug(f"Display Result Data: {result}")
        logging.debug(f"Target Language for Viewer Font: {target_language_code}")

        file_name = original_file_path
        boxes = result.get('boxes', [])
        translated_lines = result.get('translated_lines', [])

        if not file_name or not os.path.exists(file_name):
             logging.error(f"Cannot display viewer: Original capture path '{file_name}' is invalid or missing.")
             QMessageBox.critical(self.control_window, "Viewer Error", "Cannot display result: Original image file missing.")
             return

        # Font path and size are now handled more dynamically inside the viewer
        # We pass the control window defaults and the target language
        initial_font_path = self.fonts.get(self.default_font_type, get_system_font_path("default"))
        initial_font_size = self.default_font_size

        try:
            logging.debug("Creating TranslatedImageViewer instance...")
            viewer = TranslatedImageViewer(
                file_name, boxes, translated_lines,
                initial_font_path, initial_font_size,
                target_language_code, # Pass the target language code
                self.control_window # Parent the viewer to the control window
            )
            logging.debug("Showing TranslatedImageViewer dialog...")
            viewer.exec()
            logging.debug("TranslatedImageViewer closed.")
        except Exception as e:
            logging.error(f"Failed to create or show TranslatedImageViewer: {e}", exc_info=True)
            QMessageBox.critical(self.control_window, "Viewer Error", f"Could not display the translated image viewer:\n{e}")
    # --- END MODIFICATION 3 ---

    def toggleClickThrough(self):
        self.force_click_through = not self.force_click_through
        self.updateClickThroughState()
        if self.control_window:
            button_text = "Disable Click-Through (F2)" if self.force_click_through else "Enable Click-Through (F2)"
            self.control_window.toggle_btn.setText(button_text)
        logging.info(f"User forced click-through toggled {'ON' if self.force_click_through else 'OFF'}.")

    def updateClickThroughState(self):
        opacity = self.windowOpacity()
        # Use a tolerance for opacity check due to potential float inaccuracies
        should_be_click_through = self.force_click_through or math.isclose(opacity, MIN_OPACITY, rel_tol=1e-5, abs_tol=1e-5)

        current_flags = self.windowFlags()
        is_currently_click_through = bool(current_flags & Qt.WindowTransparentForInput)

        needs_update = False
        if should_be_click_through and not is_currently_click_through:
             self.setWindowFlags(current_flags | Qt.WindowTransparentForInput)
             needs_update = True
             logging.debug(f"Enabling click-through (Forced: {self.force_click_through}, Opacity: {opacity:.3f})")
        elif not should_be_click_through and is_currently_click_through:
             self.setWindowFlags(current_flags & ~Qt.WindowTransparentForInput)
             needs_update = True
             logging.debug(f"Disabling click-through (Forced: {self.force_click_through}, Opacity: {opacity:.3f})")

        if needs_update:
            self.show() # Re-apply flags by re-showing the window
            if should_be_click_through:
                 self.setCursor(Qt.ArrowCursor) # Reset cursor if click-through enabled

    def is_on_resize_corner(self, pos):
        handle_size = self.borderRadius
        return (pos.x() >= self.width() - handle_size - self.threshold and
                pos.y() >= self.height() - handle_size - self.threshold)

    def mousePressEvent(self, event):
        is_click_through_active = bool(self.windowFlags() & Qt.WindowTransparentForInput)
        if is_click_through_active:
             event.ignore()
             return

        if event.button() == Qt.LeftButton:
             if self.is_on_resize_corner(event.pos()):
                 self.resizing = True
                 self.offset = event.globalPosition().toPoint() - self.geometry().bottomRight()
                 self.setCursor(Qt.SizeFDiagCursor)
                 logging.debug("Resize started.")
                 event.accept()
             else:
                 self.dragging = True
                 self.offset = event.position().toPoint()
                 self.setCursor(Qt.SizeAllCursor)
                 logging.debug("Drag started.")
                 event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
         is_click_through_active = bool(self.windowFlags() & Qt.WindowTransparentForInput)
         if is_click_through_active:
              event.ignore()
              return

         if event.buttons() & Qt.LeftButton:
             if self.resizing:
                 new_bottom_right = event.globalPosition().toPoint() - self.offset
                 new_width = max(100, new_bottom_right.x() - self.geometry().left())
                 new_height = max(50, new_bottom_right.y() - self.geometry().top())
                 self.resize(new_width, new_height)
                 event.accept()
             elif self.dragging:
                 new_pos = event.globalPosition().toPoint() - self.offset
                 screen_geo = QApplication.primaryScreen().availableGeometry()
                 # Keep window fully on screen during drag
                 new_pos.setX(max(screen_geo.left(), min(new_pos.x(), screen_geo.right() - self.width())))
                 new_pos.setY(max(screen_geo.top(), min(new_pos.y(), screen_geo.bottom() - self.height())))

                 # # Allow partial off-screen drag (original behaviour)
                 # new_pos.setX(max(screen_geo.left() - self.width() + 50, min(new_pos.x(), screen_geo.right() - 50)))
                 # new_pos.setY(max(screen_geo.top() - self.height() + 50, min(new_pos.y(), screen_geo.bottom() - 50)))
                 self.move(new_pos)
                 event.accept()
             else: # Only update cursor if not dragging/resizing
                  if self.is_on_resize_corner(event.pos()): self.setCursor(Qt.SizeFDiagCursor)
                  else: self.setCursor(Qt.ArrowCursor)
                  event.ignore()
         else: # Update cursor on hover when no buttons pressed
              if self.is_on_resize_corner(event.pos()): self.setCursor(Qt.SizeFDiagCursor)
              else: self.setCursor(Qt.ArrowCursor)
              event.ignore()

    def mouseReleaseEvent(self, event):
         is_click_through_active = bool(self.windowFlags() & Qt.WindowTransparentForInput)
         if is_click_through_active:
              event.ignore()
              return

         if event.button() == Qt.LeftButton:
             if self.resizing:
                 self.resizing = False
                 self.unsetCursor()
                 self.save_geometry()
                 logging.debug("Resize finished.")
                 event.accept()
             elif self.dragging:
                 self.dragging = False
                 self.unsetCursor()
                 self.save_geometry()
                 logging.debug("Drag finished.")
                 event.accept()
             else:
                 event.ignore()
         else:
             super().mouseReleaseEvent(event)

    def load_geometry(self):
        positions = load_window_positions()
        if 'CaptureWidget' in positions:
             try:
                 geometry = positions['CaptureWidget']
                 if all(k in geometry for k in ('x', 'y', 'width', 'height')):
                     self.setGeometry(int(geometry['x']), int(geometry['y']), int(geometry['width']), int(geometry['height']))
                     opacity = geometry.get('opacity', 0.8)
                     self.setWindowOpacity(float(opacity))
                     self.updateClickThroughState() # Ensure correct state after loading
                     logging.debug(f"Loaded CaptureWidget geometry: {geometry}, Opacity: {opacity}")
                 else:
                     logging.warning("CaptureWidget geometry incomplete. Using default.")
                     self.setGeometry(100, 100, 600, 400)
             except (ValueError, TypeError) as e:
                 logging.error(f"Error loading CaptureWidget geometry: {e}. Using default.")
                 self.setGeometry(100, 100, 600, 400)
        else:
             self.setGeometry(100, 100, 600, 400)

    def save_geometry(self):
#        positions = load_window_positions() # Load existing
#        positions['CaptureWidget'] = {
#            'x': self.x(),
#            'y': self.y(),
#            'width': self.width(),
#            'height': self.height(),
#            'opacity': self.windowOpacity()
#        }
#        # Call main save function
#        save_window_positions(positions)
#        logging.debug(f"Saved CaptureWidget geometry and opacity.")
        logging.debug("CaptureWidget.save_geometry called (no immediate save).")
        pass

    def closeEvent(self, event):
        logging.debug("CaptureWidget closeEvent called.")
        self.save_geometry()
        # Cleanup managed by ControlWindow
        event.accept()


# --- SnippingTool ---
class SnippingTool(QWidget):
    def __init__(self, capture_widget):
        super().__init__()
        if not capture_widget:
            raise ValueError("SnippingTool requires a valid CaptureWidget instance.")
        self.capture_widget = capture_widget
        self.parent_control_window = capture_widget.control_window

        self.window_id = getattr(Qt, 'WId', 0)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

        self.selection_rect = QRect()
        self.start_point = QPoint()
        self.dragging = False

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.updateGlow)
        self.glow_phase = 0.0
        self.glow_intensity = 1.0

        self.overlay_color = QColor(0, 0, 0, 100)
        self.setVisible(False)

    def showEvent(self, event):
        logging.debug("SnippingTool shown.")
        desktop_geometry = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(desktop_geometry)
        self.selection_rect = QRect()
        self.dragging = False
        self.glow_phase = 0.0
        if not self.animation_timer.isActive():
            self.animation_timer.start(30)
        self.update()
        self.activateWindow()
        self.raise_()
        super().showEvent(event)

    def hideEvent(self, event):
        logging.debug("SnippingTool hidden.")
        if self.animation_timer.isActive():
            self.animation_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self.overlay_color)

        if not self.selection_rect.isNull() and self.selection_rect.isValid():
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self.selection_rect, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # Use theme accent color for glow
            glow_base_color = QColor(current_theme["colors"].get("border_accent", "#00ffcc"))
            current_glow_alpha = 150 + int(80 * self.glow_intensity * abs(math.sin(self.glow_phase)))
            glow_color = QColor(glow_base_color.red(), glow_base_color.green(), glow_base_color.blue(), current_glow_alpha)

            pen_width = 3
            glow_pen = QPen(glow_color, pen_width)
            glow_pen.setJoinStyle(Qt.RoundJoin)

            painter.setPen(glow_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(self.selection_rect.adjusted(-1, -1, 1, 1), 8, 8)

            # Use a theme light border color for the dashed line
            dash_color = QColor(current_theme["colors"].get("border_light", "rgba(255, 255, 255, 50)"))
            dash_pen = QPen(dash_color, 1, Qt.DashLine)
            painter.setPen(dash_pen)
            painter.drawRoundedRect(self.selection_rect, 8, 8)

    def updateGlow(self):
        self.glow_phase += 0.15
        if self.glow_phase > 2 * math.pi:
            self.glow_phase -= 2 * math.pi
        if not self.selection_rect.isNull():
             update_rect = self.selection_rect.adjusted(-5, -5, 5, 5)
             self.update(update_rect)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_point = event.pos()
            self.selection_rect = QRect(self.start_point, QSize(1, 1))
            self.dragging = True
            self.update()
            event.accept()
        elif event.button() == Qt.RightButton:
             logging.debug("Snipping cancelled via right-click.")
             self.hide()
             if self.capture_widget and not self.capture_widget.isVisible():
                 self.capture_widget.show()
             event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            self.selection_rect = QRect(self.start_point, event.pos()).normalized()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            if self.selection_rect.width() > 10 and self.selection_rect.height() > 10:
                logging.debug(f"Snip selection finished: {self.selection_rect}")
                self.takeSnip()
            else:
                logging.debug("Snip selection too small, cancelled.")
            self.hide()
            if self.capture_widget:
                self.capture_widget.show()
            event.accept()

    def keyPressEvent(self, event):
         if event.key() == Qt.Key_Escape:
             logging.debug("Snipping cancelled via Escape key.")
             self.hide()
             if self.capture_widget and not self.capture_widget.isVisible():
                 self.capture_widget.show()
             event.accept()
         else:
             super().keyPressEvent(event)

    def takeSnip(self):
        screen = QApplication.primaryScreen()
        if not screen:
             logging.error("Could not get primary screen for snipping.")
             return
        rect_to_grab = self.selection_rect
        # Short delay to allow the snipping overlay to hide before grabbing
        QTimer.singleShot(50, lambda: self._perform_grab(screen, rect_to_grab))

    def _perform_grab(self, screen, rect):
        try:
             # Ensure the capture widget is hidden before grabbing
             if self.capture_widget and self.capture_widget.isVisible():
                 self.capture_widget.hide()
                 QApplication.processEvents() # Allow hide to process
                 time.sleep(0.05) # Small extra delay

             # Use 0 for window ID to capture the desktop directly
             screenshot = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())

             # Show capture widget again immediately after grab
             if self.capture_widget and not self.capture_widget.isVisible():
                 self.capture_widget.show()

             if screenshot.isNull():
                  logging.error("Snipping grabWindow returned a null pixmap.")
                  QMessageBox.warning(self.parent_control_window, "Snip Error", "Failed to capture the selected screen area.")
                  return

             timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
             ensure_support_folder()
             fileName = os.path.join(SUPPORT_FOLDER, f"snip_{timestamp}.png")

             if not screenshot.save(fileName, "PNG", quality=95):
                  logging.error(f"Failed to save snip screenshot to {fileName}")
                  QMessageBox.warning(self.parent_control_window, "Snip Error", "Failed to save the captured snip.")
                  return

             logging.info(f"Snip captured successfully: {fileName}")
             # Update the capture widget's current path for metadata saving
             if self.capture_widget:
                 self.capture_widget.current_capture_path = fileName

             # Trigger translation in the control window
             if self.parent_control_window:
                 self.parent_control_window.translation_progress_bar.setVisible(True)
                 self.parent_control_window.translation_progress_bar.setValue(5)
                 self.parent_control_window.translation_progress_bar.setFormat("Translating Snip...")
                 QApplication.processEvents()
                 self.parent_control_window.startTranslationWorker(fileName, live=False)
             else:
                  logging.error("Cannot start translation: Parent ControlWindow reference lost.")
        except Exception as e:
             logging.error(f"Error during snip capture or saving: {e}", exc_info=True)
             QMessageBox.critical(self.parent_control_window, "Snip Error", f"An error occurred during snipping:\n{e}")
             # Ensure capture widget is shown even if error occurs
             if self.capture_widget and not self.capture_widget.isVisible():
                 self.capture_widget.show()


# --- ChatWindow ---
class ChatWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        logging.debug("ChatWindow.__init__ started")
        self.parent = parent
        self.font_size = 14
        self.ai_streaming_worker = None
        self.last_ai_response = ""

        self.setWindowTitle("AI Chat")
        self.setMinimumSize(500, 400)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint |
                            Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint |
                            Qt.WindowMaximizeButtonHint |
                            (Qt.WindowStaysOnTopHint if parent else Qt.Widget))
        # Theme applied globally
        try:
            self.initUI()
            # --- FIX: Load positions without processing theme ---
            positions = load_window_positions(process_theme=False)
            # --- END FIX ---
            self.load_geometry(positions) # Pass dict
            logging.debug("ChatWindow.__init__ completed")
        except Exception as e:
            logging.error(f"ChatWindow.__init__ failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Chat Init Error", f"Failed to initialize chat window:\n{e}")

    def initUI(self):
        logging.debug("Initializing ChatWindow UI")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        self.chat_history = QTextEdit(self)
        self.chat_history.setReadOnly(True)
        self.chat_history.setFontFamily("Roboto Mono")
        self.update_chat_history_style()
        logging.debug("Chat history widget created")
        main_layout.addWidget(self.chat_history)

        controls_layout = QHBoxLayout()
        controls_layout.addStretch(1)

        self.decrease_font_btn = QPushButton("-", self)
        self.decrease_font_btn.setToolTip("Decrease Font Size")
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "zoom_out.svg")
        if os.path.exists(icon_path): self.decrease_font_btn.setIcon(QIcon(icon_path)); self.decrease_font_btn.setText('')
        self.decrease_font_btn.setFixedSize(30, 30)
        self.decrease_font_btn.clicked.connect(self.decreaseFontSize)
        controls_layout.addWidget(self.decrease_font_btn)

        self.increase_font_btn = QPushButton("+", self)
        self.increase_font_btn.setToolTip("Increase Font Size")
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "zoom_in.svg")
        if os.path.exists(icon_path): self.increase_font_btn.setIcon(QIcon(icon_path)); self.increase_font_btn.setText('')
        self.increase_font_btn.setFixedSize(30, 30)
        self.increase_font_btn.clicked.connect(self.increaseFontSize)
        controls_layout.addWidget(self.increase_font_btn)

        main_layout.addLayout(controls_layout)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(5)

        self.user_input = QLineEdit(self)
        self.user_input.setPlaceholderText("Enter your message here...")
        self.update_user_input_style()
        self.user_input.returnPressed.connect(self.sendMessage)
        logging.debug("User input field created")
        input_layout.addWidget(self.user_input)

        self.send_btn = QPushButton(">", self)
        self.send_btn.setToolTip("Send Message (Enter)")
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "send.svg")
        if os.path.exists(icon_path): self.send_btn.setIcon(QIcon(icon_path)); self.send_btn.setText('')
        self.send_btn.setFixedSize(40, 40)
        self.send_btn.clicked.connect(self.sendMessage)
        logging.debug("Send button created")
        input_layout.addWidget(self.send_btn)

        main_layout.addLayout(input_layout)
        self.setLayout(main_layout)
        logging.debug("ChatWindow layout set")

        self.append_message("[System]", "AI Chat initialized. Enter your message.", system=True)

    def update_chat_history_style(self):
        self.chat_history.setStyleSheet(f"""
            QTextEdit {{
                background-color: {current_theme['colors'].get('bg_input', 'rgba(10, 10, 20, 200)')};
                color: {current_theme['colors'].get('text_light', '#e0e0e0')};
                font-size: {self.font_size}px;
                border-radius: 8px;
                border: 1px solid {current_theme['colors'].get('border_light', 'rgba(255, 255, 255, 20)')};
                padding: 10px;
                font-family: 'Roboto Mono', 'Courier New', monospace;
            }}
        """)

    def update_user_input_style(self):
         self.user_input.setStyleSheet(f"""
             QLineEdit {{
                 background-color: {current_theme['colors'].get('bg_input', 'rgba(40, 40, 50, 200)')};
                 color: {current_theme['colors'].get('text_light', '#e0e0e0')};
                 font-size: {self.font_size}px;
                 border-radius: 6px;
                 border: 1px solid {current_theme['colors'].get('border_light', 'rgba(255, 255, 255, 20)')};
                 padding: 8px 10px;
             }}
             QLineEdit:focus {{
                 border: 1px solid {current_theme['colors'].get('border_accent', '#00ffcc')};
             }}
         """)

    def append_message(self, sender, message, system=False):
        if system:
            formatted_message = f"<div style='color: #888888;'><i>[System] {message}</i></div>"
        elif sender == "You":
             escaped_message = textwrap.fill(message.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), width=80)
             formatted_message = f"<div style='color: {current_theme['colors'].get('text_light', '#e0e0e0')};'><b>[You]&gt;</b><pre style='display: inline; white-space: pre-wrap; font-family: inherit;'> {escaped_message}</pre></div>"
        elif sender == "AI":
             # Start the div but don't close it, text chunks will be added
             formatted_message = f"<div style='color: {current_theme['colors'].get('text_accent', '#00ffcc')};'><b>[AI]&gt;</b> "
        else: # Generic sender, currently unused
            escaped_message = message.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            formatted_message = f"<div><b>[{sender}]&gt;</b> {escaped_message}</div>"

        # Use HTML insertion for better control, especially for AI messages
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        if sender != "AI": # Insert complete HTML block for non-AI messages
             cursor.insertHtml(formatted_message + "<br>") # Add a line break
        else: # Insert just the start of the AI message block
             cursor.insertHtml(formatted_message)

        self.chat_history.setTextCursor(cursor)
        self.chat_history.ensureCursorVisible()


    def append_ai_chunk(self, chunk):
        # Append plain text chunk to the currently open AI message div
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        escaped_chunk = chunk.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        cursor.insertText(escaped_chunk) # Insert plain text
        self.chat_history.setTextCursor(cursor)
        self.chat_history.ensureCursorVisible()


    def finish_ai_message(self):
         # Close the AI message div and add a line break
         cursor = self.chat_history.textCursor()
         cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
         cursor.insertHtml("</div><br>")
         self.chat_history.setTextCursor(cursor)
         self.chat_history.ensureCursorVisible()


    def sendMessage(self):
        user_message = self.user_input.text().strip()
        logging.debug(f"User input received: '{user_message}'")
        if not user_message: return

        self.append_message("You", user_message)
        self.user_input.clear()
        self.send_btn.setEnabled(False)
        self.user_input.setEnabled(False)

        self.append_message("AI", "") # Add prefix, prepares the div
        self.start_streaming_response(user_message)

    def start_streaming_response(self, message):
        if self.ai_streaming_worker and self.ai_streaming_worker.isRunning():
            logging.warning("Stopping previous AI streaming worker.")
            self.ai_streaming_worker.stop()

        if not ai_api_config.get("provider"):
            logging.error("Cannot send message: AI provider not configured.")
            self.append_ai_chunk(" Error: AI provider not configured.")
            self.finish_ai_message()
            self.send_btn.setEnabled(True)
            self.user_input.setEnabled(True)
            return

        logging.info(f"Starting AI streaming response ({ai_api_config['provider']})")
        target_lang = self.parent.target_language if self.parent else 'en'
        self.ai_streaming_worker = AIStreamingWorker(message, target_lang, self)
        self.ai_streaming_worker.text_chunk.connect(self.append_ai_chunk)
        self.ai_streaming_worker.finished_stream.connect(self.on_streaming_finished)
        self.ai_streaming_worker.error_stream.connect(self.on_streaming_error)
        self.ai_streaming_worker.start()

    def on_streaming_finished(self, final_response):
        logging.info(f"AI stream finished. Final Text Length: {len(final_response)}")
        self.finish_ai_message() # Close the AI message div
        self.last_ai_response = final_response
        self.send_btn.setEnabled(True)
        self.user_input.setEnabled(True)
        self.user_input.setFocus()

    def on_streaming_error(self, error_message):
        logging.error(f"AI streaming error: {error_message}")
        self.append_ai_chunk(f" [Stream Error: {error_message}]")
        self.finish_ai_message() # Close the AI message div even on error
        self.send_btn.setEnabled(True)
        self.user_input.setEnabled(True)
        self.user_input.setFocus()

    def increaseFontSize(self):
        if self.font_size < 24:
            self.font_size += 1
            self.update_chat_history_style()
            self.update_user_input_style()
            logging.debug(f"Chat font size increased to {self.font_size}")

    def decreaseFontSize(self):
        if self.font_size > 9:
            self.font_size -= 1
            self.update_chat_history_style()
            self.update_user_input_style()
            logging.debug(f"Chat font size decreased to {self.font_size}")

    def load_geometry(self):
        positions = load_window_positions()
        if 'ChatWindow' in positions:
            try:
                geometry = positions['ChatWindow']
                if all(k in geometry for k in ('x', 'y', 'width', 'height')):
                    self.setGeometry(int(geometry['x']), int(geometry['y']), int(geometry['width']), int(geometry['height']))
                    logging.debug(f"Loaded ChatWindow geometry: {geometry}")
                else: logging.warning("ChatWindow geometry incomplete.")
            except (ValueError, TypeError) as e: logging.error(f"Error loading ChatWindow geometry: {e}.")

    def save_geometry(self):
#        positions = load_window_positions() # Load existing
#        positions['ChatWindow'] = { 'x': self.x(), 'y': self.y(), 'width': self.width(), 'height': self.height() }
#        # Call main save function
#        save_window_positions(positions)
        logging.debug("ChatWindow.save_geometry called (no immediate save).")
        pass
    def closeEvent(self, event):
        logging.debug("ChatWindow closeEvent called.")
        self.save_geometry()
        if self.ai_streaming_worker and self.ai_streaming_worker.isRunning():
            logging.info("Stopping AI streaming worker on chat window close.")
            self.ai_streaming_worker.stop()
        event.accept()


# --- AIStreamingWorker Thread ---
# (Keep AIStreamingWorker class as it is - no changes requested there)
class AIStreamingWorker(QThread):
    text_chunk = Signal(str) # Emits chunks of text as they arrive
    finished_stream = Signal(str) # Emits the full concatenated response on success
    error_stream = Signal(str) # Emits error message on failure

    def __init__(self, message, target_language, parent=None):
        super().__init__(parent)
        self.message = message
        self.target_language = target_language
        self.is_running = True

    def stop(self):
        logging.debug("AIStreamingWorker requested to stop.")
        self.is_running = False

    def run(self):
        if not self.is_running:
            logging.warning("AIStreamingWorker cancelled before start.")
            return

        provider = ai_api_config.get("provider")
        endpoint = ai_api_config.get("endpoint")
        if not provider or not endpoint:
            self.error_stream.emit("No AI API configured.")
            logging.error("AI streaming run attempted without configured provider.")
            return

        start_time = time.time()
        logging.info(f"Starting AI stream request ({provider}). Target Endpoint: {endpoint}")
        full_response_text = ""

        try:
            lang_map = { "en": "English", "es": "Spanish", "fr": "French", "de": "German",
                        "it": "Italian", "pt": "Portuguese", "ru": "Russian",
                        "zh-cn": "Simplified Chinese", "zh": "Simplified Chinese",
                        "ja": "Japanese", "ko": "Korean",
                        "ch": "Chinese" }
            target_lang_name = lang_map.get(self.target_language, self.target_language)

            prompt = (
                f"User: {self.message}\n"
                f"Assistant (concise response in {target_lang_name}):"
            )
            logging.debug(f"AI Chat Prompt:\n---PROMPT START---\n{prompt}\n---PROMPT END---")

            headers = {"Content-Type": "application/json"}
            api_key = None

            if provider in ["OpenAI", "LM Studio"]:
                try:
                    api_key = keyring.get_password("OverlayTranslate", provider)
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"
                    elif provider == "OpenAI":
                        raise ValueError(f"API key for {provider} not found.")
                    else:
                        logging.warning(f"API key for {provider} not found/provided, proceeding without.")
                except Exception as key_err:
                    raise ValueError(f"Failed to retrieve API key for {provider}: {key_err}")

            response = None
            max_tokens = 1024
            can_stream = True

            if provider == "OpenAI":
                headers["Accept"] = "text/event-stream"
                data = { "model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens, "temperature": 0.6, "stream": True }
                logging.debug(f"Sending stream request to OpenAI: {endpoint}")
                response = requests.post(endpoint, headers=headers, json=data, stream=True, timeout=60)
            elif provider == "Ollama":
                if endpoint.endswith('/api/chat'):
                    headers["Accept"] = "application/x-ndjson"
                    data = { "model": "llama3.1:8b", # Example model
                             "messages": [{"role": "user", "content": prompt}],
                            "stream": True, "options": { "temperature": 0.6, "num_predict": max_tokens } }
                    logging.debug(f"Sending stream request to Ollama (chat): {endpoint}")
                    response = requests.post(endpoint, headers=headers, json=data, stream=True, timeout=60)
                elif endpoint.endswith('/api/generate'):
                    can_stream = False # /generate endpoint typically doesn't stream
                    data = { "model": "llama3.1:8b", # Example model
                             "prompt": prompt, "stream": False,
                            "options": { "temperature": 0.6, "num_predict": max_tokens } }
                    logging.debug(f"Sending non-stream request to Ollama (generate): {endpoint}")
                    response = requests.post(endpoint, headers=headers, json=data, timeout=60)
                else:
                    raise ValueError("Ollama endpoint must end with /api/chat (streaming) or /api/generate (non-streaming)")
            elif provider == "LM Studio":
                headers["Accept"] = "text/event-stream"
                data = { "model": "loaded-model", # Assume user loads model in LM Studio UI
                         "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens, "temperature": 0.6, "stream": True }
                logging.debug(f"Sending stream request to LM Studio: {endpoint}")
                response = requests.post(endpoint, headers=headers, json=data, stream=True, timeout=60)
            else:
                raise ValueError(f"Unsupported AI provider for streaming: {provider}")

            response.raise_for_status()
            logging.debug(f"AI Response Status Code: {response.status_code}")
            client = None

            if can_stream:
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/event-stream" in content_type:
                    try:
                        from sseclient import SSEClient
                        client = SSEClient(response)
                        for event in client.events():
                            if not self.is_running: break
                            if event.event == 'message' and event.data:
                                if event.data.strip() == '[DONE]': break
                                try:
                                    json_data = json.loads(event.data)
                                    delta = json_data.get("choices", [{}])[0].get("delta", {})
                                    text_chunk = delta.get("content", "")
                                    if text_chunk:
                                        full_response_text += text_chunk
                                        if self.is_running: self.text_chunk.emit(text_chunk)
                                except (json.JSONDecodeError, IndexError, KeyError) as e:
                                    logging.error(f"Error parsing SSE chunk: {e}, data: {event.data[:100]}")
                            elif event.event == 'error':
                                raise RuntimeError(f"AI stream error event: {event.data}")
                        if client: client.close()
                    except ImportError:
                        logging.error("sseclient-py not found. pip install sseclient-py")
                        if client: client.close()
                        raise RuntimeError("SSEClient library required for this provider.")
                    except Exception as e:
                        logging.error(f"Error processing SSE stream: {e}", exc_info=True)
                        if client: client.close()
                        raise
                elif "application/x-ndjson" in content_type:
                    try:
                        for line in response.iter_lines():
                            if not self.is_running: break
                            if line:
                                try:
                                    decoded_line = line.decode('utf-8').strip()
                                    if not decoded_line: continue
                                    json_data = json.loads(decoded_line)
                                    text_chunk = json_data.get("message", {}).get("content", "")
                                    is_done = json_data.get("done", False)
                                    if text_chunk:
                                        full_response_text += text_chunk
                                        if self.is_running: self.text_chunk.emit(text_chunk)
                                    if is_done: break
                                except (json.JSONDecodeError, KeyError) as e:
                                    logging.error(f"Error parsing NDJSON chunk: {e}, line: {decoded_line[:100]}")
                    except Exception as e:
                        logging.error(f"Error processing NDJSON stream: {e}", exc_info=True)
                        raise
                else:
                    logging.warning(f"Unexpected streaming Content-Type '{content_type}'. Reading full response.")
                    full_response_text = response.text
                    if self.is_running: self.text_chunk.emit(full_response_text)
            else: # Handle non-streaming response
                result = response.json()
                logging.debug(f"Received Non-Streaming JSON: {result}")
                if provider == "Ollama" and endpoint.endswith('/api/generate'):
                    full_response_text = result.get("response", "")
                else:
                    logging.warning(f"Received non-streaming response for unhandled provider/endpoint: {provider}/{endpoint}")
                    full_response_text = str(result)
                if not full_response_text: logging.warning("Non-streaming AI response content is empty.")
                if self.is_running: self.text_chunk.emit(full_response_text.strip())

            if not self.is_running:
                logging.warning("AI Processing stopped before completion.")
                return

            logging.info(f"AI processing finished in {time.time() - start_time:.3f} seconds.")
            self.finished_stream.emit(full_response_text.strip())

        except requests.exceptions.RequestException as e:
            error_msg = f"API Request Error: {e}"
            logging.error(f"AI streaming request failed ({provider}): {e}", exc_info=True)
            if self.is_running: self.error_stream.emit(error_msg)
        except ValueError as e:
            error_msg = f"Configuration/Value Error: {e}"
            logging.error(f"AI streaming config error ({provider}): {e}", exc_info=True)
            if self.is_running: self.error_stream.emit(error_msg)
        except RuntimeError as e:
            error_msg = f"Runtime Error: {e}"
            logging.error(f"AI streaming runtime error ({provider}): {e}", exc_info=True)
            if self.is_running: self.error_stream.emit(error_msg)
        except Exception as e:
            error_msg = f"Unexpected Error: {e}"
            logging.error(f"Unexpected error in AI processing ({provider}): {e}", exc_info=True)
            if self.is_running: self.error_stream.emit(error_msg)
        finally:
            self.is_running = False
            if 'response' in locals() and response:
                try: response.close()
                except Exception as resp_close_err: logging.warning(f"Error closing AI response connection: {resp_close_err}")
            logging.debug("AIStreamingWorker finished run method.")

# --- Theme Related Classes (ThemeDialog, ColorBarPicker) ---
# Inside class ThemeDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Theme Settings")
        self.setMinimumWidth(500)
        # Inherits style from global theme

        # Use a deep copy to avoid modifying the global theme until save
        self.current_local_theme = json.loads(json.dumps(current_theme)) # Deep copy trick
        self.layout = QVBoxLayout(self) # Assigns layout to 'self' immediately
        self.color_pickers = {}

        grid_layout = QtWidgets.QGridLayout()
        row, col = 0, 0
        # Use the new tooltip method
        for key, (name, tooltip) in self.get_user_friendly_names_and_tooltips().items():
            if key not in self.current_local_theme["colors"]:
                logging.warning(f"Theme key '{key}' not found in current_local_theme during dialog init.")
                continue # Skip if key missing in theme data

            label = QLabel(f"{name}:")
            label.setToolTip(tooltip) # <-- Add Tooltip

            color_button = QPushButton()
            color_button.setFixedSize(80, 25)
            # Ensure initial color is valid before updating button
            initial_color_str = self.current_local_theme["colors"].get(key, "#FFFFFFFF") # Default to white if missing
            if not QColor(initial_color_str).isValid():
                 logging.warning(f"Invalid initial color '{initial_color_str}' for key '{key}', defaulting button.")
                 initial_color_str = "#FFFFFFFF" # Use opaque white fallback for button display

            self.update_button_color(color_button, initial_color_str)
            color_button.clicked.connect(lambda k=key, b=color_button: self.pick_color(k, b))

            grid_layout.addWidget(label, row, col * 2)
            grid_layout.addWidget(color_button, row, col * 2 + 1)

            col += 1
            if col >= 2: col = 0; row += 1
            self.color_pickers[key] = color_button

        self.layout.addLayout(grid_layout)
        self.layout.addStretch()

        button_layout = QHBoxLayout()
        reset_btn = QPushButton("Reset to Default")
        save_btn = QPushButton("Save & Apply")
        cancel_btn = QPushButton("Cancel")
        reset_btn.clicked.connect(self.reset_theme)
        save_btn.clicked.connect(self.save_and_apply)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(reset_btn)
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)
        self.layout.addLayout(button_layout)

    # Renamed and expanded this method
    def get_user_friendly_names_and_tooltips(self):
        # Map internal keys to (User-friendly Name, Tooltip Text)
        return {
            "bg_main": ("Main Background", "Main window/dialog background color."),
            "bg_groupbox": ("Group Box BG", "Background color for group boxes."),
            "bg_titlebar": ("Group Title BG", "Background for group box titles."),
            "bg_input": ("Input BG", "Background for text inputs, combo boxes, progress bars."),
            "bg_tooltip": ("Tooltip BG", "Background color for tooltips."),
            "bg_menu": ("Menu BG", "Background for menus (main menu bar, context menus)."),
            "bg_menu_item_sel": ("Menu Sel BG", "Background color for selected menu items."),

            "text_light": ("Primary Text", "Main text color for labels, etc."),
            "text_accent": ("Accent Text", "Highlight/accent text color (e.g., labels, group titles)."),
            "text_secondary": ("Secondary Text", "Secondary accent color (e.g., slider handle)."),
            "text_button": ("Button Text", "Text color on buttons."),
            "text_disabled": ("Disabled Text", "Text color for disabled widgets."),
            "text_tooltip": ("Tooltip Text", "Text color for tooltips."),

            "border_main": ("Main Border", "Border around the main window (often transparent)."),
            "border_accent": ("Accent Border", "Highlight border color (e.g., focused inputs, capture overlay)."),
            "border_medium": ("Medium Border", "Standard border color (e.g., checkboxes, tooltips)."),
            "border_light": ("Light Border", "Subtle border color (e.g., inputs, group boxes, progress)."),
            "border_menu": ("Menu Border", "Border around menus."),

            "grad_button_start": ("Button Grad Start", "Start color for button background gradient."),
            "grad_button_end": ("Button Grad End", "End color for button background gradient."),
            "grad_button_hover_start": ("Btn Hover Start", "Start color for button hover gradient."),
            "grad_button_hover_end": ("Btn Hover End", "End color for button hover gradient."),
            "grad_button_pressed": ("Btn Pressed BG", "Background color when button is pressed."),
            "grad_slider_start": ("Slider Grad Start", "Start color for slider filled part gradient."),
            "grad_slider_end": ("Slider Grad End", "End color for slider filled part gradient."),
            "progress_chunk_start": ("Progress Start", "Start color for progress bar chunk gradient."),
            "progress_chunk_end": ("Progress End", "End color for progress bar chunk gradient."),
            "checkbox_checked": ("Checkbox Checked", "Background color for checked checkboxes."),
        }

    def update_button_color(self, button, color_str):
        try:
            # Ensure color_str is in #AARRGGBB format before passing to QColor
            if isinstance(color_str, str) and color_str.startswith('#') and len(color_str) == 9:
                color = QColor(color_str)
            else:
                 # Attempt conversion if needed, fallback if invalid
                 temp_color = QColor(color_str)
                 if temp_color.isValid():
                     color = temp_color
                 else:
                     raise ValueError(f"Invalid format: {color_str}")

            if color.isValid():
                # Use HexArgb for consistency, ensure some visibility for transparent colors
                display_alpha = max(color.alpha(), 100) # Ensure at least some opacity for preview
                display_color = QColor(color.red(), color.green(), color.blue(), display_alpha)
                button.setStyleSheet(f"background-color: {display_color.name(QColor.NameFormat.HexArgb)}; border: 1px solid #888;")
            else:
                # This path should ideally not be reached if input is validated
                logging.warning(f"Button update called with invalid QColor derived from: {color_str}")
                button.setStyleSheet("background-color: grey; border: 1px solid #888;")
        except Exception as e:
             logging.error(f"Error setting button color for input '{color_str}': {e}")
             button.setStyleSheet("background-color: red; border: 1px solid #888;") # Error indicator

    def pick_color(self, key, button):
        current_color_str = self.current_local_theme["colors"].get(key, "#FFFFFFFF")
        initial_color = QColor(current_color_str)
        if not initial_color.isValid():
            logging.warning(f"Invalid initial color '{current_color_str}' for key '{key}', using white.")
            initial_color = QColor("#FFFFFFFF") # Opaque white

        color_dialog = QColorDialog(initial_color, self)
        color_dialog.setOptions(QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color_dialog.exec():
             color = color_dialog.selectedColor()
             if color.isValid():
                 # --- Ensure saved format is #AARRGGBB ---
                 color_str = color.name(QColor.NameFormat.HexArgb)
                 self.current_local_theme["colors"][key] = color_str
                 self.update_button_color(button, color_str)


    def reset_theme(self):
        # Reset local copy to default
        self.current_local_theme = json.loads(json.dumps(DEFAULT_THEME)) # Deep copy default
        for key, button in self.color_pickers.items():
            if key in self.current_local_theme["colors"]:
                 self.update_button_color(button, self.current_local_theme["colors"][key])
            else:
                 # Handle case where default might miss a key (shouldn't happen)
                 self.update_button_color(button, "#FF0000FF") # Red error indicator
        QMessageBox.information(self, "Theme Reset", "Theme reset to default. Click 'Save & Apply' to confirm.")

    def save_and_apply(self):
        global current_theme
        # Apply the changes from the local copy to the global theme
        current_theme = json.loads(json.dumps(self.current_local_theme)) # Deep copy local to global
        apply_theme() # Apply the new global theme visually

        # --- Explicitly Save ALL settings ---
        try:
            # Load the current full state (positions etc.)
            positions = load_window_positions()
            # Update the 'theme' part with our confirmed changes
            positions['theme'] = current_theme # Use the updated global theme
            # Save the entire dictionary back
            # Use the main save function directly (it now includes theme)
            save_window_positions(positions)
            logging.info("Theme explicitly saved along with other settings.")
        except Exception as e:
            logging.error(f"Failed to explicitly save theme settings: {e}", exc_info=True)
            QMessageBox.warning(self, "Save Error", f"Could not save theme settings:\n{e}")

        self.accept() # Close the dialog


# --- TranslatedImageViewer Dialog ---
class TranslatedImageViewer(QDialog):
    # --- MODIFICATION 3: Add target_language_code to __init__ ---
    def __init__(self, image_path, boxes, translated_lines, initial_font_path, initial_font_size, target_language_code, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.boxes = boxes if boxes else []
        self.translated_lines = translated_lines if translated_lines else []
        self.target_language_code = target_language_code # Store target language
        self.original_image = None
        self.rendered_image = None # This will hold the image with translations drawn on
        self.image_label = None
        self.save_on_close = True # Flag to control automatic saving

        # Load positions/settings WITHOUT processing/logging theme
        positions = load_window_positions(process_theme=False) # <--- Set process_theme=False
        vs = positions.get('viewer_settings', {})
        default_font_color_tuple = (0, 0, 255, 255) # Opaque Blue default
        default_bg_outer_tuple = (255, 255, 255, 200) # Whiteish default
        default_bg_inner_tuple = (200, 200, 255, 180) # Light blueish default (unused currently)

        # Get saved colors or use defaults
        font_color_tuple = tuple(vs.get('font_color', default_font_color_tuple))
        bg_outer_tuple = tuple(vs.get('bg_color_outer', default_bg_outer_tuple))
        bg_inner_tuple = tuple(vs.get('bg_color_inner', default_bg_inner_tuple))

        self.font_color = QColor(*font_color_tuple)
        self.bg_color_outer = QColor(*bg_outer_tuple)
        self.bg_color_inner = QColor(*bg_inner_tuple) # Stored but not used in rendering currently

        # Determine initial font path and size
        saved_font_path = vs.get('font_path')
        saved_font_size = vs.get('font_size')

        if saved_font_path and saved_font_size:
            # Use saved font settings if they exist and are valid
            if os.path.exists(saved_font_path):
                 self.font_path = saved_font_path
                 self.font_size = saved_font_size
                 logging.info(f"Using saved viewer font: {self.font_path}, Size: {self.font_size}")
            else:
                 logging.warning(f"Saved viewer font path '{saved_font_path}' not found. Attempting language-based.")
                 self.font_path = get_system_font_path(self.target_language_code)
                 self.font_size = initial_font_size # Use initial size if path was bad
                 logging.info(f"Using language-based font: {self.font_path}, Size: {self.font_size}")
        else:
            # No saved settings, try to determine based on target language
            logging.info("No saved viewer font. Determining based on target language.")
            self.font_path = get_system_font_path(self.target_language_code)
            self.font_size = initial_font_size # Use default size from control window
            logging.info(f"Using language-based font: {self.font_path}, Size: {self.font_size}")

        # Final fallback if language-based path is still invalid
        if not self.font_path or not os.path.exists(self.font_path):
            logging.warning(f"Font path '{self.font_path}' invalid. Using absolute default.")
            self.font_path = get_system_font_path("default")
            # Keep initial_font_size
            logging.info(f"Using absolute default font: {self.font_path}, Size: {self.font_size}")


        # Load image (as before)
        try:
            self.original_image = Image.open(image_path).convert("RGBA")
        except Exception as e:
            logging.error(f"Failed to load image '{image_path}' for viewer: {e}", exc_info=True)
            QMessageBox.critical(self, "Image Load Error", f"Failed to load image:\n{e}")
            self.save_on_close = False # Don't try to save if image failed to load
            QTimer.singleShot(0, self.reject)
            return

        # Ensure lines match boxes (as before)
        if len(self.translated_lines) != len(self.boxes):
             logging.warning(f"Viewer line/box mismatch ({len(self.translated_lines)} lines vs {len(self.boxes)} boxes). Padding/truncating lines.")
             diff = len(self.boxes) - len(self.translated_lines)
             if diff > 0: self.translated_lines.extend([""] * diff)
             else: self.translated_lines = self.translated_lines[:len(self.boxes)]

        self.setWindowTitle("Translated Image Viewer")
        self.setMinimumSize(600, 500)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint |
                             Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint |
                             Qt.WindowMaximizeButtonHint)
        # Style applied globally

        self.initUI()
        self.renderTranslatedImage() # Initial render with determined font
        self.updateImageDisplay()
        self.load_viewer_geometry(positions) # Pass dict

    def initUI(self):
        # ... (main_layout, image_label setup as before) ...
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #202020; border-radius: 5px;") # Simple dark background
        self.image_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.image_label, 1) # Give label more space

        controls_group = QGroupBox("Display Settings")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setSpacing(8)

        # --- Font Selection Logic (Revised) ---
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("Font:"))
        self.font_combo = QComboBox()
        font_db = QFontDatabase()
        available_families = sorted(font_db.families())
        self.font_family_to_path = {}

        # Populate combo box with available system fonts and map family names to paths
        # Prioritize adding the currently selected font first if possible
        current_font_found_in_db = False
        if self.font_path and os.path.exists(self.font_path):
            try:
                loaded_font = ImageFont.truetype(self.font_path, 10) # Load small size to get name
                font_family_name = loaded_font.getname()[0] # Get primary family name
                # Add the current font if not already implicitly added by db scan
                if font_family_name not in [f for f in available_families if QFontInfo(font_db.font(f, font_db.styles(f)[0], 9)).family() == font_family_name]:
                     custom_name = f"{font_family_name} (Current Path)"
                     self.font_combo.addItem(custom_name)
                     self.font_family_to_path[custom_name] = self.font_path
                     current_font_found_in_db = True # Mark as found
                else:
                    # Font family is known to QFontDatabase, let normal loop handle it
                    pass
            except Exception as e:
                logging.error(f"Error trying to preload current font '{self.font_path}': {e}")

        # Add other system fonts
        for family in available_families:
             styles = font_db.styles(family)
             if styles:
                 try:
                    # Use QFontInfo to get the canonical family name and check path
                    qfont = font_db.font(family, styles[0], 9) # Point size doesn't matter much here
                    font_info = QFontInfo(qfont)
                    resolved_family = font_info.family()

                    # Attempt to get a reliable path (might not always work)
                    guessed_path = get_system_font_path(resolved_family) # Use our helper

                    if guessed_path and os.path.exists(guessed_path) and family not in self.font_family_to_path:
                         self.font_family_to_path[family] = guessed_path
                         self.font_combo.addItem(family)
                         # Check if this matches the initially determined font path
                         if not current_font_found_in_db and self.font_path and guessed_path.lower() == self.font_path.lower():
                              current_font_found_in_db = True # Found it via DB scan
                 except Exception as font_err:
                     logging.warning(f"Could not process/map font family '{family}': {font_err}")

        # Set the current selection in the combo box
        current_display_name = next((name for name, path in self.font_family_to_path.items() if path and self.font_path and path.lower() == self.font_path.lower()), None)
        if current_display_name:
             self.font_combo.setCurrentText(current_display_name)
        else:
             logging.warning(f"Could not find display name for current font path '{self.font_path}' in combo box.")


        self.font_combo.currentTextChanged.connect(self.updateFont)
        font_layout.addWidget(self.font_combo, 1)
        controls_layout.addLayout(font_layout)
        # --- End Font Selection ---


        # Font Size
        font_size_layout = QHBoxLayout()
        font_size_layout.addWidget(QLabel("Size:"))
        self.font_size_slider = QSlider(Qt.Horizontal)
        self.font_size_slider.setRange(8, 72)
        self.font_size_slider.setValue(self.font_size)
        self.font_size_slider.valueChanged.connect(self.updateFontSize)
        self.font_size_value_label = QLabel(f"{self.font_size}pt")
        self.font_size_value_label.setMinimumWidth(40)
        font_size_layout.addWidget(self.font_size_slider, 1)
        font_size_layout.addWidget(self.font_size_value_label)
        controls_layout.addLayout(font_size_layout)

        # Font Color
        font_color_layout = QHBoxLayout()
        font_color_label = QLabel("Text:")
        self.font_color_picker = ColorBarPicker(self.font_color, self)
        self.font_color_picker.colorChanged.connect(self.updateFontColor)
        font_color_layout.addWidget(font_color_label)
        font_color_layout.addWidget(self.font_color_picker)
        controls_layout.addLayout(font_color_layout)

        # Background Color
        bg_color_layout = QHBoxLayout()
        bg_color_label = QLabel("BG:")
        self.bg_color_picker = ColorBarPicker(self.bg_color_outer, self)
        self.bg_color_picker.colorChanged.connect(self.updateBgColor)
        bg_color_layout.addWidget(bg_color_label)
        bg_color_layout.addWidget(self.bg_color_picker)
        controls_layout.addLayout(bg_color_layout)

        main_layout.addWidget(controls_group)

        # --- Action Buttons (Modified as per previous request) ---
        button_layout = QHBoxLayout()
        self.reset_btn = QPushButton("Reset Styles")
        self.reset_btn.setToolTip("Reset colors and font to defaults")
        self.reset_btn.clicked.connect(self.resetStyles)

        self.close_btn = QPushButton("Close")
        self.close_btn.setToolTip("Save styles and close")
        self.close_btn.clicked.connect(self.accept) # Use accept() to close dialog

        button_layout.addWidget(self.reset_btn)
        button_layout.addStretch(1)
        button_layout.addWidget(self.close_btn) # Add the new Close button
        main_layout.addLayout(button_layout)
        # --- End Action Buttons Modification ---

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateImageDisplay() # Rescale pixmap on resize

    def updateFont(self, font_family):
        new_path = self.font_family_to_path.get(font_family)
        if new_path and os.path.exists(new_path):
            if self.font_path != new_path:
                 self.font_path = new_path
                 logging.debug(f"Viewer font updated to: {font_family}, Path: {self.font_path}")
                 self.renderTranslatedImage()
                 self.updateImageDisplay()
        else:
             # Handle case where "(Current Path)" might be selected but path became invalid
             if "(Current Path)" in font_family and self.font_path and os.path.exists(self.font_path):
                 logging.debug("Keeping current custom path font.")
             else:
                 logging.warning(f"Could not find valid path for font family '{font_family}'. Keeping previous: {self.font_path}")
                 # Optionally reset combo to the actual current font name?
                 current_display_name = next((name for name, path in self.font_family_to_path.items() if path and self.font_path and path.lower() == self.font_path.lower()), None)
                 if current_display_name:
                      self.font_combo.blockSignals(True)
                      self.font_combo.setCurrentText(current_display_name)
                      self.font_combo.blockSignals(False)

    def updateFontSize(self, value):
        if self.font_size != value:
             self.font_size = value
             self.font_size_value_label.setText(f"{value}pt")
             logging.debug(f"Viewer font size updated to: {self.font_size}")
             # Use a timer to avoid re-rendering on every tiny slider move
             if not hasattr(self, '_render_timer'):
                 self._render_timer = QTimer(self)
                 self._render_timer.setSingleShot(True)
                 self._render_timer.timeout.connect(self._delayedRenderUpdate)
             self._render_timer.start(200) # 200ms delay

    def _delayedRenderUpdate(self):
        """Slot for delayed rendering after slider changes."""
        self.renderTranslatedImage()
        self.updateImageDisplay()

    def updateFontColor(self, color):
        if self.font_color != color:
            self.font_color = color
            logging.debug(f"Viewer font color updated to: {self.font_color.name(QColor.NameFormat.HexArgb)}")
            self.renderTranslatedImage()
            self.updateImageDisplay()

    def updateBgColor(self, color):
        if self.bg_color_outer != color:
            self.bg_color_outer = color
            # Generate inner color slightly darker/more transparent based on outer
            h, s, v, a = color.getHsvF()
            new_v_inner = max(0, v * 0.9)
            new_a_inner = min(255, int(color.alpha() * 0.9)) # Ensure int
            self.bg_color_inner = QColor.fromHsvF(h, s, new_v_inner, new_a_inner / 255.0)
            logging.debug(f"Viewer BG color updated - Outer: {self.bg_color_outer.name(QColor.NameFormat.HexArgb)}, Inner: {self.bg_color_inner.name(QColor.NameFormat.HexArgb)}")
            self.renderTranslatedImage()
            self.updateImageDisplay()

    def resetStyles(self):
        logging.debug("Resetting viewer styles.")
        # Use defaults defined in __init__
        default_font_color_tuple = (0, 0, 255, 255) # Opaque Blue default
        default_bg_outer_tuple = (255, 255, 255, 200) # Whiteish default

        self.font_color = QColor(*default_font_color_tuple)
        self.bg_color_outer = QColor(*default_bg_outer_tuple)
        h, s, v, a = self.bg_color_outer.getHsvF()
        new_v_inner = max(0, v * 0.9)
        new_a_inner = min(255, int(self.bg_color_outer.alpha() * 0.9))
        self.bg_color_inner = QColor.fromHsvF(h, s, new_v_inner, new_a_inner / 255.0)

        # Reset color pickers
        self.font_color_picker.setColor(self.font_color)
        self.bg_color_picker.setColor(self.bg_color_outer)

        # Reset font based on target language originally passed
        parent_initial_size = self.parent().default_font_size if self.parent() else 20
        self.font_path = get_system_font_path(self.target_language_code)
        self.font_size = parent_initial_size

        # Final fallback if target language font not found
        if not self.font_path or not os.path.exists(self.font_path):
             self.font_path = get_system_font_path("default")

        logging.info(f"Resetting font to language/default: {self.font_path}, Size: {self.font_size}")

        # Update UI elements for font
        self.font_size_slider.setValue(self.font_size)
        self.font_size_value_label.setText(f"{self.font_size}pt")

        default_display_font = next((name for name, path in self.font_family_to_path.items() if path and self.font_path and path.lower() == self.font_path.lower()), None)
        if default_display_font:
             self.font_combo.blockSignals(True)
             self.font_combo.setCurrentText(default_display_font)
             self.font_combo.blockSignals(False)
        else:
             logging.warning(f"Could not find display name for reset font path '{self.font_path}' in combo box.")

        self.renderTranslatedImage()
        self.updateImageDisplay()

    def renderTranslatedImage(self):
        if not self.original_image:
             logging.error("renderTranslatedImage called with no original image loaded.")
             return
        image = self.original_image.copy()
        draw = ImageDraw.Draw(image)

        font_color_tuple = self.font_color.getRgb()
        bg_outer_tuple = self.bg_color_outer.getRgb()

        try:
            font = ImageFont.truetype(self.font_path, self.font_size)
        except IOError:
             logging.warning(f"Failed to load font '{self.font_path}' size {self.font_size}. Falling back.")
             fallback_path = get_system_font_path("default")
             try: font = ImageFont.truetype(fallback_path, self.font_size)
             except IOError:
                 logging.error("Failed to load even default fallback font. Using PIL default.")
                 font = ImageFont.load_default()
             logging.info(f"Using fallback font: {fallback_path if font != ImageFont.load_default() else 'PIL Default'}")

        if not self.boxes:
            # ... (no-text rendering logic should be okay, but double-check anchor usage) ...
            try:
                no_text_msg = "(No text detected in original image)"
                # Use anchor only if text is single line (which this is)
                text_anchor_nt = 'mm'

                try:
                    # textbbox should support anchor for single line text
                    bbox = draw.textbbox((image.width / 2, image.height / 2), no_text_msg, font=font, anchor=text_anchor_nt)
                    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    tx, ty = image.width / 2, image.height / 2
                except AttributeError: # Fallback for older Pillow
                    logging.debug("Using Pillow fallback for textbbox/anchor for no-text message.")
                    try:
                         tw = draw.textlength(no_text_msg, font=font)
                         th = self.font_size
                    except AttributeError:
                         bbox_legacy = font.getbbox(no_text_msg) if hasattr(font, 'getbbox') else (0, 0, 50, 10)
                         tw = bbox_legacy[2] - bbox_legacy[0]
                         th = bbox_legacy[3] - bbox_legacy[1]
                    tx, ty = (image.width - tw) / 2, (image.height - th) / 2
                    bbox = (tx, ty, tx + tw, ty + th)
                    text_anchor_nt = None # Cannot use anchor if calculated manually


                bg_pad = 5
                bg_coords = [(bbox[0] - bg_pad, bbox[1] - bg_pad), (bbox[2] + bg_pad, bbox[3] + bg_pad)]
                draw.rectangle(bg_coords, fill=bg_outer_tuple)
                # Use anchor only if available and text is single line
                draw.text((image.width / 2, image.height / 2) if text_anchor_nt == 'mm' else (tx, ty), no_text_msg, font=font, fill=font_color_tuple, anchor=text_anchor_nt)

            except Exception as e: logging.error(f"Error rendering no-text msg: {e}")

        else:
            for i, bbox_coords in enumerate(self.boxes):
                if i >= len(self.translated_lines): continue
                line = self.translated_lines[i].strip()
                if not line: continue

                left, top, right, bottom = bbox_coords
                box_w = right - left
                box_h = bottom - top
                if box_w <= 0 or box_h <= 0: continue

                avg_char_width = max(1, self.font_size * 0.5)
                wrap_width = max(5, int(box_w / avg_char_width))
                wrapped_lines = textwrap.wrap(line, width=wrap_width)
                rendered_text = "\n".join(wrapped_lines)
                is_multiline = '\n' in rendered_text # Check if wrapping actually occurred

                try:
                    # --- FIX: REMOVE anchor from textbbox call ---
                    # Calculate bbox starting from the original box's top-left
                    text_bbox = draw.textbbox((left, top), rendered_text, font=font, spacing=4) # NO ANCHOR
                    # --- END FIX ---

                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]

                    # Background calculation remains the same
                    bg_pad_x, bg_pad_y = 3, 2
                    bg_left = text_bbox[0] - bg_pad_x
                    bg_top = text_bbox[1] - bg_pad_y
                    bg_right = text_bbox[2] + bg_pad_x
                    bg_bottom = text_bbox[3] + bg_pad_y
                    bg_left = max(0, bg_left)
                    bg_top = max(0, bg_top)
                    bg_right = min(image.width, bg_right)
                    bg_bottom = min(image.height, bg_bottom)
                    outer_coords = [(bg_left, bg_top), (bg_right, bg_bottom)]
                    draw.rectangle(outer_coords, fill=bg_outer_tuple)

                    # --- FIX: REMOVE anchor from draw.text call (already done previously) ---
                    # Draw text at the calculated top-left of its bounding box.
                    draw.text((text_bbox[0], text_bbox[1]), rendered_text, font=font, fill=font_color_tuple, spacing=4) # NO ANCHOR
                    # --- END FIX ---

                except AttributeError: # Fallback for older Pillow without textbbox
                    # ... (Fallback logic remains the same, it shouldn't use anchor either) ...
                    logging.debug(f"Using Pillow fallback for textbbox for line {i+1}")
                    text_width = 0
                    if wrapped_lines:
                         try: text_width = draw.textlength(wrapped_lines[0], font=font)
                         except AttributeError:
                             bbox_legacy = font.getbbox(wrapped_lines[0]) if hasattr(font, 'getbbox') else (0,0,50,10)
                             text_width = bbox_legacy[2] - bbox_legacy[0]

                    text_height = self.font_size * len(wrapped_lines) + (4 * (len(wrapped_lines) -1) if wrapped_lines else 0)
                    text_bbox = (left, top, left + text_width, top + text_height)

                    bg_pad_x, bg_pad_y = 3, 2
                    bg_coords = [(left - bg_pad_x, top - bg_pad_y), (left + text_width + bg_pad_x, top + text_height + bg_pad_y)]
                    draw.rectangle(bg_coords, fill=bg_outer_tuple)
                    draw.text((left, top), rendered_text, font=font, fill=font_color_tuple, spacing=4) # Draw without anchor

                except Exception as e:
                     logging.error(f"Error rendering line {i+1} ('{line[:20]}...'): {e}", exc_info=True)

        self.rendered_image = image
        logging.debug("Image rendering complete.")
    def updateImageDisplay(self):
        if not self.rendered_image or not self.image_label: return
        try:
            im = self.rendered_image
            qimage = QImage(im.tobytes("raw", "RGBA"), im.width, im.height, QImage.Format.Format_RGBA8888)
            if qimage.isNull():
                 logging.error("Failed to create QImage from rendered PIL image.")
                 return
            pixmap = QPixmap.fromImage(qimage)

            # Scale pixmap to fit label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
        except Exception as e: logging.error(f"Error updating image display: {e}", exc_info=True)


    # --- REMOVED saveAndClose method ---

    def auto_save_image(self):
        """Automatically saves the rendered image to the support folder."""
        if self.rendered_image and self.save_on_close:
            try:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                ensure_support_folder()
                # Extract original filename base to make save name more relevant
                base_name = os.path.splitext(os.path.basename(self.image_path))[0]
                save_filename = f"{base_name}_translated_{timestamp}.png"
                save_path = os.path.join(SUPPORT_FOLDER, save_filename)

                logging.info(f"Auto-saving translated image to: {save_path}")
                # Save without alpha if possible, or ensure background isn't transparent if saving RGBA
                # For simplicity, save as PNG which handles alpha.
                self.rendered_image.save(save_path, format='PNG')
            except Exception as e:
                logging.error(f"Failed to auto-save image to {save_path}: {e}", exc_info=True)
                # Optionally inform user non-blockingly if save fails
                if self.parent() and hasattr(self.parent(), 'tray_icon') and self.parent().tray_icon and self.parent().tray_icon.isVisible():
                    self.parent().tray_icon.showMessage("Save Error", f"Failed to save {save_filename}.", QSystemTrayIcon.MessageIcon.Warning, 3000)
        elif not self.save_on_close:
            logging.debug("Auto-save skipped because save_on_close is False.")
        else:
             logging.warning("Auto-save skipped: No rendered image available.")

    def save_viewer_settings(self):
#        """Saves viewer settings and geometry to the config file."""
#        positions['viewer_settings'] = {
#            'font_color': self.font_color.getRgb(),
#            'bg_color_outer': self.bg_color_outer.getRgb(),
#            'bg_color_inner': self.bg_color_inner.getRgb(),
#            'font_path': self.font_path,
#            'font_size': self.font_size
#            }
#        positions['TranslatedImageViewer'] = { 'x': self.x(), 'y': self.y(), 'width': self.width(), 'height': self.height() }
#
#        # Call main save function
#        save_window_positions(positions)
#        logging.info("Viewer settings and geometry saved.")
        logging.debug("TranslatedImageViewer.save_viewer_settings called (no immediate save).")
    pass


    def load_viewer_geometry(self, positions): # Accept dict
        if 'TranslatedImageViewer' in positions:
            try:
                geo = positions['TranslatedImageViewer']
                if all(k in geo for k in ('x', 'y', 'width', 'height')):
                    self.setGeometry(int(geo['x']), int(geo['y']), int(geo['width']), int(geo['height']))
            except Exception as e: logging.error(f"Error loading viewer geometry: {e}.")

    def closeEvent(self, event):
        """Override close event to save settings and image automatically."""
        logging.debug("TranslatedImageViewer closeEvent triggered.")
        self.save_viewer_settings()
        self.auto_save_image()
        super().closeEvent(event)

    # Override accept and reject to ensure closeEvent logic runs
    def accept(self):
        logging.debug("TranslatedImageViewer accepted (closed).")
        # closeEvent will handle saving
        super().accept()

    def reject(self):
        logging.debug("TranslatedImageViewer rejected (closed).")
        # Set flag to prevent saving if rejected (e.g., by Esc key or error)
        # We decided save_on_close is mainly for load errors. Close always saves.
        # self.save_on_close = False
        super().reject()



# --- Main Application Execution ---
if __name__ == '__main__':
    # --- Exception Hook ---
    def excepthook(exc_type, exc_value, exc_tb):
        logging.critical("Unhandled exception caught:", exc_info=(exc_type, exc_value, exc_tb))
        import traceback
        tb_details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb, limit=15))
        error_msg = f"A critical error occurred:\n\n{exc_value}\n\nTraceback:\n{tb_details}"
        try:
             # Try showing a message box if GUI is available
             if QApplication.instance():
                 QMessageBox.critical(None, "Critical Application Error", error_msg)
             else:
                 print(f"CRITICAL ERROR (GUI not available):\n{error_msg}")
        except Exception as mb_error:
             print(f"Failed to show error message box: {mb_error}")
             print(f"CRITICAL ERROR:\n{error_msg}")
        # Use os._exit to force exit even if threads are running
        os._exit(1)

    sys.excepthook = excepthook

    # --- DPI Scaling Attributes ---
    if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
         QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
         QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    # --- Application Setup ---
    app_args = sys.argv if hasattr(sys, 'argv') else []
    app = QApplication(app_args)

    app.setApplicationName("OverlayTranslate")
    app.setOrganizationName("YourOrganization") # Optional

    # Set application icon
    icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        logging.warning(f"Application icon not found at {icon_path}")

    # Set default font
    default_font = QFont("Segoe UI", 9) if platform.system() == "Windows" else QFont("Roboto", 10)
    app.setFont(default_font)
    logging.info(f"Set application default font: {default_font.family()} {default_font.pointSize()}pt")

    # --- Instance Locking ---
    lock_file_path = os.path.join(tempfile.gettempdir(), "overlay_translate_instance.lock")
    lock_file = QtCore.QLockFile(lock_file_path)
    lock_file.setStaleLockTime(0) # Consider stale immediately if process crashed

    if not lock_file.tryLock(100): # Try locking for 100ms
        # Check if the lock failed because it's stale (owned by non-existent process)
        # Note: QLockFile error codes might differ slightly across Qt versions
        # We assume LockFailedError implies it *could* be stale or actively held
        is_stale = lock_file.error() in [QtCore.QLockFile.LockError.LockFailedError, QtCore.QLockFile.LockError.PermissionDeniedError] # Broader check might be needed

        if is_stale:
             logging.warning("Lock file exists. Checking if stale...")
             if lock_file.removeStaleLockFile():
                  logging.info("Stale lock file removed successfully.")
                  # Try locking again after removing stale lock
                  if not lock_file.tryLock(100):
                       QMessageBox.warning(None, "Already Running", "Another instance of Overlay Translate is already running (failed to re-acquire lock).")
                       sys.exit(0)
                  else:
                      logging.info("Acquired lock after removing stale file.")
             else:
                  # Could not remove stale lock, means another instance is likely running
                  QMessageBox.warning(None, "Already Running", "Another instance of Overlay Translate is already running (could not remove stale lock).")
                  sys.exit(0)
        else:
            # Lock failed and it wasn't considered stale - definitely another instance running
            QMessageBox.warning(None, "Already Running", "Another instance of Overlay Translate is already running.")
            sys.exit(0)
    logging.info(f"Acquired instance lock file: {lock_file_path}")


    # --- Ensure Support Folder Exists (Moved here for safety before logging/theme) ---
    ensure_support_folder()
    # --- END Ensure Support Folder ---


    # --- Load Theme EARLY and Apply Globally ONCE ---
    load_window_positions() # Loads theme into current_theme
    apply_theme()           # Apply the loaded/default theme to the app instance
    # --- END Apply Theme EARLY ---

    # --- Defer OCR Init ---
    logging.info("Initializing OCR Engine...")
    init_msg_box = QMessageBox(QMessageBox.Icon.Information, "Initializing", "Loading OCR engine, please wait...", QMessageBox.StandardButton.NoButton, None)
    init_msg_box.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowStaysOnTopHint)
    apply_theme() # Ensure message box is themed
    init_msg_box.show()
    QApplication.processEvents() # Make sure it displays

    # Initialize OCR based on saved source language if possible, else 'en'
    positions = load_window_positions()
    initial_ocr_lang = 'en' # Default
    # Check if control window settings exist and have language
    # Note: ControlWindow isn't created yet, so cannot access its state directly.
    # We rely on the config file.
    # If we add src/tgt lang saving, load it here. For now, default 'en'.
    # Example if source_language was saved in 'settings':
    # if 'settings' in positions and 'source_language' in positions['settings']:
    #     saved_lang = positions['settings']['source_language']
    #     if saved_lang != 'auto': # Don't init with 'auto'
    #         initial_ocr_lang = saved_lang

    initialize_paddle_ocr(initial_ocr_lang) # Initialize OCR here

    init_msg_box.accept() # Close the message box
    del init_msg_box # Clean up

    if not paddle_ocr: # Check if initialization failed
         logging.critical("OCR engine failed to initialize during startup.")
         QMessageBox.critical(None, "Initialization Error", "Failed to initialize the OCR engine. Please check logs. The application cannot start.")
         sys.exit(1)
    logging.info("OCR engine initialization complete.")
    # --- END Defer OCR Init ---

    # --- Main Execution ---
    control_window = None # Define outside try block for finally
    try:
        # Create the main window
        control_window = ControlWindow()

        # Re-apply Theme AFTER ControlWindow UI is built (ensure all widgets get styled)
        apply_theme()

        # Wait for Flask server readiness check (with refined logic)
        logging.info("Waiting for local translation server check...")
        server_wait_timeout = 15 # Increased timeout slightly to 15s
        server_ready_flag = False
        server_check_timed_out = False

        if hasattr(control_window, 'capture_widget') and control_window.capture_widget:
            # Wait for the event from the checker thread
            server_ready_flag = control_window.capture_widget.flask_server_ready.wait(timeout=server_wait_timeout)
            if not server_ready_flag:
                server_check_timed_out = True # Mark that the wait timed out

            # Log the outcome clearly
            if server_check_timed_out:
                logging.warning(f"Flask server readiness check timed out after {server_wait_timeout} seconds.")
            else:
                logging.info("Flask server readiness event received.")

            # Check if the server thread is *actually* running *after* the wait
            # This check is slightly less reliable if port was already in use
            if not control_window.capture_widget.flask_running and not server_check_timed_out:
                 # If wait *didn't* time out, but thread isn't running -> real problem
                 logging.error("Flask server thread is not running after readiness check completed.")
                 QMessageBox.warning(control_window, "Server Error", "Local translation server failed to start or stopped prematurely.\nOffline translation will not work.\nPlease check logs.")
            elif server_check_timed_out and not control_window.capture_widget.flask_running:
                 # Wait timed out AND thread isn't running -> Likely failed to start
                 logging.error("Flask server readiness check timed out and thread is not running.")
                 # Error message already shown in check_flask_server_readiness in this case
            elif server_check_timed_out and control_window.capture_widget.flask_running:
                 # If wait timed out BUT server is running, log it but don't block UI
                 logging.warning("Server check timed out, but server thread appears running. Proceeding cautiously.")
                 if control_window.tray_icon and control_window.tray_icon.isVisible():
                    control_window.tray_icon.showMessage("Server Status", "Could not confirm server status quickly. Offline translation might be delayed.", QSystemTrayIcon.MessageIcon.Warning, 4000)
            else:
                 # Event received and server is running (or port was already in use) - success/proceed
                 logging.info("Local translation server check confirmed successful or assumed running.")

        else:
             logging.error("Capture widget not initialized before server check.")
             QMessageBox.critical(None, "Startup Error", "Critical component (Capture Widget) failed to initialize.")
             sys.exit(1)


        control_window.show()
        exit_code = app.exec()
        logging.info(f"Application event loop finished with exit code: {exit_code}")
        sys.exit(exit_code)

    except Exception as main_err:
        logging.critical(f"Critical error during application startup or execution: {main_err}", exc_info=True)
        QMessageBox.critical(None, "Application Runtime Error", f"A critical error occurred:\n{main_err}")
        sys.exit(1)
    finally:
        # Ensure lock file is released on exit
        if 'lock_file' in locals() and lock_file.isLocked():
             lock_file.unlock()
             logging.info("Released instance lock file.")

        # Clean up temporary directory explicitly if control_window and capture_widget exist
        # Although capture_widget.cleanup() should handle it, this is a safeguard
        if control_window and hasattr(control_window, 'capture_widget') and control_window.capture_widget:
             temp_dir_path = control_window.capture_widget.tempDir
             if temp_dir_path and os.path.exists(temp_dir_path) and "OverlayTranslate_" in os.path.basename(temp_dir_path): # Safety check on name
                 try:
                     logging.info(f"Final cleanup check for temp dir: {temp_dir_path}")
                     # Reuse cleanup logic from CaptureWidget
                     control_window.capture_widget.cleanup()
                 except Exception as final_cleanup_err:
                     logging.error(f"Error during final temp dir cleanup: {final_cleanup_err}")


        logging.info("--- Application End ---")
