# utils/helpers.py
import os
import platform
import json
import logging
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import QApplication
from .config import (
    CONFIG_FILE, DEFAULT_THEME, logger, get_current_theme, update_current_theme,
    ai_api_config, PREDEFINED_THEMES # Import PREDEFINED_THEMES
)
import keyring # Keep keyring import here

# --- REVISED FUNCTION ---
def get_system_font_path(font_request):
    """
    Finds the path to a system font file based on a request (font name, language code, or 'default').
    Prioritizes fonts with broader coverage for mixed scripts.
    """
    system = platform.system()
    specific_font_path = None
    log_prefix = f"[get_system_font_path({font_request})]"

    # --- Font Definitions ---
    # OS-specific paths (Add more known good paths if needed)
    font_locations = {
        "Windows": {
            # Good Coverage / UI Fonts (Prioritized)
            "Segoe UI": r"C:\Windows\Fonts\segoeui.ttf",
            "Microsoft YaHei UI": r"C:\Windows\Fonts\msyh.ttc", # Good CJK + Latin
            "Malgun Gothic": r"C:\Windows\Fonts\malgun.ttf", # Korean + Latin
            "Yu Gothic UI": r"C:\Windows\Fonts\YuGothB.ttc", # Japanese + Latin (Bold variant often includes Regular)
            "Noto Sans": r"C:\Windows\Fonts\NotoSans-Regular.ttf", # Needs installation
            # Common Fallbacks
            "Arial": r"C:\Windows\Fonts\arial.ttf",
            "Times New Roman": r"C:\Windows\Fonts\times.ttf",
            # Specific Language (Less coverage maybe)
            "MS Gothic": r"C:\Windows\Fonts\msgothic.ttc",
            "SimSun": r"C:\Windows\Fonts\simsun.ttc",
        },
        "Darwin": { # macOS
            # Good Coverage / UI Fonts (Prioritized)
            "San Francisco": "/System/Library/Fonts/SFNS.ttf", # Default UI font has good coverage
            ".SF NS": "/System/Library/Fonts/SFNS.ttf", # Alias
            "Helvetica Neue": "/System/Library/Fonts/HelveticaNeue.ttc",
            "Noto Sans": "/Library/Fonts/NotoSans-Regular.ttf", # Needs installation
            "PingFang SC": "/System/Library/Fonts/PingFang.ttc", # Chinese
            "PingFang TC": "/System/Library/Fonts/PingFang.ttc", # Chinese TC
            "Hiragino Kaku Gothic ProN": "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", # Japanese
            "Apple SD Gothic Neo": "/System/Library/Fonts/AppleSDGothicNeo.ttc", # Korean
            # Common Fallbacks
            "Arial": "/Library/Fonts/Arial.ttf",
            "Times New Roman": "/Library/Fonts/Times New Roman.ttf",
        },
        "Linux": {
            # Good Coverage / UI Fonts (Prioritized)
            "Noto Sans": "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "Noto Sans CJK JP": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", # Example path
            "Noto Sans CJK KR": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "Noto Sans CJK SC": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "Noto Sans CJK TC": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "DejaVu Sans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", # Good fallback
            # Common Fallbacks
            "Ubuntu": "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
            "Liberation Sans": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "Arial": "/usr/share/fonts/truetype/msttcorefonts/arial.ttf", # If installed
            # Specific Language (Less coverage maybe)
            "WenQuanYi Micro Hei": "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", # Chinese fallback
            "TakaoPGothic": "/usr/share/fonts/truetype/takao-gothic/TakaoPGothic.ttf", # Japanese fallback
            "NanumGothic": "/usr/share/fonts/truetype/nanum/NanumGothic.ttf", # Korean fallback
        }
    }

    # Prioritized list of font *keys* (from font_locations) for language codes/default
    # Fonts earlier in the list are preferred if they exist.
    font_preferences = {
        # For CJK, prefer fonts known to bundle good Latin characters
        "zh": ["Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Noto Sans", "WenQuanYi Micro Hei", "SimSun", "default"],
        "ja": ["Yu Gothic UI", "Hiragino Kaku Gothic ProN", "Noto Sans CJK JP", "Noto Sans", "MS Gothic", "TakaoPGothic", "default"],
        "ko": ["Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans", "NanumGothic", "default"],
        # Aliases
        "ch": ["Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Noto Sans", "WenQuanYi Micro Hei", "SimSun", "default"],
        "zh-cn": ["Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Noto Sans", "WenQuanYi Micro Hei", "SimSun", "default"],
        "zh-tw": ["Microsoft YaHei UI", "PingFang TC", "Noto Sans CJK TC", "Noto Sans", "default"], # Prefer TC variant if specified
        # Default/English - prefer modern UI fonts with good coverage
        "default": ["Segoe UI", "San Francisco", ".SF NS", "Noto Sans", "Ubuntu", "DejaVu Sans", "Arial"],
        "en": ["Segoe UI", "San Francisco", ".SF NS", "Noto Sans", "Arial", "Helvetica Neue", "Times New Roman"],
        # Add other languages here if needed
    }

    os_font_map = font_locations.get(system, {})
    normalized_request = font_request.lower().strip()

    keys_to_try = []

    # 1. Check if the request is a direct font name known for this OS
    direct_match_key = next((key for key in os_font_map if key.lower() == normalized_request), None)
    if direct_match_key:
        path = os_font_map.get(direct_match_key)
        if path and os.path.exists(path):
            logger.debug(f"{log_prefix} Found direct match for font name '{direct_match_key}': {path}")
            specific_font_path = path
        else:
             logger.warning(f"{log_prefix} Direct match '{direct_match_key}' found but path '{path}' does not exist.")
             # Continue to language/default lookup if direct match fails

    # 2. If no valid direct match, check if it's a language hint or use default
    if not specific_font_path:
        if normalized_request in font_preferences:
            keys_to_try = font_preferences[normalized_request]
            logger.debug(f"{log_prefix} Using language/default preference list: {keys_to_try}")
        else:
            # Treat unknown requests as 'default'
            logger.debug(f"{log_prefix} Unknown request, falling back to 'default' preferences.")
            keys_to_try = font_preferences["default"]

        # Iterate through the preferred keys for the language/default
        for key in keys_to_try:
            if key == "default": # Avoid infinite recursion if "default" is in a list
                continue
            path = os_font_map.get(key)
            if path and os.path.exists(path):
                logger.debug(f"{log_prefix} Found preferred font '{key}' at: {path}")
                specific_font_path = path
                break # Found the best available preferred font

    # 3. If still no font found (e.g., none of the preferred exist), use the ultimate OS default
    if not specific_font_path:
        logger.debug(f"{log_prefix} No preferred or direct match found. Trying ultimate OS default.")
        # Get the 'default' list again and find the first existing one
        default_keys = font_preferences["default"]
        for key in default_keys:
             path = os_font_map.get(key)
             if path and os.path.exists(path):
                 logger.debug(f"{log_prefix} Using ultimate default font '{key}' at: {path}")
                 specific_font_path = path
                 break

    # 4. Final fallback if absolutely nothing is found (should be rare)
    if not specific_font_path or not os.path.exists(specific_font_path):
        fallback_font = "Arial" if system == "Windows" else "Sans" # Generic fallback names
        logger.error(f"{log_prefix} Critical: No valid font path found after all checks! Returning generic name: '{fallback_font}'. Text rendering may fail.")
        # NOTE: Pillow might still fail with just "Sans" on Linux/macOS if no fontconfig alias exists.
        # Returning *some* path, even if potentially wrong, is sometimes better. Let's try Arial/Times as last resort path.
        last_resort_path = os_font_map.get("Arial", os_font_map.get("Times New Roman"))
        if last_resort_path and os.path.exists(last_resort_path):
             logger.error(f"{log_prefix} Using last resort path: {last_resort_path}")
             return last_resort_path
        else: # Give up on paths, return the name
             return fallback_font

    logger.info(f"{log_prefix} Determined font path: {specific_font_path}")
    return specific_font_path
# --- END REVISED FUNCTION ---

def choose_font_for_text(text, default_font_family="Roboto", font_size=24):
    """Chooses a QFont based on detected script in the text."""
    # (This function remains unchanged - it's for Qt's QLabel, not Pillow)
    if not text:
        return QFont(default_font_family, font_size)
    if any('\u4e00' <= char <= '\u9fff' for char in text): # CJK Unified Ideographs
        font_name = "Microsoft YaHei UI" if platform.system() == "Windows" else "Noto Sans CJK SC"
        return QFont(font_name, font_size)
    elif any('\u3040' <= char <= '\u30ff' for char in text): # Hiragana/Katakana
        font_name = "Yu Gothic UI" if platform.system() == "Windows" else "Noto Sans CJK JP"
        return QFont(font_name, font_size)
    elif any('\uac00' <= char <= '\ud7af' for char in text): # Hangul Syllables
        font_name = "Malgun Gothic" if platform.system() == "Windows" else "Noto Sans CJK KR"
        return QFont(font_name, font_size)
    # Add other script checks if needed
    else:
        # Fallback to a font likely good for Latin/Default scripts
        default_os_font = "Segoe UI" if platform.system() == "Windows" else ("San Francisco" if platform.system() == "Darwin" else "Noto Sans")
        return QFont(default_os_font, font_size)


def load_settings():
    # (load_settings remains the same as previous correction)
    global ai_api_config
    settings = {}
    active_theme = DEFAULT_THEME
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f: settings = json.load(f)
            logger.info(f"Successfully loaded settings from {CONFIG_FILE}")
            saved_theme_name = settings.get('active_theme_name')
            if saved_theme_name and saved_theme_name in PREDEFINED_THEMES:
                active_theme = PREDEFINED_THEMES[saved_theme_name]
                logger.info(f"Loaded active theme: '{saved_theme_name}'")
            elif saved_theme_name:
                logger.warning(f"Saved theme name '{saved_theme_name}' not found. Using default.")
            else: logger.info("No active theme name found. Using default theme.")
            update_current_theme(active_theme)
            loaded_ai_config_data = settings.get('ai_api_config')
            current_ai_config = {"provider": None, "endpoint": None, "key_stored": False}
            if loaded_ai_config_data and isinstance(loaded_ai_config_data, dict):
                 current_ai_config["provider"] = loaded_ai_config_data.get("provider", None)
                 current_ai_config["endpoint"] = loaded_ai_config_data.get("endpoint", None)
                 if current_ai_config["provider"] in ["OpenAI", "LM Studio"]:
                      try:
                          if keyring.get_password("OverlayTranslate", current_ai_config["provider"]): current_ai_config["key_stored"] = True
                      except Exception as key_err: logger.warning(f"Could not check keyring for {current_ai_config['provider']} key: {key_err}")
                 logger.info(f"Loaded AI Config: Provider={current_ai_config['provider']}, Endpoint={current_ai_config['endpoint']}, KeyStored={current_ai_config['key_stored']}")
            else: logger.info("No AI API config found. Using defaults.")
            ai_api_config.update(current_ai_config)
        except Exception as e:
            logger.error(f"Failed to load/process config from {CONFIG_FILE}: {e}. Using defaults.", exc_info=True)
            settings = {}; update_current_theme(DEFAULT_THEME)
            ai_api_config.update({"provider": None, "endpoint": None, "key_stored": False})
    else:
        logger.info("Config file not found. Using default theme and settings.")
        settings = {}; update_current_theme(DEFAULT_THEME)
    return settings

def save_settings(settings_dict):
    # (save_settings remains the same as previous correction)
    try:
        active_theme_dict = get_current_theme()
        active_theme_name = active_theme_dict.get("name", DEFAULT_THEME["name"])
        settings_dict['active_theme_name'] = active_theme_name
        if 'theme' in settings_dict: del settings_dict['theme']
        settings_dict['ai_api_config'] = { "provider": ai_api_config.get("provider"), "endpoint": ai_api_config.get("endpoint") }
        logger.debug(f"Attempting to save settings dictionary to {CONFIG_FILE}.")
        viewer_settings_to_save = settings_dict.get('viewer_settings')
        if viewer_settings_to_save: logger.debug(f"Viewer settings being saved: {viewer_settings_to_save}")
        else: logger.debug("No viewer_settings key found in the dictionary to be saved.")
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(settings_dict, f, indent=4, ensure_ascii=False)
        logger.info(f"Settings (including active theme name '{active_theme_name}') saved successfully to {CONFIG_FILE}.")
    except Exception as e:
        logger.error(f"Failed to save settings to {CONFIG_FILE}: {e}", exc_info=True)
# ... (Keep generate_stylesheet and apply_theme functions) ...

def generate_stylesheet(theme_colors):
    # (This function remains unchanged)
    # ... (copy the function from the previous correct version) ...
    colors = theme_colors
    stylesheet_template = f"""
        QDialog, QMainWindow {{
            background-color: {colors.get('bg_main', '#C8141414')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            font-family: 'Roboto', Arial, sans-serif;
            border-radius: 15px;
        }}
        QLabel {{
            color: {colors.get('text_accent', '#FF00FFCC')};
            font-size: 14px;
            background-color: transparent;
        }}
         QLabel[objectName="DefaultTextLabel"] {{
            color: {colors.get('text_light', '#FFE0E0E0')};
        }}
         QLabel#ControlWindowLiveLabel {{ /* Style for preview label in ControlWindow */
            border-radius: 10px;
            padding: 15px;
            font-size: 16px; /* Base size, can be overridden */
            min-height: 50px;
            background-color: {colors.get('bg_input', '#961E1E1E')}; /* Use input background */
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            color: {colors.get('text_accent', '#FF00FFCC')}; /* Use accent color */
        }}
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {colors.get('grad_button_start', '#FF4A90E2')}, stop:1 {colors.get('grad_button_end', '#FF00FFCC')});
            color: {colors.get('text_button', '#FFFFFFFF')};
            border-radius: 10px;
            padding: 10px 12px; /* Adjusted padding */
            font-size: 14px;
            font-weight: 600;
            border: none;
            min-height: 30px; /* Ensure minimum button height */
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {colors.get('grad_button_hover_start', '#FF5AA1F2')}, stop:1 {colors.get('grad_button_hover_end', '#FF00FFDD')});
        }}
        QPushButton:pressed {{
            background: {colors.get('grad_button_pressed', '#FF357ABD')};
            padding-top: 12px; /* Adjust padding slightly on press */
            padding-bottom: 8px;
        }}
        QPushButton:disabled {{
            background: rgba(120, 120, 120, 100);
            color: {colors.get('text_disabled', '#64FFFFFF')};
        }}
        /* Style for AI Toggle Button */
        QPushButton[aiActive="true"] {{
             background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2ecc71, stop:1 #27ae60); /* Green */
        }}
         QPushButton[aiActive="true"]:hover {{
             background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3edf81, stop:1 #38bf71);
        }}
         QPushButton[aiActive="true"]:pressed {{
             background: #27ae60;
        }}
        /* Style for Live Button */
        QPushButton[liveActive="true"] {{
             background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e74c3c, stop:1 #c0392b); /* Red */
        }}
         QPushButton[liveActive="true"]:hover {{
             background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f75c4c, stop:1 #d1483b);
        }}
         QPushButton[liveActive="true"]:pressed {{
             background: #c0392b;
        }}

        QCheckBox {{
            color: {colors.get('text_light', '#FFE0E0E0')};
            font-size: 14px;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px; height: 16px; border-radius: 4px;
            border: 1px solid {colors.get('border_medium', '#32FFFFFF')};
            background-color: {colors.get('bg_input', '#961E1E1E')};
        }}
        QCheckBox::indicator:checked {{
            background-color: {colors.get('checkbox_checked', '#FF00FFCC')};
            border: 1px solid {colors.get('checkbox_checked', '#FF00FFCC')};
        }}
        QCheckBox::indicator:hover {{
            border: 1px solid {colors.get('border_accent', '#FF00FFCC')};
        }}
        QLineEdit {{
            background: {colors.get('bg_input', '#961E1E1E')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 6px;
            padding: 8px;
            font-size: 14px;
        }}
        QLineEdit:focus {{
            border: 1px solid {colors.get('border_accent', '#FF00FFCC')};
        }}
        QGroupBox {{
            color: {colors.get('text_accent', '#FF00FFCC')};
            font-size: 16px; font-weight: 600;
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 10px; margin-top: 12px;
            padding-top: 25px; padding-bottom: 10px; padding-left: 10px; padding-right: 10px;
            background: {colors.get('bg_groupbox', '#961E1E1E')};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 6px 12px; color: {colors.get('text_accent', '#FF00FFCC')};
            margin-left: 10px; margin-top: 3px;
            background-color: {colors.get('bg_titlebar', '#C8282828')};
            border-radius: 5px;
        }}
        QTextEdit {{
            background: {colors.get('bg_input', '#961E1E1E')};
            color: {colors.get('text_light', '#FFE0E0E0')}; /* Usually light text for editing */
            font-family: 'Roboto Mono', 'Courier New', monospace; font-size: 14px;
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 10px; padding: 12px;
        }}
        QSlider::groove:horizontal {{
            height: 6px; background: rgba(255, 255, 255, 20);
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, stop:0 #ffffff, stop:1 {colors.get('text_secondary', '#FF4A90E2')});
            width: 16px; height: 16px; border-radius: 8px; margin: -5px 0;
        }}
        QSlider::sub-page:horizontal {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {colors.get('grad_slider_start', '#FF4A90E2')}, stop:1 {colors.get('grad_slider_end', '#FF00FFCC')});
            border-radius: 3px;
        }}
        QComboBox {{
            background: {colors.get('bg_input', '#961E1E1E')};
            color: {colors.get('text_accent', '#FF00FFCC')};
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 6px; padding: 5px; min-height: 20px;
        }}
        QComboBox:hover {{ border: 1px solid {colors.get('border_accent', '#FF00FFCC')}; }}
        QComboBox::drop-down {{ border: none; background: transparent; width: 20px; }}
        QComboBox::down-arrow {{ image: none; }} /* Consider adding a themeable arrow */
        QComboBox QAbstractItemView {{
            background: {colors.get('bg_menu', '#C8141414')};
            color: {colors.get('text_accent', '#FF00FFCC')};
            selection-background-color: {colors.get('bg_menu_item_sel', '#FF4A90E2')};
            selection-color: {colors.get('text_button', '#FFFFFFFF')};
            border: 1px solid {colors.get('border_medium', '#32FFFFFF')};
            border-radius: 5px; padding: 5px; outline: 0px;
        }}
        QProgressBar {{
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 6px; background: {colors.get('bg_input', '#961E1E1E')};
            color: {colors.get('text_light', '#FFE0E0E0')}; text-align: center;
            font-size: 12px; height: 18px;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {colors.get('progress_chunk_start', '#FF4A90E2')}, stop:1 {colors.get('progress_chunk_end', '#FF00FFCC')});
            border-radius: 5px; margin: 1px;
        }}
        QMenuBar {{
            background: {colors.get('bg_main', '#C8141414')};
            color: {colors.get('text_accent', '#FF00FFCC')};
            font-size: 14px; font-family: 'Roboto', Arial, sans-serif;
        }}
        QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
        QMenuBar::item:selected {{ background: {colors.get('bg_menu_item_sel', '#FF4A90E2')}; color: {colors.get('text_button', '#FFFFFFFF')}; }}
        QMenu {{
            background: {colors.get('bg_menu', '#C8141414')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            border: 1px solid {colors.get('border_menu', '#14FFFFFF')};
            border-radius: 8px; padding: 5px;
        }}
        QMenu::item {{ padding: 6px 25px; border-radius: 0px; }}
        /* Style for selected menu items - uses ActionGroup for check state */
        QMenu::item:checked {{
             font-weight: bold;
             background-color: {colors.get('bg_menu_item_sel', '#FF4A90E2')};
             color: {colors.get('text_button', '#FFFFFFFF')};
        }}
        QMenu::item:selected {{ /* Hover style for non-checked items */
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {colors.get('grad_button_start', '#FF4A90E2')}, stop:1 {colors.get('grad_button_end', '#FF00FFCC')});
            color: {colors.get('text_button', '#FFFFFFFF')};
        }}
        QMenu::separator {{ height: 1px; background: {colors.get('border_light', '#14FFFFFF')}; margin: 5px 0; }}
        QToolTip {{
            background-color: {colors.get('bg_tooltip', '#F032323C')};
            color: {colors.get('text_tooltip', '#FFF0F0F0')};
            border: 1px solid {colors.get('border_medium', '#32FFFFFF')};
            padding: 5px;
            border-radius: 4px;
            opacity: 230;
        }}
        QDialog#LiveTranslationWindow {{
             background-color: {colors.get('bg_groupbox', '#961E1E1E')};
             border: 1px solid {colors.get('border_accent', '#FF00FFCC')};
             border-radius: 8px;
        }}
        QLabel#LiveLabel {{
             color: {colors.get('text_accent', '#FF00FFCC')};
             background-color: transparent;
             padding: 8px;
             font-weight: normal;
             border: none;
        }}

                /* --- ADDED Rule for Live Popout Window --- */
        QDialog#LiveTranslationWindow {{
             /* Use a semi-transparent version of the groupbox color */
             background-color: {QColor(colors.get('bg_groupbox', '#961E1E1E')).lighter(110).name(QColor.NameFormat.HexArgb)};
             border: 1px solid {colors.get('border_accent', '#FF00FFCC')};
             border-radius: 8px; /* Optional: Rounded corners */
        }}
        /* --- END ADDED Rule --- */

        /* Style for the label INSIDE the popout */
        QDialog#LiveTranslationWindow QLabel#LiveLabel {{
             color: {colors.get('text_accent', '#FF00FFCC')};
             background-color: transparent; /* Label itself is transparent */
             padding: 8px; /* Padding inside the dialog */
             font-weight: normal;
             border: none; /* No border on the label */
             border-radius: 0px; /* Label shouldn't have rounded corners */
        }}
        /* Status bar style */
        QStatusBar {{
            background: {colors.get('bg_titlebar', '#C8282828')};
            color: {colors.get('text_secondary', '#FF4A90E2')};
            font-size: 12px;
            padding-left: 5px;
        }}
        QStatusBar::item {{
            border: none;
            margin: 0 2px;
        }}
        /* Style for Resource Monitor Widgets in Status Bar */
        QStatusBar QProgressBar {{
             border: 1px solid #555555; border-radius: 3px;
             background-color: #333333; text-align: center;
             color: white; font-size: 9px;
             max-height: 14px;
             min-width: 60px;
        }}
        QStatusBar QProgressBar::chunk {{
             border-radius: 2px; margin: 1px;
        }}
        QStatusBar QLabel {{
             color: #cccccc;
             background-color: transparent;
             font-size: 11px;
             padding: 0 2px;
        }}
    """
    return stylesheet_template


def apply_theme():
    # (This function remains unchanged)
    # ... (copy the function from the previous correct version) ...
    try:
        theme_data = get_current_theme() # Use the getter
        if not isinstance(theme_data, dict) or "colors" not in theme_data:
            logger.error("Invalid theme structure found. Reverting to default.")
            theme_data = DEFAULT_THEME
            update_current_theme(theme_data) # Update central store

        stylesheet = generate_stylesheet(theme_data["colors"])
        app_instance = QApplication.instance()
        if app_instance:
            app_instance.setStyleSheet(stylesheet)
            logger.info(f"Applied theme: {theme_data.get('name', 'Unnamed')}")
        else:
            logger.warning("Cannot apply theme: No QApplication instance exists.")
    except Exception as e:
        logger.error(f"Failed to apply theme: {e}", exc_info=True)
        try:
             logger.warning("Attempting to apply default theme as fallback.")
             stylesheet = generate_stylesheet(DEFAULT_THEME["colors"])
             app_instance = QApplication.instance()
             if app_instance:
                 app_instance.setStyleSheet(stylesheet)
                 logger.warning("Fell back to default theme due to error.")
                 update_current_theme(DEFAULT_THEME) # Update central store
        except Exception as fallback_e:
             logger.error(f"Failed to apply even default theme: {fallback_e}")
    """Applies the current_theme stylesheet to the application."""
    try:
        theme_data = get_current_theme() # Use the getter
        if not isinstance(theme_data, dict) or "colors" not in theme_data:
            logger.error("Invalid theme structure found. Reverting to default.")
            theme_data = DEFAULT_THEME
            update_current_theme(theme_data) # Update central store

        stylesheet = generate_stylesheet(theme_data["colors"])
        app_instance = QApplication.instance()
        if app_instance:
            app_instance.setStyleSheet(stylesheet)
            logger.info(f"Applied theme: {theme_data.get('name', 'Unnamed')}")
        else:
            logger.warning("Cannot apply theme: No QApplication instance exists.")
    except Exception as e:
        logger.error(f"Failed to apply theme: {e}", exc_info=True)
        # Fallback to default stylesheet if generation fails
        try:
             logger.warning("Attempting to apply default theme as fallback.")
             stylesheet = generate_stylesheet(DEFAULT_THEME["colors"])
             app_instance = QApplication.instance()
             if app_instance:
                 app_instance.setStyleSheet(stylesheet)
                 logger.warning("Fell back to default theme due to error.")
                 update_current_theme(DEFAULT_THEME) # Update central store
        except Exception as fallback_e:
             logger.error(f"Failed to apply even default theme: {fallback_e}")