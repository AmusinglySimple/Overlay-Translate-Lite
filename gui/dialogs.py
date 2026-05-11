# gui/dialogs.py — Lite version (no ChatWindow, no ThemeAutoSwitch, no ThemePreview)
import os
import logging
import textwrap
import json
import re
import datetime

from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QInputDialog, QMessageBox, QSystemTrayIcon,
    QWidget, QHBoxLayout, QTextEdit, QLineEdit, QFileDialog, QGroupBox, QCheckBox,
    QColorDialog, QComboBox, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QDialogButtonBox, QGridLayout, QSlider, QScrollArea, QSpinBox, QToolBar, QToolButton,
    QMenu, QApplication, QFrame, QFormLayout, QSizePolicy
)
from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QTimer, Signal, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QIcon, QFont, QFontDatabase, QFontInfo, QFontMetricsF, QImage

from .custom_widgets import ColorBarPicker
from .enhanced_image_viewer import ZoomableImageLabel, AnnotationTool, TranslationOverlayBlock

from utils.config import (
    PROJECT_ROOT, DEFAULT_THEME, get_current_theme, PREDEFINED_THEMES,
    logger, SUPPORT_FOLDER, ensure_support_folder,
    update_current_theme,
    DIALOG_MARGIN, DIALOG_SPACING, DIALOG_MIN_WIDTH, DIALOG_MIN_HEIGHT, DIALOG_ICON_SIZE
)
from utils.helpers import apply_theme, choose_font_for_text, generate_stylesheet, load_settings, get_system_font_path, save_settings

from PIL import Image, ImageDraw, ImageFont, ImageOps
import math


# --- IntroDialog ---
class IntroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("🌌 Overlay Translate Lite"))
        self.setMinimumSize(DIALOG_MIN_WIDTH, DIALOG_MIN_HEIGHT)
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint | Qt.WindowStaysOnTopHint)
        self.initUI()
        if parent:
            try:
                parent_geo = parent.geometry()
                if parent_geo.isValid():
                    self.move(parent_geo.center() - self.rect().center())
                else:
                    self.move(QtWidgets.QApplication.primaryScreen().availableGeometry().center() - self.rect().center())
            except (AttributeError, RuntimeError) as e:
                logger.debug(f"Could not center dialog on parent: {e}")
                self.move(QtWidgets.QApplication.primaryScreen().availableGeometry().center() - self.rect().center())
        else:
            self.move(QtWidgets.QApplication.primaryScreen().availableGeometry().center() - self.rect().center())
        self.raise_()
        self.activateWindow()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_MARGIN)
        layout.setSpacing(DIALOG_SPACING)
        intro_text = self.tr("""
        <h2 style='text-align: center; margin-bottom: 15px; font-weight: 600;'>🌌 Welcome to Overlay Translate Lite</h2>
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
            <li>💾 Save captures effortlessly</li>
            <li>⚙️ Customizable themes</li>
        </ul>
        <br/>
        <p style='text-align: center; font-size: 16px; font-weight: bold;'>
            Dive into the future of translation! 🚀
        </p>
        """)
        intro_label = QLabel(intro_text)
        intro_label.setWordWrap(True)
        intro_label.setTextFormat(Qt.RichText)
        intro_label.setAlignment(Qt.AlignLeft)
        close_button = QPushButton(self.tr("Launch"))
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "launch.svg")
        if os.path.exists(icon_path):
            close_button.setIcon(QIcon(icon_path))
            close_button.setIconSize(QtCore.QSize(DIALOG_ICON_SIZE, DIALOG_ICON_SIZE))
        close_button.clicked.connect(self.accept)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        try:
            accent_color = QColor(get_current_theme()["colors"].get("text_accent", "#00ffcc"))
            if accent_color.isValid():
                shadow_color = accent_color.lighter(110)
                shadow_color.setAlpha(100)
                shadow.setColor(shadow_color)
            else:
                shadow.setColor(QColor(0, 255, 204, 100))
        except (KeyError, TypeError, ValueError) as e:
            logger.debug(f"Could not apply theme color to shadow: {e}")
            shadow.setColor(QColor(0, 255, 204, 100))
        shadow.setOffset(0, 2)
        close_button.setGraphicsEffect(shadow)
        layout.addWidget(intro_label)
        layout.addStretch(1)
        layout.addWidget(close_button)
        self.setLayout(layout)
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.animation.setDuration(800)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.animation.start()


# --- ThemeDialog ---
class ThemeDialog(QDialog):
    COLOR_CATEGORIES = [
        ("🎨 Backgrounds", [
            ("bg_main", "Main Background"), ("bg_groupbox", "Panel / Group Box"),
            ("bg_input", "Input Fields"), ("bg_titlebar", "Title Bar / Headers"),
            ("bg_tooltip", "Tooltips"), ("bg_menu", "Menus"),
        ]),
        ("✏️ Text Colors", [
            ("text_light", "Primary Text"), ("text_accent", "Accent / Headings"),
            ("text_secondary", "Secondary / Subtle"), ("text_button", "Button Labels"),
            ("text_disabled", "Disabled Text"), ("text_tooltip", "Tooltip Text"),
        ]),
        ("📐 Borders", [
            ("border_accent", "Accent Border"), ("border_light", "Light Border"),
            ("border_medium", "Medium Border"), ("border_menu", "Menu Border"),
        ]),
        ("🔘 Button Gradients", [
            ("grad_button_start", "Gradient Start"), ("grad_button_end", "Gradient End"),
            ("grad_button_hover_start", "Hover Start"), ("grad_button_hover_end", "Hover End"),
            ("grad_button_pressed", "Pressed"),
        ]),
        ("📊 Indicators & Accents", [
            ("grad_slider_start", "Slider Start"), ("grad_slider_end", "Slider End"),
            ("progress_chunk_start", "Progress Start"), ("progress_chunk_end", "Progress End"),
            ("checkbox_checked", "Checkbox Active"), ("bg_menu_item_sel", "Menu Selection"),
        ]),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Theme Settings")
        self.setMinimumWidth(620)
        self.resize(680, 700)
        source_theme = get_current_theme()
        self.current_local_theme = json.loads(json.dumps(source_theme))
        colors_to_check = self.current_local_theme.get("colors", {})
        default_colors = DEFAULT_THEME["colors"]
        for key, color_str in colors_to_check.items():
            if key not in default_colors:
                continue
            if not (isinstance(color_str, str) and color_str.startswith('#') and len(color_str) == 9 and QColor(color_str).isValid()):
                self.current_local_theme["colors"][key] = default_colors.get(key, "#FFFF0000")
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(10)
        self.color_buttons = {}

        name_layout = QHBoxLayout()
        name_label = QLabel("Theme Name:")
        name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        name_layout.addWidget(name_label)
        self.theme_name_input = QLineEdit(self.current_local_theme.get("name", "Custom Theme"))
        self.theme_name_input.setPlaceholderText("Enter theme name (optional)")
        self.theme_name_input.textChanged.connect(self.update_local_theme_name)
        name_layout.addWidget(self.theme_name_input)
        self.main_layout.addLayout(name_layout)

        self._build_preview_panel()

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_content_widget = QWidget()
        content_layout = QVBoxLayout(scroll_content_widget)
        content_layout.setSpacing(6)
        content_layout.setContentsMargins(6, 6, 6, 6)

        for section_title, keys in self.COLOR_CATEGORIES:
            header = QLabel(section_title)
            header.setStyleSheet("font-weight: bold; font-size: 13px; padding: 6px 0 2px 0; background: transparent;")
            content_layout.addWidget(header)
            grid = QGridLayout()
            grid.setSpacing(6)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(3, 1)
            row = 0
            col = 0
            max_cols = 2
            for key, label_text in keys:
                if key not in self.current_local_theme.get("colors", {}):
                    continue
                label = QLabel(f"{label_text}:")
                label.setStyleSheet("font-size: 12px; background: transparent;")
                color_button = QPushButton()
                color_button.setFixedSize(80, 28)
                color_button.setCursor(Qt.PointingHandCursor)
                color_button.setToolTip(f"{key}: click to change")
                initial_color = self.current_local_theme["colors"].get(key, "#FFFF0000")
                self.update_button_color(color_button, initial_color)
                color_button.setProperty("currentColorHex", initial_color)
                def create_picker_lambda(k, b):
                    return lambda checked=False: self.pick_and_update_local(k, b)
                color_button.clicked.connect(create_picker_lambda(key, color_button))
                grid.addWidget(label, row, col * 2, Qt.AlignRight)
                grid.addWidget(color_button, row, col * 2 + 1)
                self.color_buttons[key] = color_button
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
            content_layout.addLayout(grid)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFrameShadow(QFrame.Shadow.Sunken)
            sep.setMaximumHeight(1)
            content_layout.addWidget(sep)

        content_layout.addStretch()
        scroll_content_widget.setLayout(content_layout)
        scroll_area.setWidget(scroll_content_widget)
        self.main_layout.addWidget(scroll_area, 1)

        button_box = QDialogButtonBox()
        reset_btn = button_box.addButton("Reset to Default", QDialogButtonBox.ResetRole)
        ok_button = button_box.addButton(QDialogButtonBox.StandardButton.Ok)
        cancel_button = button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        reset_btn.clicked.connect(self.reset_theme)
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        self.accepted.connect(self.save_and_apply)
        self.main_layout.addWidget(button_box)

    def _build_preview_panel(self):
        preview_frame = QFrame()
        preview_frame.setFixedHeight(60)
        preview_layout = QHBoxLayout(preview_frame)
        preview_layout.setContentsMargins(8, 4, 8, 4)
        preview_layout.setSpacing(6)
        self._preview_labels = {}
        preview_items = [
            ("bg_main", "BG"), ("text_accent", "Accent"), ("grad_button_start", "Btn"),
            ("grad_button_end", "Btn2"), ("border_accent", "Border"), ("text_light", "Text"),
            ("checkbox_checked", "Check"), ("progress_chunk_start", "Prog"),
        ]
        for key, label_text in preview_items:
            swatch = QFrame()
            swatch.setFixedSize(40, 40)
            swatch.setToolTip(key)
            color = self.current_local_theme.get("colors", {}).get(key, "#FFFF0000")
            swatch.setStyleSheet(f"background-color: {color}; border-radius: 6px; border: 1px solid rgba(128,128,128,80);")
            self._preview_labels[key] = swatch
            col_layout = QVBoxLayout()
            col_layout.setSpacing(1)
            col_layout.setContentsMargins(0, 0, 0, 0)
            col_layout.addWidget(swatch, 0, Qt.AlignCenter)
            tiny_label = QLabel(label_text)
            tiny_label.setStyleSheet("font-size: 8px; background: transparent;")
            tiny_label.setAlignment(Qt.AlignCenter)
            col_layout.addWidget(tiny_label)
            preview_layout.addLayout(col_layout)
        preview_layout.addStretch()
        self.main_layout.addWidget(preview_frame)

    def _refresh_preview(self):
        colors = self.current_local_theme.get("colors", {})
        for key, swatch in self._preview_labels.items():
            color = colors.get(key, "#FFFF0000")
            swatch.setStyleSheet(f"background-color: {color}; border-radius: 6px; border: 1px solid rgba(128,128,128,80);")

    def update_local_theme_name(self, new_name):
        self.current_local_theme["name"] = new_name.strip()

    def update_button_color(self, button, color_str):
        try:
            color = QColor(color_str)
            if color.isValid():
                display_color = QColor(color.red(), color.green(), color.blue(), max(color.alpha(), 150))
                button.setStyleSheet(f"background-color: {display_color.name(QColor.NameFormat.HexArgb)}; border: 1px solid #888;")
            else:
                button.setStyleSheet("background-color: grey; border: 1px solid #888;")
        except Exception:
            button.setStyleSheet("background-color: red; border: 1px solid #888;")

    def pick_and_update_local(self, key, button):
        initial_color_str = button.property("currentColorHex")
        try:
            initial_color = QColor(initial_color_str)
            if not initial_color.isValid():
                raise ValueError
        except (TypeError, ValueError):
            initial_color = QColor("#FFFFFFFF")
        color_dialog = QColorDialog(initial_color, self)
        color_dialog.setOptions(QColorDialog.ColorDialogOption.ShowAlphaChannel | QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if color_dialog.exec():
            color = color_dialog.selectedColor()
            if color.isValid():
                new_color_str = color.name(QColor.NameFormat.HexArgb).upper()
                button.setProperty("currentColorHex", new_color_str)
                self.update_button_color(button, new_color_str)
                if self.current_local_theme["colors"].get(key) != new_color_str:
                    self.current_local_theme["colors"][key] = new_color_str
                    self._refresh_preview()

    def reset_theme(self):
        self.current_local_theme = json.loads(json.dumps(DEFAULT_THEME))
        self.theme_name_input.setText(self.current_local_theme.get("name", "Default Neon"))
        default_colors = self.current_local_theme.get("colors", {})
        for key, button in self.color_buttons.items():
            if key in default_colors:
                default_color_str = default_colors[key]
                button.setProperty("currentColorHex", default_color_str)
                self.update_button_color(button, default_color_str)
        self._refresh_preview()
        QMessageBox.information(self, self.tr("Theme Reset"), self.tr("Dialog reset to default. Click 'OK' to apply this default theme."))

    def save_and_apply(self):
        theme_to_apply = self.current_local_theme
        theme_name = theme_to_apply.get('name', 'N/A')
        update_current_theme(theme_to_apply)
        apply_theme()
        logger.info(f"Theme '{theme_name}' settings applied.")


# --- LiveTranslationWindow ---
class LiveTranslationWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Live Translation"))
        self.setObjectName("LiveTranslationWindow")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(250, 60)
        self.offset = None
        self.font_size = 16
        self.is_pinned = True
        self.window_opacity = 1.0
        self.initUI()
        self.load_geometry()
        self.label_opacity_effect = QGraphicsOpacityEffect(self)
        self.translation_label.setGraphicsEffect(self.label_opacity_effect)
        self.label_fade_anim = QPropertyAnimation(self.label_opacity_effect, b"opacity", self)
        self.label_fade_anim.setDuration(300)
        self.label_fade_anim.setStartValue(0.0)
        self.label_fade_anim.setEndValue(1.0)
        self.label_fade_anim.setEasingCurve(QEasingCurve.InOutQuad)

    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.toolbar = QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.toolbar.setStyleSheet("QToolBar { border: none; background: transparent; spacing: 2px; }")

        self.pin_button = QToolButton(self)
        self.pin_button.setCheckable(True)
        self.pin_button.setChecked(self.is_pinned)
        self.pin_button.setText("📌")
        self.pin_button.setToolTip("Toggle Always On Top (F11)")
        self.pin_button.clicked.connect(self.toggle_pin)
        self.toolbar.addWidget(self.pin_button)
        self.toolbar.addSeparator()

        self.opacity_button = QToolButton(self)
        self.opacity_button.setText("👁️")
        self.opacity_button.setToolTip("Adjust Opacity")
        self.opacity_button.clicked.connect(self.show_opacity_slider)
        self.toolbar.addWidget(self.opacity_button)
        self.toolbar.addSeparator()

        self.font_minus_button = QToolButton(self)
        self.font_minus_button.setText("A-")
        self.font_minus_button.setToolTip("Decrease Font Size (Ctrl+-)")
        self.font_minus_button.clicked.connect(self.decrease_font_size)
        self.toolbar.addWidget(self.font_minus_button)

        self.font_plus_button = QToolButton(self)
        self.font_plus_button.setText("A+")
        self.font_plus_button.setToolTip("Increase Font Size (Ctrl++)")
        self.font_plus_button.clicked.connect(self.increase_font_size)
        self.toolbar.addWidget(self.font_plus_button)
        self.toolbar.addSeparator()

        self.copy_button = QToolButton(self)
        self.copy_button.setText("📋")
        self.copy_button.setToolTip("Copy Translation (Ctrl+C)")
        self.copy_button.clicked.connect(self.copy_translation)
        self.toolbar.addWidget(self.copy_button)

        layout.addWidget(self.toolbar)

        self.translation_label = QLabel("Waiting for live data...", self)
        self.translation_label.setObjectName("LiveLabel")
        self.translation_label.setWordWrap(True)
        self.translation_label.setAlignment(Qt.AlignCenter)
        self.translation_label.setMinimumHeight(30)
        layout.addWidget(self.translation_label)
        self.setLayout(layout)

    def updateTranslation(self, text):
        flat_text = text.replace('\n', ' ').strip()
        display_text = flat_text if flat_text else "..."
        if self.translation_label.text() != display_text:
            self.translation_label.setText(display_text)
            self.translation_label.setFont(choose_font_for_text(flat_text, default_font_family="Roboto", font_size=self.font_size))
            self.adjustSize()

    def set_font_size(self, size):
        self.font_size = size
        current_text = self.translation_label.text()
        if current_text and current_text != "...":
            flat_text = current_text.replace('\n', ' ').strip()
            self.translation_label.setFont(choose_font_for_text(flat_text, default_font_family="Roboto", font_size=self.font_size))
            self.adjustSize()

    def toggle_pin(self):
        self.is_pinned = not self.is_pinned
        flags = Qt.Window | Qt.Tool
        if self.is_pinned:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        self.pin_button.setChecked(self.is_pinned)

    def show_opacity_slider(self):
        current_opacity = int(self.window_opacity * 100)
        opacity, ok = QInputDialog.getInt(self, "Adjust Opacity", "Window Opacity (%):", current_opacity, 10, 100, 5)
        if ok:
            self.window_opacity = opacity / 100.0
            self.setWindowOpacity(self.window_opacity)

    def increase_font_size(self):
        if self.parent():
            self.parent().increaseFontSize()

    def decrease_font_size(self):
        if self.parent():
            self.parent().decreaseFontSize()

    def copy_translation(self):
        text = self.translation_label.text()
        if text and text != "..." and "Waiting" not in text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            original_text = text
            self.translation_label.setText("✓ Copied!")
            QTimer.singleShot(1000, lambda: self.translation_label.setText(original_text))

    def show_skip_indicator(self, show=True):
        if show:
            if self.label_opacity_effect:
                self.label_opacity_effect.setOpacity(0.6)
        else:
            if self.label_opacity_effect:
                self.label_opacity_effect.setOpacity(1.0)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
            self.copy_translation()
            event.accept()
        elif event.key() in (Qt.Key_Plus, Qt.Key_Equal) and event.modifiers() == Qt.ControlModifier:
            self.increase_font_size()
            event.accept()
        elif event.key() == Qt.Key_Minus and event.modifiers() == Qt.ControlModifier:
            self.decrease_font_size()
            event.accept()
        elif event.key() == Qt.Key_F11:
            self.toggle_pin()
            event.accept()
        else:
            super().keyPressEvent(event)

    def trigger_fade_in(self):
        if self.label_fade_anim and self.label_opacity_effect:
            self.label_fade_anim.stop()
            self.label_opacity_effect.setOpacity(0.0)
            self.label_fade_anim.start()
        else:
            self.translation_label.setVisible(True)

    def load_geometry(self):
        settings = load_settings()
        if 'LiveTranslationWindow' in settings:
            try:
                geo = settings['LiveTranslationWindow']
                if all(k in geo for k in ('x', 'y', 'width', 'height')):
                    self.setGeometry(int(geo['x']), int(geo['y']), int(geo['width']), int(geo['height']))
                else:
                    self.resize(300, 80)
                if 'font_size' in geo:
                    self.font_size = int(geo['font_size'])
                if 'opacity' in geo:
                    self.window_opacity = float(geo['opacity'])
                    self.setWindowOpacity(self.window_opacity)
                if 'pinned' in geo:
                    self.is_pinned = bool(geo['pinned'])
                    flags = Qt.Window | Qt.Tool
                    if self.is_pinned:
                        flags |= Qt.WindowStaysOnTopHint
                    self.setWindowFlags(flags)
                    if hasattr(self, 'pin_button'):
                        self.pin_button.setChecked(self.is_pinned)
            except (ValueError, TypeError, KeyError) as e:
                logger.error(f"Error loading LiveTranslationWindow settings: {e}. Using defaults.")
                self.resize(300, 80)
        else:
            self.resize(300, 80)

    def save_geometry(self):
        return {
            'x': self.x(), 'y': self.y(), 'width': self.width(), 'height': self.height(),
            'font_size': self.font_size, 'opacity': self.window_opacity, 'pinned': self.is_pinned
        }

    def closeEvent(self, event):
        logger.debug("LiveTranslationWindow closing.")
        event.accept()


# --- TranslatedImageViewer ---
class TranslatedImageViewer(QDialog):
    def __init__(self, image_path, boxes, translated_lines, initial_font_size, target_language_code, control_window_ref, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.boxes = boxes if boxes else []
        self.translated_lines = translated_lines if translated_lines else []
        self.target_language_code = target_language_code
        self.control_window_ref = control_window_ref
        self.original_image = None
        self.rendered_image = None
        self.image_label = None
        self.translation_overlay_items = []
        self.viewer_scene_margin = 180
        self.save_on_close = True

        vs = {}
        try:
            if self.control_window_ref and hasattr(self.control_window_ref, 'last_viewer_settings'):
                vs = self.control_window_ref.last_viewer_settings
                if not (vs and isinstance(vs, dict)):
                    vs = load_settings().get('viewer_settings', {})
            else:
                vs = load_settings().get('viewer_settings', {})
        except RuntimeError:
            vs = load_settings().get('viewer_settings', {})

        default_font_color_tuple = (255, 255, 255, 255)
        default_bg_outer_tuple = (0, 0, 0, 200)
        font_color_val = vs.get('font_color', default_font_color_tuple)
        font_color_tuple = tuple(font_color_val) if isinstance(font_color_val, (list, tuple)) and len(font_color_val) == 4 else default_font_color_tuple
        bg_outer_val = vs.get('bg_color_outer', default_bg_outer_tuple)
        bg_outer_tuple = tuple(bg_outer_val) if isinstance(bg_outer_val, (list, tuple)) and len(bg_outer_val) == 4 else default_bg_outer_tuple

        try:
            self.font_color = QColor(*font_color_tuple)
            assert self.font_color.isValid()
        except (TypeError, ValueError, AssertionError):
            self.font_color = QColor(*default_font_color_tuple)
        try:
            self.bg_color_outer = QColor(*bg_outer_tuple)
            assert self.bg_color_outer.isValid()
        except (TypeError, ValueError, AssertionError):
            self.bg_color_outer = QColor(*default_bg_outer_tuple)

        h, s, v, a = self.bg_color_outer.getHsvF()
        new_v_inner = max(0, v * 0.9)
        new_a_inner = min(255, int(self.bg_color_outer.alpha() * 0.9))
        self.bg_color_inner = QColor.fromHsvF(h, s, new_v_inner, new_a_inner / 255.0)

        saved_font_path = vs.get('font_path')
        saved_font_size = vs.get('font_size')
        if saved_font_path and isinstance(saved_font_size, int) and os.path.exists(saved_font_path):
            self.font_path = saved_font_path
            self.font_size = saved_font_size
        else:
            self.font_path = get_system_font_path(self.target_language_code)
            self.font_size = initial_font_size
            if not self.font_path or not os.path.exists(self.font_path):
                self.font_path = get_system_font_path("default")

        try:
            self.original_image = Image.open(image_path).convert("RGBA")
        except Exception as e:
            logger.error(f"Failed to load image '{image_path}': {e}", exc_info=True)
            QMessageBox.critical(self, self.tr("Image Load Error"), self.tr("Failed to load image:\n{}").format(e))
            self.save_on_close = False
            QTimer.singleShot(0, self.reject)
            return

        if len(self.translated_lines) != len(self.boxes):
            diff = len(self.boxes) - len(self.translated_lines)
            if diff > 0:
                self.translated_lines.extend([""] * diff)
            else:
                self.translated_lines = self.translated_lines[:len(self.boxes)]

        self.setWindowTitle(self.tr("Translated Image Viewer"))
        self.setMinimumSize(400, 350)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)

        self.initUI()
        self.renderTranslatedImage()
        self.updateImageDisplay()

        settings_for_geom = load_settings()
        if 'TranslatedImageViewer' in settings_for_geom:
            try:
                geo = settings_for_geom['TranslatedImageViewer']
                if all(k in geo for k in ('x', 'y', 'width', 'height')):
                    self.setGeometry(int(geo['x']), int(geo['y']), int(geo['width']), int(geo['height']))
                else:
                    self.resize(600, 450)
            except (ValueError, TypeError, KeyError):
                self.resize(600, 450)
        else:
            self.resize(600, 450)

        # Clamp window to fit within the available screen
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            w = min(self.width(), avail.width())
            h = min(self.height(), avail.height())
            x = max(avail.x(), min(self.x(), avail.x() + avail.width() - w))
            y = max(avail.y(), min(self.y(), avail.y() + avail.height() - h))
            self.setGeometry(x, y, w, h)

    def initUI(self):
        self.setObjectName("translatedImageViewer")
        self.setStyleSheet(
            """
            QDialog#translatedImageViewer {
                background-color: #0f141b;
            }
            QGroupBox {
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                margin-top: 14px;
                padding-top: 12px;
                background-color: rgba(255, 255, 255, 0.03);
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
            QPushButton {
                background-color: #1a2330;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 9px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #223041;
            }
            QPushButton:checked {
                background-color: #2e5b84;
                border-color: rgba(180, 225, 255, 0.45);
            }
            QComboBox, QSpinBox {
                background-color: #161f2b;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                padding: 5px 8px;
            }
            QSlider::groove:horizontal {
                border-radius: 3px;
                height: 6px;
                background: rgba(255, 255, 255, 0.10);
            }
            QSlider::handle:horizontal {
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
                background: #88c8ff;
            }
            QLabel#viewerHintLabel {
                color: rgba(230, 238, 248, 0.78);
                background-color: rgba(136, 200, 255, 0.08);
                border: 1px solid rgba(136, 200, 255, 0.16);
                border-radius: 10px;
                padding: 8px 12px;
            }
            """
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.viewer_hint_label = QLabel(self.tr("Wheel zooms. Drag pans. Ctrl+drag pans from anywhere. Cards can overflow outside the capture."))
        self.viewer_hint_label.setObjectName("viewerHintLabel")
        self.viewer_hint_label.setWordWrap(True)
        main_layout.addWidget(self.viewer_hint_label)

        toolbar_layout = QHBoxLayout()

        zoom_group = QGroupBox("Zoom")
        zoom_layout = QHBoxLayout(zoom_group)
        zoom_layout.setSpacing(4)
        zoom_layout.setContentsMargins(4, 4, 4, 4)

        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setToolTip("Zoom In")
        self.zoom_in_btn.setFixedWidth(30)
        self.zoom_in_btn.clicked.connect(self.onZoomIn)
        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.setToolTip("Zoom Out")
        self.zoom_out_btn.setFixedWidth(30)
        self.zoom_out_btn.clicked.connect(self.onZoomOut)
        self.zoom_fit_btn = QPushButton("Fit")
        self.zoom_fit_btn.setFixedWidth(35)
        self.zoom_fit_btn.clicked.connect(self.onZoomFit)
        self.zoom_100_btn = QPushButton("100%")
        self.zoom_100_btn.setFixedWidth(45)
        self.zoom_100_btn.clicked.connect(self.onZoom100)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(50)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        zoom_layout.addWidget(self.zoom_out_btn)
        zoom_layout.addWidget(self.zoom_in_btn)
        zoom_layout.addWidget(self.zoom_fit_btn)
        zoom_layout.addWidget(self.zoom_100_btn)
        zoom_layout.addWidget(self.zoom_label)

        annot_group = QGroupBox("Annotations")
        annot_layout = QHBoxLayout(annot_group)
        annot_layout.setSpacing(4)
        annot_layout.setContentsMargins(4, 4, 4, 4)
        self.tool_none_btn = QPushButton("Select")
        self.tool_none_btn.setCheckable(True)
        self.tool_none_btn.setChecked(True)
        self.tool_none_btn.clicked.connect(lambda: self.setAnnotationTool(AnnotationTool.NONE))
        self.tool_pan_btn = QPushButton("Pan")
        self.tool_pan_btn.setCheckable(True)
        self.tool_pan_btn.clicked.connect(lambda: self.setAnnotationTool(AnnotationTool.PAN))
        self.tool_arrow_btn = QPushButton("Arrow")
        self.tool_arrow_btn.setCheckable(True)
        self.tool_arrow_btn.clicked.connect(lambda: self.setAnnotationTool(AnnotationTool.ARROW))
        self.tool_rect_btn = QPushButton("Rect")
        self.tool_rect_btn.setCheckable(True)
        self.tool_rect_btn.clicked.connect(lambda: self.setAnnotationTool(AnnotationTool.RECTANGLE))
        self.tool_text_btn = QPushButton("Text")
        self.tool_text_btn.setCheckable(True)
        self.tool_text_btn.clicked.connect(lambda: self.setAnnotationTool(AnnotationTool.TEXT))
        self.annot_color_btn = QPushButton()
        self.annot_color_btn.setFixedSize(30, 24)
        self.annot_color = QColor(255, 0, 0, 255)
        self.annot_color_btn.setStyleSheet(f"background-color: {self.annot_color.name()};")
        self.annot_color_btn.clicked.connect(self.chooseAnnotationColor)
        self.annot_width_spin = QSpinBox()
        self.annot_width_spin.setRange(1, 10)
        self.annot_width_spin.setValue(2)
        self.annot_width_spin.setFixedWidth(50)
        self.annot_width_spin.valueChanged.connect(self.onAnnotationWidthChanged)
        self.annot_undo_btn = QPushButton("Undo")
        self.annot_undo_btn.clicked.connect(self.onUndoAnnotation)
        self.annot_clear_btn = QPushButton("Clear")
        self.annot_clear_btn.clicked.connect(self.onClearAnnotations)
        annot_layout.addWidget(self.tool_none_btn)
        annot_layout.addWidget(self.tool_pan_btn)
        annot_layout.addWidget(self.tool_arrow_btn)
        annot_layout.addWidget(self.tool_rect_btn)
        annot_layout.addWidget(self.tool_text_btn)
        annot_layout.addWidget(QLabel("|"))
        annot_layout.addWidget(self.annot_color_btn)
        annot_layout.addWidget(self.annot_width_spin)
        annot_layout.addWidget(QLabel("|"))
        annot_layout.addWidget(self.annot_undo_btn)
        annot_layout.addWidget(self.annot_clear_btn)

        export_group = QGroupBox("Export")
        export_layout = QHBoxLayout(export_group)
        export_layout.setSpacing(4)
        export_layout.setContentsMargins(4, 4, 4, 4)
        self.export_png_btn = QPushButton("PNG")
        self.export_png_btn.clicked.connect(lambda: self.exportImage("PNG"))
        self.export_jpg_btn = QPushButton("JPEG")
        self.export_jpg_btn.clicked.connect(lambda: self.exportImage("JPEG"))
        self.export_pdf_btn = QPushButton("PDF")
        self.export_pdf_btn.clicked.connect(lambda: self.exportImage("PDF"))
        export_layout.addWidget(self.export_png_btn)
        export_layout.addWidget(self.export_jpg_btn)
        export_layout.addWidget(self.export_pdf_btn)
        export_layout.addStretch()

        toolbar_layout.addWidget(zoom_group)
        toolbar_layout.addWidget(annot_group)
        toolbar_layout.addWidget(export_group)
        toolbar_layout.addStretch()
        main_layout.addLayout(toolbar_layout)

        self.image_label = ZoomableImageLabel(self)
        self.image_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.image_label.zoomChanged.connect(self.onZoomChanged)
        main_layout.addWidget(self.image_label, 1)

        controls_group = QGroupBox("Display Settings")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setSpacing(8)

        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("Font:"))
        self.font_combo = QComboBox()
        font_db = QFontDatabase()
        available_families = sorted(font_db.families())
        self.font_family_to_path = {}
        current_font_found_in_db = False
        current_font_display_name = None
        if self.font_path and os.path.exists(self.font_path):
            try:
                loaded_id = QFontDatabase.addApplicationFont(self.font_path)
                if loaded_id != -1:
                    families = QFontDatabase.applicationFontFamilies(loaded_id)
                    if families:
                        font_family_name = families[0]
                        display_name = f"{font_family_name}"
                        is_standard = font_family_name in available_families
                        if not is_standard:
                            display_name += " (Loaded)"
                        if display_name not in self.font_family_to_path:
                            self.font_combo.addItem(display_name)
                            self.font_family_to_path[display_name] = self.font_path
                            current_font_found_in_db = True
                            current_font_display_name = display_name
                    else:
                        try:
                            font_pil = ImageFont.truetype(self.font_path, 10)
                            font_family_name_pil = font_pil.getname()[0]
                            display_name = f"{font_family_name_pil} (Loaded Path)"
                            if display_name not in self.font_family_to_path:
                                self.font_combo.addItem(display_name)
                                self.font_family_to_path[display_name] = self.font_path
                                current_font_found_in_db = True
                                current_font_display_name = display_name
                        except Exception:
                            pass
            except Exception:
                pass
        for family in available_families:
            styles = font_db.styles(family)
            if styles:
                try:
                    qfont = font_db.font(family, styles[0], 9)
                    font_info = QFontInfo(qfont)
                    resolved_family = font_info.family()
                    if resolved_family not in self.font_family_to_path:
                        self.font_family_to_path[resolved_family] = None
                        self.font_combo.addItem(resolved_family)
                        if not current_font_found_in_db and self.font_path:
                            guessed_path = get_system_font_path(resolved_family)
                            if guessed_path and guessed_path.lower() == self.font_path.lower():
                                self.font_family_to_path[resolved_family] = guessed_path
                                current_font_found_in_db = True
                                current_font_display_name = resolved_family
                except Exception:
                    continue
        if current_font_display_name and self.font_combo.findText(current_font_display_name) != -1:
            self.font_combo.setCurrentText(current_font_display_name)
        elif self.font_combo.count() > 0:
            self.font_combo.setCurrentIndex(0)
            self.updateFont(self.font_combo.currentText())
        self.font_combo.currentTextChanged.connect(self.updateFont)
        font_layout.addWidget(self.font_combo, 1)
        controls_layout.addLayout(font_layout)

        font_size_layout = QHBoxLayout()
        font_size_layout.addWidget(QLabel("Size:"))
        self.font_size_slider = QSlider(Qt.Horizontal)
        self.font_size_slider.setRange(8, 15)
        self.font_size_slider.setValue(min(self.font_size, 15))
        self.font_size_slider.valueChanged.connect(self.updateFontSize)
        self.font_size_value_label = QLabel(f"{self.font_size}pt")
        self.font_size_value_label.setMinimumWidth(40)
        font_size_layout.addWidget(self.font_size_slider, 1)
        font_size_layout.addWidget(self.font_size_value_label)
        controls_layout.addLayout(font_size_layout)

        color_layout = QGridLayout()
        color_layout.setSpacing(8)
        font_color_label = QLabel("Text:")
        self.font_color_picker = ColorBarPicker(self.font_color, self)
        self.font_color_picker.colorChanged.connect(self.updateFontColor)
        color_layout.addWidget(font_color_label, 0, 0)
        color_layout.addWidget(self.font_color_picker, 0, 1)
        bg_color_label = QLabel("BG:")
        self.bg_color_picker = ColorBarPicker(self.bg_color_outer, self)
        self.bg_color_picker.colorChanged.connect(self.updateBgColor)
        color_layout.addWidget(bg_color_label, 1, 0)
        color_layout.addWidget(self.bg_color_picker, 1, 1)
        color_layout.setColumnStretch(1, 1)
        controls_layout.addLayout(color_layout)

        main_layout.addWidget(controls_group)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateImageDisplay()

    def updateFont(self, font_display_name):
        new_path = self.font_family_to_path.get(font_display_name)
        if new_path is None and font_display_name in self.font_family_to_path:
            new_path = get_system_font_path(font_display_name)
            if new_path and os.path.exists(new_path):
                self.font_family_to_path[font_display_name] = new_path
            else:
                new_path = None
        if new_path and os.path.exists(new_path):
            if self.font_path != new_path:
                self.font_path = new_path
                self.renderTranslatedImage()
                self.updateImageDisplay()
        else:
            current_display_name = next((name for name, path in self.font_family_to_path.items() if path and self.font_path and path.lower() == self.font_path.lower()), None)
            if current_display_name:
                self.font_combo.blockSignals(True)
                self.font_combo.setCurrentText(current_display_name)
                self.font_combo.blockSignals(False)

    def updateFontSize(self, value):
        if self.font_size != value:
            self.font_size = value
            self.font_size_value_label.setText(f"{value}pt")
            if not hasattr(self, '_render_timer'):
                self._render_timer = QTimer(self)
                self._render_timer.setSingleShot(True)
                self._render_timer.timeout.connect(self._delayedRenderUpdate)
            self._render_timer.start(200)

    def _delayedRenderUpdate(self):
        self.renderTranslatedImage()
        self.updateImageDisplay()

    def updateFontColor(self, color):
        if self.font_color != color:
            self.font_color = color
            self.renderTranslatedImage()
            self.updateImageDisplay()

    def updateBgColor(self, color):
        if self.bg_color_outer != color:
            self.bg_color_outer = color
            h, s, v, a = color.getHsvF()
            new_v_inner = max(0, v * 0.9)
            new_a_inner = min(255, int(color.alpha() * 0.9))
            self.bg_color_inner = QColor.fromHsvF(h, s, new_v_inner, new_a_inner / 255.0)
            self.renderTranslatedImage()
            self.updateImageDisplay()

    def _get_active_font_family(self):
        current_text = self.font_combo.currentText().strip() if hasattr(self, 'font_combo') else ""
        if current_text:
            return re.sub(r"\s+\([^)]*\)$", "", current_text).strip()
        if self.font_path and os.path.exists(self.font_path):
            try:
                font_id = QFontDatabase.addApplicationFont(self.font_path)
                if font_id != -1:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        return families[0]
            except Exception as font_err:
                logger.debug(f"Unable to resolve active font family from path '{self.font_path}': {font_err}")
        return "Arial"

    def renderTranslatedImage(self):
        if not self.original_image:
            return
        self.rendered_image = self.original_image.copy()

        if self.rendered_image.mode != "RGBA":
            self.rendered_image = self.rendered_image.convert("RGBA")

        draw = ImageDraw.Draw(self.rendered_image)
        font_color_tuple = self.font_color.getRgb()
        bg_color_tuple = self.bg_color_outer.getRgb()

        if not self.boxes:
            msg = "No text detected in the captured image."
            try:
                font = ImageFont.truetype(self.font_path, max(12, min(18, self.font_size))) if self.font_path and os.path.exists(self.font_path) else ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), msg, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = (self.rendered_image.width - tw) // 2
            y = (self.rendered_image.height - th) // 2
            pad = 10
            draw.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], fill=bg_color_tuple)
            draw.text((x, y), msg, fill=font_color_tuple, font=font)
        else:
            for i, bbox in enumerate(self.boxes):
                if i >= len(self.translated_lines):
                    break
                line = self.translated_lines[i].strip()
                if not line:
                    continue

                left, top, right, bottom = bbox
                box_w = right - left
                box_h = bottom - top
                if box_w <= 0 or box_h <= 0:
                    continue

                fitted_font = None
                wrapped_text = None
                for fs in range(max(8, self.font_size), 7, -1):
                    try:
                        font = ImageFont.truetype(self.font_path, fs) if self.font_path and os.path.exists(self.font_path) else ImageFont.load_default()
                    except Exception:
                        font = ImageFont.load_default()

                    avg_char_w = max(1, fs * 0.6)
                    chars_per_line = max(1, int(box_w / avg_char_w))
                    lines = textwrap.wrap(line, width=chars_per_line)
                    if not lines:
                        lines = [line]

                    total_h = 0
                    for ln in lines:
                        tb = draw.textbbox((0, 0), ln, font=font)
                        total_h += tb[3] - tb[1] + 2

                    if total_h <= box_h or fs == 8:
                        fitted_font = font
                        wrapped_text = lines
                        break

                if not fitted_font or not wrapped_text:
                    continue

                draw.rectangle([left, top, right, bottom], fill=bg_color_tuple)

                y_cursor = top + 2
                for ln in wrapped_text:
                    tb = draw.textbbox((0, 0), ln, font=fitted_font)
                    line_h = tb[3] - tb[1]
                    draw.text((left + 2, y_cursor), ln, fill=font_color_tuple, font=fitted_font)
                    y_cursor += line_h + 2
                    if y_cursor >= bottom:
                        break

    def updateImageDisplay(self):
        if not self.rendered_image or not self.image_label:
            return
        try:
            im = self.rendered_image
            if im.mode != "RGBA":
                im = im.convert("RGBA")
            qimage = QImage(im.tobytes(), im.width, im.height, QImage.Format.Format_RGBA8888)
            if qimage.isNull():
                return
            pixmap = QPixmap.fromImage(qimage)
            preserve_view = hasattr(self, '_initial_fit_done')
            self.image_label.set_pixmap(pixmap, preserve_view=preserve_view)
            if not preserve_view:
                self._initial_fit_done = True
                QTimer.singleShot(100, self.image_label.zoom_fit)
        except Exception as e:
            logger.error(f"Error updating image display: {e}", exc_info=True)

    def auto_save_image(self):
        save_path = None
        if self.image_label and self.image_label.get_pixmap() and self.save_on_close:
            try:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                ensure_support_folder()
                base_name = os.path.splitext(os.path.basename(self.image_path))[0]
                suffix = "translated_snip" if "snip_" in base_name else "translated_capture"
                clean_base = base_name.replace("capture_", "").replace("snip_", "")
                save_filename = f"{clean_base}_{suffix}_{timestamp}.png"
                save_path = os.path.join(SUPPORT_FOLDER, save_filename)
                self.rendered_image.save(save_path, "PNG")
            except Exception as e:
                logger.error(f"Failed to auto-save image: {e}", exc_info=True)

    def get_viewer_settings(self):
        return {
            'font_color': list(self.font_color.getRgb()),
            'bg_color_outer': list(self.bg_color_outer.getRgb()),
            'font_path': self.font_path,
            'font_size': self.font_size
        }

    def get_geometry_settings(self):
        return {'x': self.x(), 'y': self.y(), 'width': self.width(), 'height': self.height()}

    def closeEvent(self, event):
        if self.control_window_ref and hasattr(self.control_window_ref, 'update_last_viewer_settings'):
            self.control_window_ref.update_last_viewer_settings(self.get_viewer_settings())
        self.auto_save_image()
        super().closeEvent(event)

    def accept(self):
        super().accept()

    def reject(self):
        super().reject()

    def onZoomIn(self):
        self.image_label.zoom_in()

    def onZoomOut(self):
        self.image_label.zoom_out()

    def onZoomFit(self):
        self.image_label.zoom_fit()

    def onZoom100(self):
        self.image_label.zoom_actual()

    def onZoomChanged(self, zoom_factor: float):
        self.zoom_label.setText(f"{int(zoom_factor * 100)}%")

    def setAnnotationTool(self, tool: AnnotationTool):
        self.image_label.set_annotation_tool(tool)
        self.tool_none_btn.setChecked(tool == AnnotationTool.NONE)
        self.tool_pan_btn.setChecked(tool == AnnotationTool.PAN)
        self.tool_arrow_btn.setChecked(tool == AnnotationTool.ARROW)
        self.tool_rect_btn.setChecked(tool == AnnotationTool.RECTANGLE)
        self.tool_text_btn.setChecked(tool == AnnotationTool.TEXT)

    def chooseAnnotationColor(self):
        color = QColorDialog.getColor(self.annot_color, self, "Choose Annotation Color")
        if color.isValid():
            self.annot_color = color
            self.annot_color_btn.setStyleSheet(f"background-color: {color.name()};")
            self.image_label.set_annotation_color(color)

    def onAnnotationWidthChanged(self, value: int):
        self.image_label.set_annotation_line_width(value)

    def onUndoAnnotation(self):
        self.image_label.undo_last_annotation()

    def onClearAnnotations(self):
        reply = QMessageBox.question(self, self.tr("Clear Annotations"), self.tr("Are you sure you want to clear all annotations?"), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.image_label.clear_annotations()

    def exportImage(self, format_type: str):
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(os.path.basename(self.image_path))[0]
            if format_type == "PNG":
                ext, filter_str = "png", "PNG Files (*.png)"
            elif format_type == "JPEG":
                ext, filter_str = "jpg", "JPEG Files (*.jpg *.jpeg)"
            elif format_type == "PDF":
                ext, filter_str = "pdf", "PDF Files (*.pdf)"
            else:
                return
            default_filename = f"{base_name}_export_{timestamp}.{ext}"
            default_path = os.path.join(SUPPORT_FOLDER, default_filename)
            file_path, _ = QFileDialog.getSaveFileName(self, f"Export as {format_type}", default_path, filter_str)
            if not file_path:
                return
            if self.rendered_image:
                im = self.rendered_image
                if im.mode != "RGBA":
                    im = im.convert("RGBA")
                qimage = QImage(im.tobytes(), im.width, im.height, QImage.Format.Format_RGBA8888)
                pixmap = QPixmap.fromImage(qimage)
            else:
                pixmap = self.image_label.get_rendered_pixmap(include_scene_margin=False)
            if format_type == "PNG":
                success = pixmap.save(file_path, "PNG")
            elif format_type == "JPEG":
                image = pixmap.toImage()
                if image.hasAlphaChannel():
                    rgb_image = QImage(image.size(), QImage.Format_RGB888)
                    rgb_image.fill(Qt.white)
                    painter = QPainter(rgb_image)
                    painter.drawImage(0, 0, image)
                    painter.end()
                    success = rgb_image.save(file_path, "JPEG", 95)
                else:
                    success = image.save(file_path, "JPEG", 95)
            elif format_type == "PDF":
                from PySide6.QtPrintSupport import QPrinter
                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(file_path)
                if pixmap.width() > pixmap.height():
                    printer.setPageOrientation(QPrinter.Landscape)
                painter = QPainter(printer)
                page_rect = printer.pageRect(QPrinter.DevicePixel)
                scaled_pixmap = pixmap.scaled(page_rect.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = (page_rect.width() - scaled_pixmap.width()) / 2
                y = (page_rect.height() - scaled_pixmap.height()) / 2
                painter.drawPixmap(int(x), int(y), scaled_pixmap)
                success = painter.end()
            if success:
                QMessageBox.information(self, self.tr("Export Successful"), self.tr("Image exported to:\n{}").format(file_path))
            else:
                QMessageBox.critical(self, self.tr("Export Failed"), self.tr("Failed to export image to:\n{}").format(file_path))
        except Exception as e:
            logger.error(f"Error exporting image: {e}", exc_info=True)
            QMessageBox.critical(self, self.tr("Export Error"), self.tr("An error occurred while exporting:\n{}").format(str(e)))
