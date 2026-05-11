# utils/helpers.py
"""
Legacy helper functions for settings, theme, and font management.

DEPRECATION NOTE:
- load_settings() and save_settings() are now WRAPPERS around SettingsManager
- New code should use: from utils.settings_manager import get_settings_manager
- These wrappers maintain backward compatibility during migration
- Font and theme utilities (choose_font_for_text, apply_theme, etc.) remain here
"""

import os
import platform
import json
import logging
from typing import Dict, Optional, Any
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import QApplication
from .config import (
    CONFIG_FILE, DEFAULT_THEME, logger, get_current_theme, update_current_theme,
    PREDEFINED_THEMES
)
from .settings_manager import get_settings_manager
import sys

def get_system_font_path(font_request: str) -> str:
    """
    Finds the path to a system font file based on a request (font name, language code, or 'default').
    Prioritizes fonts with broader coverage for mixed scripts.
    """
    system = platform.system()
    specific_font_path = None
    log_prefix = f"[get_system_font_path({font_request})]"

    font_locations = {
        "Windows": {
            "Segoe UI": r"C:\Windows\Fonts\segoeui.ttf", "Microsoft YaHei UI": r"C:\Windows\Fonts\msyh.ttc",
            "Malgun Gothic": r"C:\Windows\Fonts\malgun.ttf", "Yu Gothic UI": r"C:\Windows\Fonts\YuGothB.ttc",
            "Noto Sans": r"C:\Windows\Fonts\NotoSans-Regular.ttf", "Arial": r"C:\Windows\Fonts\arial.ttf",
            "Times New Roman": r"C:\Windows\Fonts\times.ttf", "MS Gothic": r"C:\Windows\Fonts\msgothic.ttc",
            "SimSun": r"C:\Windows\Fonts\simsun.ttc",
        },
        "Darwin": {
            "San Francisco": "/System/Library/Fonts/SFNS.ttf", ".SF NS": "/System/Library/Fonts/SFNS.ttf",
            "Helvetica Neue": "/System/Library/Fonts/HelveticaNeue.ttc", "Noto Sans": "/Library/Fonts/NotoSans-Regular.ttf",
            "PingFang SC": "/System/Library/Fonts/PingFang.ttc", "Hiragino Kaku Gothic ProN": "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "Apple SD Gothic Neo": "/System/Library/Fonts/AppleSDGothicNeo.ttc", "Arial": "/Library/Fonts/Arial.ttf",
        },
        "Linux": {
            "Noto Sans": "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "Noto Sans CJK JP": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "DejaVu Sans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "Ubuntu": "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        }
    }
    font_preferences = {
        "zh": ["Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Noto Sans", "WenQuanYi Micro Hei", "SimSun", "default"],
        "ja": ["Yu Gothic UI", "Hiragino Kaku Gothic ProN", "Noto Sans CJK JP", "Noto Sans", "MS Gothic", "TakaoPGothic", "default"],
        "ko": ["Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans", "NanumGothic", "default"],
        "ch": ["Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Noto Sans", "WenQuanYi Micro Hei", "SimSun", "default"],
        "zh-cn": ["Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Noto Sans", "WenQuanYi Micro Hei", "SimSun", "default"],
        "zh-tw": ["Microsoft YaHei UI", "PingFang TC", "Noto Sans CJK TC", "Noto Sans", "default"],
        "default": ["Segoe UI", "San Francisco", ".SF NS", "Noto Sans", "Ubuntu", "DejaVu Sans", "Arial"],
        "en": ["Segoe UI", "San Francisco", ".SF NS", "Noto Sans", "Arial", "Helvetica Neue", "Times New Roman"],
    }

    os_font_map = font_locations.get(system, {})
    normalized_request = font_request.lower().strip()

    direct_match_key = next((key for key in os_font_map if key.lower() == normalized_request), None)
    if direct_match_key:
        path = os_font_map.get(direct_match_key)
        if path and os.path.exists(path):
            specific_font_path = path
        else:
             logger.warning(f"{log_prefix} Direct match '{direct_match_key}' found but path '{path}' does not exist.")

    if not specific_font_path:
        keys_to_try = font_preferences.get(normalized_request, font_preferences["default"])
        for key in keys_to_try:
            if key == "default": continue
            path = os_font_map.get(key)
            if path and os.path.exists(path):
                specific_font_path = path
                break

    if not specific_font_path:
        default_keys = font_preferences["default"]
        for key in default_keys:
             path = os_font_map.get(key)
             if path and os.path.exists(path):
                 specific_font_path = path
                 break

    if not specific_font_path or not os.path.exists(specific_font_path):
        fallback_font = "Arial" if system == "Windows" else "Sans"
        logger.error(f"{log_prefix} Critical: No valid font path found! Returning generic name: '{fallback_font}'.")
        last_resort_path = os_font_map.get("Arial", os_font_map.get("Times New Roman"))
        return last_resort_path if last_resort_path and os.path.exists(last_resort_path) else fallback_font

    logger.debug(f"{log_prefix} Determined font path: {specific_font_path}")
    return specific_font_path

def choose_font_for_text(text: str, default_font_family: str = "Roboto", font_size: int = 24) -> QFont:
    """
    Select appropriate font based on text content (character scripts).
    
    Detects CJK characters (Chinese, Japanese, Korean) and selects platform-specific
    fonts with proper glyph coverage. Falls back to default OS fonts for other scripts.
    
    Args:
        text (str): Text to analyze for font selection
        default_font_family (str, optional): Fallback font family. Defaults to "Roboto".
        font_size (int, optional): Font size in points. Defaults to 24.
        
    Returns:
        QFont: QFont object configured for the detected script
        
    Examples:
        >>> choose_font_for_text("Hello")  # Returns Segoe UI on Windows
        >>> choose_font_for_text("你好")   # Returns Microsoft YaHei UI on Windows
        >>> choose_font_for_text("こんにちは")  # Returns Yu Gothic UI on Windows
    """
    if not text:
        return QFont(default_font_family, font_size)
    if any('\u4e00' <= char <= '\u9fff' for char in text):
        font_name = "Microsoft YaHei UI" if platform.system() == "Windows" else "Noto Sans CJK SC"
    elif any('\u3040' <= char <= '\u30ff' for char in text):
        font_name = "Yu Gothic UI" if platform.system() == "Windows" else "Noto Sans CJK JP"
    elif any('\uac00' <= char <= '\ud7af' for char in text):
        font_name = "Malgun Gothic" if platform.system() == "Windows" else "Noto Sans CJK KR"
    else:
        default_os_font = "Segoe UI" if platform.system() == "Windows" else ("San Francisco" if platform.system() == "Darwin" else "Noto Sans")
        font_name = default_os_font
    return QFont(font_name, font_size)

def load_settings() -> Dict[str, Any]:
    """
    Legacy wrapper: Loads settings via SettingsManager and returns as dict.
    Maintains backward compatibility with existing code.
    """
    settings_manager = get_settings_manager()
    settings = settings_manager.get_all()
    
    # --- Load Theme ---
    active_theme = None
    saved_theme_data = settings.get('active_theme_data')
    if isinstance(saved_theme_data, dict):
        active_theme = saved_theme_data
    else:
        saved_theme_name = settings.get('active_theme_name')
        if saved_theme_name and saved_theme_name in PREDEFINED_THEMES:
            active_theme = PREDEFINED_THEMES[saved_theme_name]
    
    update_current_theme(active_theme if active_theme else DEFAULT_THEME)

    return settings

def save_settings(settings_dict: Dict[str, Any]) -> None:
    """
    Legacy wrapper: Saves settings via SettingsManager.
    Enriches the dict with current theme before saving.
    """
    try:
        # 1. Enrich with current theme data
        settings_dict['active_theme_data'] = get_current_theme()
        settings_dict.pop('active_theme_name', None)

        # 2. Use SettingsManager to persist settings
        settings_manager = get_settings_manager()
        settings_manager.update(settings_dict, save=True)

        logger.info(f"Settings saved successfully via SettingsManager.")

    except Exception as e:
        logger.error(f"Failed to save settings: {e}", exc_info=True)


def generate_stylesheet(theme_colors: Dict[str, str]) -> str:
    """
    Generate complete Qt stylesheet from theme color dictionary.
    
    Creates CSS-like stylesheet for all Qt widgets in the application,
    including gradients, borders, hover effects, and custom widget styles.
    Supports transparency via ARGB hex color format.
    
    Args:
        theme_colors (dict): Theme color dictionary with keys like:
            - 'bg_main', 'bg_input', 'bg_groupbox', 'bg_titlebar'
            - 'text_light', 'text_accent', 'text_secondary'
            - 'border_light', 'border_accent'
            - 'grad_button_start', 'grad_button_end'
            
    Returns:
        str: Complete Qt stylesheet string ready for QApplication.setStyleSheet()
        
    Note:
        Color format is Qt-compatible ARGB hex: #AARRGGBB
        Alpha channel: FF = opaque, 00 = transparent
    """
    colors = theme_colors

    # Compute derived hover/focus colors from accent
    accent_c = QColor(colors.get('border_accent', '#FF00FFCC'))
    hover_rgba = f"rgba({accent_c.red()}, {accent_c.green()}, {accent_c.blue()}, 25)"
    hover_strong = f"rgba({accent_c.red()}, {accent_c.green()}, {accent_c.blue()}, 40)"
    focus_glow = f"rgba({accent_c.red()}, {accent_c.green()}, {accent_c.blue()}, 60)"

    secondary_c = QColor(colors.get('text_secondary', '#FF4A90E2'))
    status_accent = f"rgba({secondary_c.red()}, {secondary_c.green()}, {secondary_c.blue()}, 200)"

    return f"""
        /* ================================================================
           OverlayTranslate — Global Theme Stylesheet
           ================================================================ */

        /* === Base Windows === */
        QDialog, QMainWindow {{
            background-color: {colors.get('bg_main', '#C8141414')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            font-family: 'Segoe UI', 'Roboto', Arial, sans-serif;
            border-radius: 12px;
        }}

        /* === Labels === */
        QLabel {{
            color: {colors.get('text_accent', '#FF00FFCC')};
            font-size: 13px;
            background-color: transparent;
        }}
        QLabel[objectName="DefaultTextLabel"] {{
            color: {colors.get('text_light', '#FFE0E0E0')};
        }}
        QLabel#ControlWindowLiveLabel {{
            border-radius: 10px;
            padding: 15px;
            font-size: 16px;
            min-height: 50px;
            background-color: {colors.get('bg_input', '#961E1E1E')};
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            color: {colors.get('text_accent', '#FF00FFCC')};
        }}

        /* === Buttons === */
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {colors.get('grad_button_start', '#FF4A90E2')},
                stop:1 {colors.get('grad_button_end', '#FF00FFCC')});
            color: {colors.get('text_button', '#FFFFFFFF')};
            border-radius: 8px;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 600;
            border: none;
            min-height: 30px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {colors.get('grad_button_hover_start', '#FF5AA1F2')},
                stop:1 {colors.get('grad_button_hover_end', '#FF00FFDD')});
        }}
        QPushButton:pressed {{
            background: {colors.get('grad_button_pressed', '#FF357ABD')};
            padding-top: 10px;
            padding-bottom: 6px;
        }}
        QPushButton:disabled {{
            background: rgba(120, 120, 120, 100);
            color: {colors.get('text_disabled', '#64FFFFFF')};
        }}
        /* AI Toggle Active */
        QPushButton[aiActive="true"] {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2ecc71, stop:1 #27ae60);
        }}
        QPushButton[aiActive="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3edf81, stop:1 #38bf71);
        }}
        QPushButton[aiActive="true"]:pressed {{ background: #27ae60; }}
        /* Live Capture Active */
        QPushButton[liveActive="true"] {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e74c3c, stop:1 #c0392b);
        }}
        QPushButton[liveActive="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f75c4c, stop:1 #d1483b);
        }}
        QPushButton[liveActive="true"]:pressed {{ background: #c0392b; }}

        /* === Checkboxes === */
        QCheckBox {{
            color: {colors.get('text_light', '#FFE0E0E0')};
            font-size: 13px;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 18px; height: 18px; border-radius: 4px;
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
        /* === Radio Buttons === */
        QRadioButton {{
            color: {colors.get('text_light', '#FFE0E0E0')};
            font-size: 13px;
            spacing: 8px;
        }}
        QRadioButton::indicator {{
            width: 18px; height: 18px; border-radius: 9px;
            border: 2px solid {colors.get('border_medium', '#32FFFFFF')};
            background-color: {colors.get('bg_input', '#961E1E1E')};
        }}
        QRadioButton::indicator:checked {{
            background-color: {colors.get('checkbox_checked', '#FF00FFCC')};
            border: 2px solid {colors.get('border_accent', '#FF00FFCC')};
        }}
        QRadioButton::indicator:hover {{
            border: 2px solid {colors.get('border_accent', '#FF00FFCC')};
        }}

        /* === Text Inputs === */
        QLineEdit {{
            background: {colors.get('bg_input', '#961E1E1E')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 6px;
            padding: 7px 10px;
            font-size: 13px;
            selection-background-color: {colors.get('bg_menu_item_sel', '#FF4A90E2')};
            selection-color: {colors.get('text_button', '#FFFFFFFF')};
        }}
        QLineEdit:focus {{
            border: 1px solid {colors.get('border_accent', '#FF00FFCC')};
        }}
        QTextEdit {{
            background: {colors.get('bg_input', '#961E1E1E')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
            font-size: 13px;
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 8px;
            padding: 10px;
            selection-background-color: {colors.get('bg_menu_item_sel', '#FF4A90E2')};
            selection-color: {colors.get('text_button', '#FFFFFFFF')};
        }}
        QTextEdit:focus {{
            border: 1px solid {colors.get('border_accent', '#FF00FFCC')};
        }}

        /* === Spin Boxes === */
        QSpinBox, QDoubleSpinBox {{
            background: {colors.get('bg_input', '#961E1E1E')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 13px;
            min-height: 24px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 1px solid {colors.get('border_accent', '#FF00FFCC')};
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button,
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            background: transparent;
            border: none;
            width: 16px;
        }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: none; }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: none; }}

        /* === Time Edit === */
        QTimeEdit {{
            background: {colors.get('bg_input', '#961E1E1E')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 13px;
        }}
        QTimeEdit:focus {{
            border: 1px solid {colors.get('border_accent', '#FF00FFCC')};
        }}

        /* === Group Boxes === */
        QGroupBox {{
            color: {colors.get('text_accent', '#FF00FFCC')};
            font-size: 14px; font-weight: 600;
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 10px; margin-top: 14px;
            padding-top: 24px; padding-bottom: 10px;
            padding-left: 12px; padding-right: 12px;
            background: {colors.get('bg_groupbox', '#961E1E1E')};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 5px 14px; color: {colors.get('text_accent', '#FF00FFCC')};
            margin-left: 10px; margin-top: 3px;
            background-color: {colors.get('bg_titlebar', '#C8282828')};
            border-radius: 6px;
            font-weight: 700;
        }}

        /* === Sliders === */
        QSlider::groove:horizontal {{
            height: 6px;
            background: {colors.get('bg_input', '#961E1E1E')};
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                stop:0 #ffffff,
                stop:1 {colors.get('text_secondary', '#FF4A90E2')});
            width: 18px; height: 18px; border-radius: 9px; margin: -6px 0;
            border: 1px solid {colors.get('border_medium', '#32FFFFFF')};
        }}
        QSlider::sub-page:horizontal {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {colors.get('grad_slider_start', '#FF4A90E2')},
                stop:1 {colors.get('grad_slider_end', '#FF00FFCC')});
            border-radius: 3px;
        }}
        QSlider::add-page:horizontal {{
            background: {colors.get('bg_input', '#961E1E1E')};
            border-radius: 3px;
        }}

        /* === ComboBox === */
        QComboBox {{
            background: {colors.get('bg_input', '#961E1E1E')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 6px; padding: 5px 10px; min-height: 24px;
            font-size: 13px;
        }}
        QComboBox:hover {{ border: 1px solid {colors.get('border_accent', '#FF00FFCC')}; }}
        QComboBox:focus {{ border: 1px solid {colors.get('border_accent', '#FF00FFCC')}; }}
        QComboBox::drop-down {{ border: none; background: transparent; width: 24px; }}
        QComboBox::down-arrow {{ image: none; }}
        QComboBox QAbstractItemView {{
            background: {colors.get('bg_menu', '#C8141414')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            selection-background-color: {colors.get('bg_menu_item_sel', '#FF4A90E2')};
            selection-color: {colors.get('text_button', '#FFFFFFFF')};
            border: 1px solid {colors.get('border_medium', '#32FFFFFF')};
            border-radius: 6px; padding: 4px; outline: 0px;
        }}

        /* === Progress Bar === */
        QProgressBar {{
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 6px;
            background: {colors.get('bg_input', '#961E1E1E')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            text-align: center;
            font-size: 11px; font-weight: 600;
            height: 18px;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {colors.get('progress_chunk_start', '#FF4A90E2')},
                stop:1 {colors.get('progress_chunk_end', '#FF00FFCC')});
            border-radius: 5px; margin: 1px;
        }}

        /* === Menu Bar === */
        QMenuBar {{
            background: {colors.get('bg_main', '#C8141414')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            font-size: 13px;
            font-family: 'Segoe UI', 'Roboto', Arial, sans-serif;
            border-bottom: 1px solid {colors.get('border_light', '#14FFFFFF')};
        }}
        QMenuBar::item {{
            padding: 6px 14px; background: transparent; border-radius: 4px;
        }}
        QMenuBar::item:selected {{
            background: {colors.get('bg_menu_item_sel', '#FF4A90E2')};
            color: {colors.get('text_button', '#FFFFFFFF')};
        }}

        /* === Menus === */
        QMenu {{
            background: {colors.get('bg_menu', '#C8141414')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            border: 1px solid {colors.get('border_menu', '#14FFFFFF')};
            border-radius: 8px; padding: 6px;
        }}
        QMenu::item {{ padding: 7px 28px 7px 16px; border-radius: 4px; }}
        QMenu::item:checked {{
            font-weight: bold;
            background-color: {colors.get('bg_menu_item_sel', '#FF4A90E2')};
            color: {colors.get('text_button', '#FFFFFFFF')};
        }}
        QMenu::item:selected {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {colors.get('grad_button_start', '#FF4A90E2')},
                stop:1 {colors.get('grad_button_end', '#FF00FFCC')});
            color: {colors.get('text_button', '#FFFFFFFF')};
        }}
        QMenu::separator {{
            height: 1px; background: {colors.get('border_light', '#14FFFFFF')};
            margin: 4px 8px;
        }}

        /* === Tooltips === */
        QToolTip {{
            background-color: {colors.get('bg_tooltip', '#F032323C')};
            color: {colors.get('text_tooltip', '#FFF0F0F0')};
            border: 1px solid {colors.get('border_medium', '#32FFFFFF')};
            padding: 6px 10px;
            border-radius: 6px;
            font-size: 12px;
        }}

        /* === Scroll Areas === */
        QScrollArea {{
            border: none;
            background: transparent;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {colors.get('border_medium', '#32FFFFFF')};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {colors.get('border_accent', '#FF00FFCC')};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0; background: transparent;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 8px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {colors.get('border_medium', '#32FFFFFF')};
            border-radius: 4px;
            min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {colors.get('border_accent', '#FF00FFCC')};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0; background: transparent;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}

        /* === Tab Widget === */
        QTabWidget::pane {{
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 8px;
            background: {colors.get('bg_groupbox', '#961E1E1E')};
        }}
        QTabBar::tab {{
            background: {colors.get('bg_input', '#961E1E1E')};
            color: {colors.get('text_secondary', '#FF4A90E2')};
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-bottom: none;
            padding: 8px 16px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
            font-size: 12px;
        }}
        QTabBar::tab:selected {{
            background: {colors.get('bg_groupbox', '#961E1E1E')};
            color: {colors.get('text_accent', '#FF00FFCC')};
            font-weight: 600;
        }}
        QTabBar::tab:hover:!selected {{
            background: {hover_rgba};
            color: {colors.get('text_light', '#FFE0E0E0')};
        }}

        /* === Collapsible Box Headers === */
        QToolButton#CollapsibleHeader {{
            border: none;
            background-color: transparent;
            font-weight: bold;
            font-size: 11pt;
            text-align: left;
            padding: 10px 12px;
            color: {colors.get('text_accent', '#FF00FFCC')};
            border-radius: 8px;
        }}
        QToolButton#CollapsibleHeader:hover {{
            background-color: {hover_rgba};
        }}
        QToolButton#CollapsibleHeader:checked {{
            color: {colors.get('text_accent', '#FF00FFCC')};
        }}

        /* === Generic Tool Buttons === */
        QToolButton {{
            background-color: transparent;
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            border-radius: 4px;
            padding: 2px 4px;
            color: {colors.get('text_secondary', '#FF4A90E2')};
        }}
        QToolButton:hover {{
            background-color: {hover_rgba};
            border-color: {colors.get('border_accent', '#FF00FFCC')};
            color: {colors.get('text_accent', '#FF00FFCC')};
        }}
        QToolButton:pressed {{
            background-color: {hover_strong};
        }}
        QToolButton:disabled {{
            color: {colors.get('text_disabled', '#64FFFFFF')};
            border-color: transparent;
        }}

        /* === Enhanced Status Bar === */
        QWidget#EnhancedStatusBar QToolButton {{
            background-color: transparent;
            border: 1px solid {colors.get('border_medium', '#32FFFFFF')};
            border-radius: 3px;
            padding: 1px 3px;
            font-size: 13px;
            color: {colors.get('text_secondary', '#FF4A90E2')};
            min-width: 18px;
            max-width: 22px;
        }}
        QWidget#EnhancedStatusBar QToolButton:hover {{
            background-color: {hover_rgba};
            border-color: {colors.get('border_accent', '#FF00FFCC')};
            color: {colors.get('text_accent', '#FF00FFCC')};
        }}
        QWidget#EnhancedStatusBar QToolButton:pressed {{
            background-color: {hover_strong};
        }}
        QWidget#EnhancedStatusBar QToolButton:disabled {{
            color: {colors.get('text_disabled', '#64FFFFFF')};
            border-color: transparent;
        }}
        QLabel#StatusSeparator {{
            color: {colors.get('border_medium', '#32FFFFFF')};
            font-size: 10px;
            background: transparent;
        }}
        QLabel#StatusOperationLabel {{
            color: {colors.get('text_secondary', '#FF4A90E2')};
            font-size: 10px;
            background: transparent;
        }}
        QLabel#StatusProgressLabel {{
            color: {colors.get('border_accent', '#FF00FFCC')};
            font-size: 10px;
            font-weight: bold;
            background: transparent;
        }}

        /* === Info / Hint Labels === */
        QLabel#InfoHintLabel, QLabel#AiInfoLabel {{
            color: {colors.get('text_secondary', '#FF4A90E2')};
            font-size: 9pt;
            padding: 5px;
            background: transparent;
        }}

        /* === Toast Notifications === */
        QFrame#ToastNotification {{
            background-color: {colors.get('bg_groupbox', '#961E1E1E')};
            border-radius: 8px;
        }}
        QFrame#ToastNotification QLabel {{
            color: {colors.get('text_light', '#FFE0E0E0')};
            background: transparent;
        }}
        QFrame#ToastNotification QToolButton {{
            background-color: transparent;
            color: {colors.get('text_secondary', '#FF4A90E2')};
            border: none;
            font-size: 14px;
        }}
        QFrame#ToastNotification QToolButton:hover {{
            color: {colors.get('text_accent', '#FF00FFCC')};
        }}

        /* === Operation History Dialog === */
        QDialog#OperationHistoryDialog QTextEdit {{
            background-color: {colors.get('bg_input', '#961E1E1E')};
            color: {colors.get('text_light', '#FFE0E0E0')};
            border: 1px solid {colors.get('border_light', '#14FFFFFF')};
            font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
            font-size: 11px;
            border-radius: 6px;
            padding: 8px;
        }}

        /* === Live Translation Window === */
        QDialog#LiveTranslationWindow {{
            background-color: {QColor(colors.get('bg_groupbox', '#961E1E1E')).lighter(110).name(QColor.NameFormat.HexArgb)};
            border: 1px solid {colors.get('border_accent', '#FF00FFCC')};
            border-radius: 8px;
        }}
        QDialog#LiveTranslationWindow QLabel#LiveLabel {{
            color: {colors.get('text_accent', '#FF00FFCC')};
            background-color: transparent;
            padding: 8px;
            font-weight: normal;
            border: none;
            border-radius: 0px;
        }}

        /* === Status Bar === */
        QStatusBar {{
            background: {colors.get('bg_titlebar', '#C8282828')};
            color: {colors.get('text_secondary', '#FF4A90E2')};
            font-size: 11px;
            padding: 2px 5px;
            border-top: 1px solid {colors.get('border_light', '#14FFFFFF')};
        }}
        QStatusBar::item {{
            border: none;
            margin: 0 2px;
        }}
        QStatusBar QProgressBar {{
            border: 1px solid {colors.get('border_medium', '#32FFFFFF')};
            border-radius: 3px;
            background-color: {colors.get('bg_input', '#961E1E1E')};
            text-align: center;
            color: {colors.get('text_light', '#FFE0E0E0')};
            font-size: 9px;
            max-height: 14px;
            min-width: 60px;
        }}
        QStatusBar QProgressBar::chunk {{
            border-radius: 2px; margin: 1px;
        }}
        QStatusBar QLabel {{
            color: {colors.get('text_secondary', '#FF4A90E2')};
            background-color: transparent;
            font-size: 11px;
            padding: 0 2px;
        }}

        /* === Dialog Button Box === */
        QDialogButtonBox QPushButton {{
            min-width: 80px;
            padding: 6px 18px;
        }}

        /* === Color Dialog (Theme Editor) === */
        QColorDialog {{
            background-color: {colors.get('bg_main', '#C8141414')};
        }}

        /* ================================================================
           Settings Dialog — Fancy Navigation & Layout
           ================================================================ */

        /* --- Header bar --- */
        QWidget#settingsHeader {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {colors.get('bg_titlebar', '#C8282828')},
                stop:1 {colors.get('bg_main', '#C8141414')});
            border-bottom: 2px solid qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {colors.get('grad_button_start', '#FF4A90E2')},
                stop:1 {colors.get('grad_button_end', '#FF00FFCC')});
        }}
        QLabel#settingsTitle {{
            color: {colors.get('text_accent', '#FF00FFCC')};
            font-size: 18pt;
            font-weight: bold;
            background: transparent;
        }}
        QLabel#settingsSubtitle {{
            color: {colors.get('text_secondary', '#FF4A90E2')};
            font-size: 9pt;
            background: transparent;
            padding: 0;
        }}
        QLineEdit#settingsSearch {{
            background: {colors.get('bg_input', '#961E1E1E')};
            border: 1px solid {colors.get('border_medium', '#32FFFFFF')};
            border-radius: 16px;
            padding: 7px 14px;
            font-size: 12px;
        }}
        QLineEdit#settingsSearch:focus {{
            border: 1px solid {colors.get('border_accent', '#FF00FFCC')};
        }}

        /* --- Category sidebar --- */
        QListWidget#settingsCategoryList {{
            background: {colors.get('bg_titlebar', '#C8282828')};
            border: none;
            border-right: 1px solid {colors.get('border_light', '#14FFFFFF')};
            padding: 8px 4px;
            outline: none;
        }}
        QListWidget#settingsCategoryList::item {{
            color: {colors.get('text_light', '#FFE0E0E0')};
            border-radius: 8px;
            padding: 10px 14px;
            margin: 2px 6px;
            border-left: 3px solid transparent;
        }}
        QListWidget#settingsCategoryList::item:hover {{
            background-color: {hover_rgba};
            border-left: 3px solid {colors.get('border_medium', '#32FFFFFF')};
        }}
        QListWidget#settingsCategoryList::item:selected {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {hover_strong}, stop:1 transparent);
            color: {colors.get('text_accent', '#FF00FFCC')};
            border-left: 3px solid {colors.get('border_accent', '#FF00FFCC')};
            font-weight: bold;
        }}

        /* --- Page content area --- */
        QWidget#settingsContent {{
            background: {colors.get('bg_main', '#C8141414')};
        }}
        QStackedWidget#settingsStack {{
            background: transparent;
        }}
        QScrollArea#settingsPageScroll {{
            background: transparent;
            border: none;
        }}
        QWidget#settingsPageContainer {{
            background: transparent;
        }}

        /* --- Section headers inside pages --- */
        QLabel#settingsSectionHeader {{
            color: {colors.get('text_accent', '#FF00FFCC')};
            font-size: 13pt;
            font-weight: bold;
            padding: 0 0 2px 0;
            background: transparent;
        }}
        QLabel#settingsSectionDesc {{
            color: {colors.get('text_secondary', '#FF4A90E2')};
            font-size: 10pt;
            padding: 0 0 6px 0;
            background: transparent;
        }}

        /* --- Button bar --- */
        QWidget#settingsButtonBar {{
            background: {colors.get('bg_titlebar', '#C8282828')};
        }}
        QFrame#settingsButtonSeparator {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 transparent,
                stop:0.2 {colors.get('border_medium', '#32FFFFFF')},
                stop:0.8 {colors.get('border_medium', '#32FFFFFF')},
                stop:1 transparent);
            max-height: 1px;
        }}
        /* Secondary (outline) buttons */
        QPushButton#settingsSecondaryBtn {{
            background: transparent;
            color: {colors.get('text_light', '#FFE0E0E0')};
            border: 1px solid {colors.get('border_medium', '#32FFFFFF')};
            border-radius: 8px;
            padding: 7px 14px;
            font-weight: 500;
        }}
        QPushButton#settingsSecondaryBtn:hover {{
            border-color: {colors.get('border_accent', '#FF00FFCC')};
            color: {colors.get('text_accent', '#FF00FFCC')};
            background: {hover_rgba};
        }}
        QPushButton#settingsSecondaryBtn:pressed {{
            background: {hover_strong};
        }}
        /* Danger button (Reset) */
        QPushButton#settingsDangerBtn {{
            background: transparent;
            color: #FFE06666;
            border: 1px solid rgba(224, 102, 102, 80);
            border-radius: 8px;
            padding: 7px 14px;
            font-weight: 500;
        }}
        QPushButton#settingsDangerBtn:hover {{
            border-color: #FFE06666;
            background: rgba(224, 102, 102, 25);
        }}
        QPushButton#settingsDangerBtn:pressed {{
            background: rgba(224, 102, 102, 50);
        }}
    """

def apply_theme() -> None:
    """
    Apply the current active theme to the entire Qt application.
    
    Generates stylesheet from current theme colors and applies it to the
    QApplication instance. Falls back to default theme on errors.
    
    Workflow:
    1. Get current theme data from global config
    2. Validate theme structure
    3. Generate stylesheet from theme colors
    4. Apply to QApplication instance
    5. On error, fallback to default theme
    
    Raises:
        None - All exceptions are caught and logged
        
    Note:
        Requires QApplication instance to exist before calling.
        Safe to call multiple times to refresh theme.
    """
    try:
        theme_data = get_current_theme()
        if not isinstance(theme_data, dict) or "colors" not in theme_data:
            logger.error("Invalid theme structure found. Reverting to default.")
            theme_data = DEFAULT_THEME; update_current_theme(theme_data)

        stylesheet = generate_stylesheet(theme_data["colors"])
        app_instance = QApplication.instance()
        if app_instance: app_instance.setStyleSheet(stylesheet); logger.info(f"Applied theme: {theme_data.get('name', 'Unnamed')}")
        else: logger.warning("Cannot apply theme: No QApplication instance exists.")
    except Exception as e:
        logger.error(f"Failed to apply theme: {e}", exc_info=True)
        try:
             logger.warning("Attempting to apply default theme as fallback.")
             stylesheet = generate_stylesheet(DEFAULT_THEME["colors"])
             app_instance = QApplication.instance()
             if app_instance: app_instance.setStyleSheet(stylesheet); logger.warning("Fell back to default theme due to error."); update_current_theme(DEFAULT_THEME)
        except Exception as fallback_e: logger.error(f"Failed to apply even default theme: {fallback_e}")

def resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for development and PyInstaller bundles.
    
    When running as PyInstaller bundle, uses sys._MEIPASS temporary folder.
    When running in development, uses PROJECT_ROOT directory.
    
    Args:
        relative_path (str): Relative path to resource file
            Examples: 'assets/icon.png', 'config.ini'
            
    Returns:
        str: Absolute path to the resource file
        
    Examples:
        >>> resource_path('assets/icon.png')
        'C:/app/_MEIPASS/assets/icon.png'  # In PyInstaller bundle
        'C:/project/assets/icon.png'        # In development
    """
    try:
        # PyInstaller crea una carpeta temporal y almacena la ruta en _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # _MEIPASS attribute doesn't exist - not running in PyInstaller bundle
        # PROJECT_ROOT ya está definido en config.py, lo importamos
        from .config import PROJECT_ROOT
        base_path = PROJECT_ROOT

    return os.path.join(base_path, relative_path)