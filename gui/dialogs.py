# gui/dialogs.py
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
    QDialogButtonBox, QGridLayout, QSlider, QScrollArea # Added QDialogButtonBox, QGridLayout
)
from PySide6.QtCore import Qt, QPoint, QRect, QTimer, Signal, QPropertyAnimation, QEasingCurve, QEventLoop, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QIcon, QFont, QFontDatabase, QFontInfo, QImage

# Internal imports (relative)
from .custom_widgets import ColorBarPicker
from workers import AIStreamingWorker # Import worker needed by ChatWindow

# Utility imports
from utils.config import (
    PROJECT_ROOT, DEFAULT_THEME, ai_api_config, get_current_theme,
    logger, SUPPORT_FOLDER, ensure_support_folder, # Added SUPPORT_FOLDER, ensure_support_folder
    update_current_theme # <--- IMPORT update_current_theme HERE
)
from utils.helpers import apply_theme, choose_font_for_text, load_settings, get_system_font_path, save_settings

# Import from PIL needed for TranslatedImageViewer
from PIL import Image, ImageDraw, ImageFont, ImageOps
import math # For TranslatedImageViewer calculations

# --- IntroDialog ---
# ... (IntroDialog class remains the same) ...
class IntroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌌 Overlay Translate")
        self.setMinimumSize(450, 500)
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
            except Exception:
                self.move(QtWidgets.QApplication.primaryScreen().availableGeometry().center() - self.rect().center())
        else:
            self.move(QtWidgets.QApplication.primaryScreen().availableGeometry().center() - self.rect().center())
        self.raise_()
        self.activateWindow()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)
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
        intro_label.setTextFormat(Qt.RichText)
        intro_label.setAlignment(Qt.AlignLeft)
        close_button = QPushButton("Launch")
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "launch.svg")
        if os.path.exists(icon_path):
            close_button.setIcon(QIcon(icon_path))
            close_button.setIconSize(QtCore.QSize(20, 20))
        else:
            logger.warning(f"Launch icon not found at: {icon_path}")
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
        except Exception:
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
# ... (ThemeDialog class remains the same) ...
class ThemeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Theme Settings")
        self.setMinimumWidth(550)
        self.resize(600, 500)
        source_theme = get_current_theme()
        logger.debug(f"ThemeDialog __init__: Source theme name = {source_theme.get('name', 'N/A')}")
        self.current_local_theme = json.loads(json.dumps(source_theme))
        logger.debug(f"ThemeDialog __init__: Copied theme name = {self.current_local_theme.get('name', 'N/A')}")
        colors_valid = True
        colors_to_check = self.current_local_theme.get("colors", {})
        default_colors = DEFAULT_THEME["colors"]
        for key, color_str in colors_to_check.items():
            if key not in default_colors:
                logger.warning(f"ThemeDialog found unexpected color key '{key}' during validation.")
                continue
            if not (isinstance(color_str, str) and color_str.startswith('#') and len(color_str) == 9 and QColor(color_str).isValid()):
                logger.error(f"ThemeDialog detected invalid color format for key '{key}': '{color_str}'. Reverting THIS key to default.")
                colors_valid = False
                self.current_local_theme["colors"][key] = default_colors.get(key, "#FFFF0000") # Fallback to red
        if not colors_valid:
            logger.warning("ThemeDialog reverted some invalid color values to default.")
        self.main_layout = QVBoxLayout(self)
        self.color_buttons = {}
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Theme Name:"))
        self.theme_name_input = QLineEdit(self.current_local_theme.get("name", "Custom Theme"))
        self.theme_name_input.setPlaceholderText("Enter theme name (optional)")
        self.theme_name_input.textChanged.connect(self.update_local_theme_name)
        name_layout.addWidget(self.theme_name_input)
        self.main_layout.addLayout(name_layout)
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_content_widget = QWidget()
        scroll_content_widget.setStyleSheet("background: transparent;")
        grid_layout = QGridLayout(scroll_content_widget)
        grid_layout.setSpacing(10)
        row, col = 0, 0
        max_cols = 2
        friendly_names = self.get_user_friendly_names()
        sorted_keys = sorted(self.current_local_theme.get("colors", {}).keys())
        for key in sorted_keys:
            if key not in DEFAULT_THEME["colors"]: continue
            name = friendly_names.get(key, key)
            label = QLabel(f"{name}:")
            color_button = QPushButton()
            color_button.setFixedSize(80, 25)
            initial_color = self.current_local_theme["colors"].get(key, "#FFFF0000")
            self.update_button_color(color_button, initial_color)
            color_button.setProperty("currentColorHex", initial_color)
            def create_picker_lambda(k, b):
                return lambda checked=False: self.pick_and_update_local(k, b)
            color_button.clicked.connect(create_picker_lambda(key, color_button))
            grid_layout.addWidget(label, row, col * 2, Qt.AlignRight)
            grid_layout.addWidget(color_button, row, col * 2 + 1)
            self.color_buttons[key] = color_button
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        grid_layout.setColumnStretch(1, 1)
        grid_layout.setColumnStretch(3, 1)
        grid_layout.addItem(QtWidgets.QSpacerItem(20, 10, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding), row + 1, 0)
        scroll_content_widget.setLayout(grid_layout)
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
    def get_user_friendly_names(self):
        return {
            "bg_main": "Main BG", "bg_groupbox": "Group Box BG", "bg_input": "Input BG",
            "text_light": "Primary Text", "text_accent": "Accent Text", "text_secondary": "Secondary Text",
            "text_button": "Button Text", "border_accent": "Accent Border", "border_light": "Light Border",
            "grad_button_start": "Btn Grad Start", "grad_button_end": "Btn Grad End",
            "grad_slider_start": "Slider Grad Start", "grad_slider_end": "Slider Grad End",
             "checkbox_checked": "Checkbox Checked", "bg_titlebar": "Group Title BG",
             "bg_tooltip": "Tooltip BG", "text_tooltip": "Tooltip Text", "border_medium": "Medium Border",
             "grad_button_hover_start": "Btn Hover Start", "grad_button_hover_end": "Btn Hover End",
             "grad_button_pressed": "Btn Pressed BG", "progress_chunk_start": "Progress Start",
             "progress_chunk_end": "Progress End", "bg_menu": "Menu BG", "bg_menu_item_sel": "Menu Sel BG",
             "border_menu": "Menu Border", "text_disabled": "Disabled Text"
        }
    def update_local_theme_name(self, new_name):
        self.current_local_theme["name"] = new_name.strip()
        logger.debug(f"Local theme name updated to: '{self.current_local_theme['name']}'")
    def update_button_color(self, button, color_str):
        try:
            color = QColor(color_str)
            if color.isValid():
                display_color = QColor(color.red(), color.green(), color.blue(), max(color.alpha(), 150))
                button.setStyleSheet(f"background-color: {display_color.name(QColor.NameFormat.HexArgb)}; border: 1px solid #888;")
            else:
                logger.warning(f"Invalid color string for button: {color_str}")
                button.setStyleSheet("background-color: grey; border: 1px solid #888;")
        except Exception as e:
             logger.error(f"Error setting button color for '{color_str}': {e}")
             button.setStyleSheet("background-color: red; border: 1px solid #888;")
    def pick_and_update_local(self, key, button):
        initial_color_str = button.property("currentColorHex")
        try:
            initial_color = QColor(initial_color_str)
            if not initial_color.isValid(): raise ValueError
        except (TypeError, ValueError):
            logger.warning(f"Invalid initial color '{initial_color_str}' for key '{key}', using white.")
            initial_color = QColor("#FFFFFFFF")
        color_dialog = QColorDialog(initial_color, self)
        color_dialog.setOptions(QColorDialog.ColorDialogOption.ShowAlphaChannel | QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if color_dialog.exec():
             color = color_dialog.selectedColor()
             if color.isValid():
                 new_color_str = color.name(QColor.NameFormat.HexArgb).upper()
                 button.setProperty("currentColorHex", new_color_str)
                 self.update_button_color(button, new_color_str)
                 old_value = self.current_local_theme["colors"].get(key)
                 if old_value != new_color_str:
                     logger.debug(f"[pick_and_update_local] Updating LOCAL theme key '{key}' from '{old_value}' to '{new_color_str}'")
                     self.current_local_theme["colors"][key] = new_color_str
                     logger.debug(f"[pick_and_update_local] LOCAL theme '{self.current_local_theme['name']}' key '{key}' is now: {self.current_local_theme['colors'].get(key)}")
    def reset_theme(self):
        logger.debug("[reset_theme] Resetting LOCAL theme state to default.")
        self.current_local_theme = json.loads(json.dumps(DEFAULT_THEME))
        self.theme_name_input.setText(self.current_local_theme.get("name", "Default Neon"))
        default_colors = self.current_local_theme.get("colors", {})
        for key, button in self.color_buttons.items():
            if key in default_colors:
                 default_color_str = default_colors[key]
                 button.setProperty("currentColorHex", default_color_str)
                 self.update_button_color(button, default_color_str)
        QMessageBox.information(self, "Theme Reset", "Dialog reset to default. Click 'OK' to apply this default theme.")
    def save_and_apply(self):
        theme_to_apply = self.current_local_theme
        theme_name = theme_to_apply.get('name', 'N/A (local)')
        logger.debug(f"[ThemeDialog.save_and_apply] Dialog accepted. Updating global theme with: '{theme_name}'")
        logger.debug(f"[ThemeDialog.save_and_apply] Sample accent color being applied: {theme_to_apply.get('colors',{}).get('text_accent', 'NOT_FOUND')}")
        update_current_theme(theme_to_apply)
        apply_theme()
        logger.info(f"Theme '{theme_name}' settings applied.")


# --- LiveTranslationWindow Dialog ---
# ... (LiveTranslationWindow class remains the same) ...
class LiveTranslationWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Live Translation")
        self.setObjectName("LiveTranslationWindow")
        # --- MODIFIED Window Flags ---
        # Remove Frameless, keep Tool and StaysOnTop
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.Tool)
        # Keep WA_TranslucentBackground for potential rounded corners from stylesheet
        self.setAttribute(Qt.WA_TranslucentBackground)
        # --- END MODIFIED ---
        self.setMinimumSize(250, 60)
        self.offset = None
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
        self.translation_label = QLabel("Waiting for live data...", self)
        self.translation_label.setObjectName("LiveLabel")
        self.translation_label.setWordWrap(True)
        self.translation_label.setAlignment(Qt.AlignCenter)
        self.translation_label.setMinimumHeight(30)
        layout.addWidget(self.translation_label)
        self.setLayout(layout)
    def updateTranslation(self, text):
        """Updates the label content. Handles empty strings."""
        flat_text = text.replace('\n', ' ').strip()
        # Display placeholder if empty, otherwise the text
        display_text = flat_text if flat_text else "..."

        # Only update if the text is actually different to reduce unnecessary paints
        if self.translation_label.text() != display_text:
            self.translation_label.setText(display_text)
            # Use helper for font selection
            self.translation_label.setFont(choose_font_for_text(flat_text, default_font_family="Roboto", font_size=16)) # Slightly smaller default?
            # Adjust dialog size to fit content, but respect minimums
            self.adjustSize()
    def trigger_fade_in(self):
        """Starts the fade-in animation."""
        # Make sure the label is actually visible before starting fade
        if self.label_fade_anim and self.label_opacity_effect:
            self.label_fade_anim.stop()
            self.label_opacity_effect.setOpacity(0.0) # Start from transparent
            self.label_fade_anim.start()
        else:
            logger.warning("Fade animation not setup correctly for LiveTranslationWindow.")
            self.translation_label.setVisible(True) # Fallback

    def load_geometry(self):
        # (load_geometry remains the same)
        settings = load_settings()
        if 'LiveTranslationWindow' in settings:
            try:
                geo = settings['LiveTranslationWindow']
                if all(k in geo for k in ('x', 'y', 'width', 'height')):
                    self.setGeometry(int(geo['x']), int(geo['y']), int(geo['width']), int(geo['height']))
                else:
                    logger.warning("LiveTranslationWindow geometry incomplete. Using default.")
                    self.resize(300, 80)
            except (ValueError, TypeError, KeyError) as e:
                 logger.error(f"Error loading LiveTranslationWindow geometry: {e}. Using default.")
                 self.resize(300, 80)
        else:
            self.resize(300, 80)

    def save_geometry(self):
        # (save_geometry remains the same)
        return { 'x': self.x(), 'y': self.y(), 'width': self.width(), 'height': self.height() }


        if event.button() == Qt.LeftButton:
            self.offset = None
            event.accept()
        else: super().mouseReleaseEvent(event)
    def closeEvent(self, event):
        logger.debug("LiveTranslationWindow closing.")
        event.accept()


# --- ChatWindow ---
# ... (ChatWindow class remains the same) ...
class ChatWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        logger.debug("ChatWindow.__init__ started")
        self.parent_control_window = parent
        self.font_size = 14
        self.ai_streaming_worker = None
        self.last_ai_response = ""
        self.setWindowTitle("AI Chat")
        self.setMinimumSize(500, 400)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint |
                            Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint |
                            Qt.WindowMaximizeButtonHint |
                            (Qt.WindowStaysOnTopHint if parent else Qt.Widget))
        try:
            self.initUI()
            settings = load_settings()
            self.load_geometry(settings)
            logger.debug("ChatWindow.__init__ completed")
        except Exception as e:
            logger.error(f"ChatWindow.__init__ failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Chat Init Error", f"Failed to initialize chat window:\n{e}")
    def initUI(self):
        logger.debug("Initializing ChatWindow UI")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        self.chat_history = QTextEdit(self)
        self.chat_history.setReadOnly(True)
        self.update_chat_history_style()
        logger.debug("Chat history widget created")
        main_layout.addWidget(self.chat_history)
        controls_layout = QHBoxLayout()
        controls_layout.addStretch(1)
        self.decrease_font_btn = QPushButton()
        self.decrease_font_btn.setToolTip("Decrease Font Size (-)")
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "zoom_out.svg")
        if os.path.exists(icon_path):
            self.decrease_font_btn.setIcon(QIcon(icon_path))
            self.decrease_font_btn.setIconSize(QSize(18, 18))
        else: self.decrease_font_btn.setText("-")
        self.decrease_font_btn.setFixedSize(30, 30)
        self.decrease_font_btn.clicked.connect(self.decreaseFontSize)
        controls_layout.addWidget(self.decrease_font_btn)
        self.increase_font_btn = QPushButton()
        self.increase_font_btn.setToolTip("Increase Font Size (+)")
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "zoom_in.svg")
        if os.path.exists(icon_path):
            self.increase_font_btn.setIcon(QIcon(icon_path))
            self.increase_font_btn.setIconSize(QSize(18, 18))
        else: self.increase_font_btn.setText("+")
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
        logger.debug("User input field created")
        input_layout.addWidget(self.user_input, 1)
        self.send_btn = QPushButton()
        self.send_btn.setToolTip("Send Message (Enter)")
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "send.svg")
        if os.path.exists(icon_path):
            self.send_btn.setIcon(QIcon(icon_path))
            self.send_btn.setIconSize(QSize(20, 20))
        else: self.send_btn.setText(">")
        self.send_btn.setFixedSize(40, 40)
        self.send_btn.clicked.connect(self.sendMessage)
        logger.debug("Send button created")
        input_layout.addWidget(self.send_btn)
        main_layout.addLayout(input_layout)
        self.setLayout(main_layout)
        logging.debug("ChatWindow layout set")
        self.append_message("[System]", "AI Chat initialized. Enter your message.", system=True)
    def update_chat_history_style(self):
        theme_colors = get_current_theme().get("colors", DEFAULT_THEME["colors"])
        self.chat_history.setStyleSheet(f"""
            QTextEdit {{
                background-color: {theme_colors.get('bg_input', 'rgba(10, 10, 20, 200)')};
                color: {theme_colors.get('text_light', '#e0e0e0')};
                font-size: {self.font_size}px;
                border-radius: 8px;
                border: 1px solid {theme_colors.get('border_light', 'rgba(255, 255, 255, 20)')};
                padding: 10px;
                font-family: 'Roboto Mono', 'Courier New', monospace;
            }}
        """)
    def update_user_input_style(self):
         theme_colors = get_current_theme().get("colors", DEFAULT_THEME["colors"])
         self.user_input.setStyleSheet(f"""
             QLineEdit {{
                 background-color: {theme_colors.get('bg_input', 'rgba(40, 40, 50, 200)')};
                 color: {theme_colors.get('text_light', '#e0e0e0')};
                 font-size: {self.font_size}px;
                 border-radius: 6px;
                 border: 1px solid {theme_colors.get('border_light', 'rgba(255, 255, 255, 20)')};
                 padding: 8px 10px;
             }}
             QLineEdit:focus {{
                 border: 1px solid {theme_colors.get('border_accent', '#00ffcc')};
             }}
         """)
    def append_message(self, sender, message, system=False):
        theme_colors = get_current_theme().get("colors", DEFAULT_THEME["colors"])
        if system: formatted_message = f"<div style='color: #888888;'><i>[System] {message}</i></div>"
        elif sender == "You":
             escaped_message = textwrap.fill(message.replace('&', '&').replace('<', '<').replace('>', '>'), width=80)
             formatted_message = f"<div style='color: {theme_colors.get('text_light', '#e0e0e0')};'><b>[You]></b><pre style='display: inline; white-space: pre-wrap; font-family: inherit;'> {escaped_message}</pre></div>"
        elif sender == "AI": formatted_message = f"<div style='color: {theme_colors.get('text_accent', '#00ffcc')};'><b>[AI]></b> "
        else:
            escaped_message = message.replace('&', '&').replace('<', '<').replace('>', '>')
            formatted_message = f"<div><b>[{sender}]></b> {escaped_message}</div>"
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        if sender != "AI": cursor.insertHtml(formatted_message + "<br>")
        else: cursor.insertHtml(formatted_message)
        self.chat_history.setTextCursor(cursor)
        self.chat_history.ensureCursorVisible()
    def append_ai_chunk(self, chunk):
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        escaped_chunk = chunk.replace('&', '&').replace('<', '<').replace('>', '>')
        cursor.insertText(escaped_chunk)
        self.chat_history.setTextCursor(cursor)
        self.chat_history.ensureCursorVisible()
    def finish_ai_message(self):
         cursor = self.chat_history.textCursor()
         cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
         cursor.insertHtml("</div><br>")
         self.chat_history.setTextCursor(cursor)
         self.chat_history.ensureCursorVisible()
    def sendMessage(self):
        user_message = self.user_input.text().strip()
        logger.debug(f"User input received: '{user_message}'")
        if not user_message: return
        self.append_message("You", user_message)
        self.user_input.clear()
        self.send_btn.setEnabled(False)
        self.user_input.setEnabled(False)
        self.append_message("AI", "")
        self.start_streaming_response(user_message)
    def start_streaming_response(self, message):
        if self.ai_streaming_worker and self.ai_streaming_worker.isRunning():
            logger.warning("Stopping previous AI streaming worker.")
            self.ai_streaming_worker.stop()
        if not ai_api_config.get("provider"):
            logger.error("Cannot send message: AI provider not configured.")
            self.append_ai_chunk(" Error: AI provider not configured.")
            self.finish_ai_message()
            self.send_btn.setEnabled(True)
            self.user_input.setEnabled(True)
            return
        logger.info(f"Starting AI streaming response ({ai_api_config['provider']})")
        target_lang = 'en'
        if self.parent_control_window and hasattr(self.parent_control_window, 'target_language'):
            target_lang = self.parent_control_window.target_language
        else:
            logger.warning("Could not get target language from parent control window for chat.")
        self.ai_streaming_worker = AIStreamingWorker(message, target_lang, self)
        self.ai_streaming_worker.text_chunk.connect(self.append_ai_chunk)
        self.ai_streaming_worker.finished_stream.connect(self.on_streaming_finished)
        self.ai_streaming_worker.error_stream.connect(self.on_streaming_error)
        self.ai_streaming_worker.start()
    def on_streaming_finished(self, final_response):
        logger.info(f"AI stream finished. Final Text Length: {len(final_response)}")
        self.finish_ai_message()
        self.last_ai_response = final_response
        self.send_btn.setEnabled(True)
        self.user_input.setEnabled(True)
        self.user_input.setFocus()
    def on_streaming_error(self, error_message):
        logger.error(f"AI streaming error: {error_message}")
        self.append_ai_chunk(f" [Stream Error: {error_message}]")
        self.finish_ai_message()
        self.send_btn.setEnabled(True)
        self.user_input.setEnabled(True)
        self.user_input.setFocus()
    def increaseFontSize(self):
        if self.font_size < 24:
            self.font_size += 1
            self.update_chat_history_style()
            self.update_user_input_style()
            logger.debug(f"Chat font size increased to {self.font_size}")
    def decreaseFontSize(self):
        if self.font_size > 9:
            self.font_size -= 1
            self.update_chat_history_style()
            self.update_user_input_style()
            logger.debug(f"Chat font size decreased to {self.font_size}")
    def load_geometry(self, settings):
        if 'ChatWindow' in settings:
            try:
                geometry = settings['ChatWindow']
                if all(k in geometry for k in ('x', 'y', 'width', 'height')):
                    self.setGeometry(int(geometry['x']), int(geometry['y']), int(geometry['width']), int(geometry['height']))
                    logger.debug(f"Loaded ChatWindow geometry: {geometry}")
                else: logger.warning("ChatWindow geometry incomplete.")
            except (ValueError, TypeError, KeyError) as e:
                logger.error(f"Error loading ChatWindow geometry: {e}.")
        else:
            self.resize(550, 450)
    def save_geometry(self):
        logger.debug("ChatWindow.save_geometry returning geometry dict.")
        return { 'x': self.x(), 'y': self.y(), 'width': self.width(), 'height': self.height() }
    def closeEvent(self, event):
        logger.debug("ChatWindow closeEvent called.")
        if self.ai_streaming_worker and self.ai_streaming_worker.isRunning():
            logger.info("Stopping AI streaming worker on chat window close.")
            self.ai_streaming_worker.stop()
        event.accept()



class TranslatedImageViewer(QDialog):
    # Corrected __init__ signature
    def __init__(self, image_path, boxes, translated_lines, initial_font_size, target_language_code, control_window_ref, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.boxes = boxes if boxes else []
        self.translated_lines = translated_lines if translated_lines else []
        self.target_language_code = target_language_code
        self.control_window_ref = control_window_ref # Store reference
        self.original_image = None
        self.rendered_image = None
        self.image_label = None
        self.save_on_close = True # Default to saving

        logger.debug(f"Initializing TranslatedImageViewer for: {os.path.basename(image_path)}")
        logger.debug(f"Target language for font: {target_language_code}, Initial size hint: {initial_font_size}")

        # --- Load style settings specifically for the viewer ---
        vs = {}
        if self.control_window_ref and hasattr(self.control_window_ref, 'last_viewer_settings'):
            vs = self.control_window_ref.last_viewer_settings
            if vs and isinstance(vs, dict): logger.debug("Loaded viewer style settings from ControlWindow reference.")
            else: vs = load_settings().get('viewer_settings', {}); logger.debug("Loaded viewer style settings from file (ControlWindow had none).")
        else: vs = load_settings().get('viewer_settings', {}); logger.warning("ControlWindow ref missing, loaded viewer style settings from file.")

        # --- Use loaded style settings (vs) with defaults ---
        default_font_color_tuple = (255, 255, 255, 255); default_bg_outer_tuple = (0, 0, 0, 200)
        font_color_val = vs.get('font_color', default_font_color_tuple)
        font_color_tuple = tuple(font_color_val) if isinstance(font_color_val, (list, tuple)) and len(font_color_val) == 4 else default_font_color_tuple
        bg_outer_val = vs.get('bg_color_outer', default_bg_outer_tuple)
        bg_outer_tuple = tuple(bg_outer_val) if isinstance(bg_outer_val, (list, tuple)) and len(bg_outer_val) == 4 else default_bg_outer_tuple
        try: self.font_color = QColor(*font_color_tuple); assert self.font_color.isValid()
        except: logger.warning(f"Invalid saved font color {font_color_tuple}. Using default."); self.font_color = QColor(*default_font_color_tuple)
        try: self.bg_color_outer = QColor(*bg_outer_tuple); assert self.bg_color_outer.isValid()
        except: logger.warning(f"Invalid saved BG color {bg_outer_tuple}. Using default."); self.bg_color_outer = QColor(*default_bg_outer_tuple)
        h, s, v, a = self.bg_color_outer.getHsvF(); new_v_inner = max(0, v * 0.9); new_a_inner = min(255, int(self.bg_color_outer.alpha() * 0.9))
        self.bg_color_inner = QColor.fromHsvF(h, s, new_v_inner, new_a_inner / 255.0)
        saved_font_path = vs.get('font_path'); saved_font_size = vs.get('font_size')
        if saved_font_path and isinstance(saved_font_size, int) and os.path.exists(saved_font_path):
            self.font_path = saved_font_path; self.font_size = saved_font_size; logger.info(f"Using saved viewer font: {self.font_path}, Size: {self.font_size}")
        else:
            if saved_font_path or saved_font_size: logger.warning(f"Saved viewer font path/size invalid. Determining new font.")
            else: logger.info("No valid viewer font settings saved. Determining new font.")
            self.font_path = get_system_font_path(self.target_language_code); self.font_size = initial_font_size
            if not self.font_path or not os.path.exists(self.font_path):
                logger.warning(f"Determined font path '{self.font_path}' invalid. Using default."); self.font_path = get_system_font_path("default")
            logger.info(f"Using determined font: {self.font_path}, Size: {self.font_size}")

        try: self.original_image = Image.open(image_path).convert("RGBA")
        except Exception as e:
            logger.error(f"Failed to load image '{image_path}' for viewer: {e}", exc_info=True); QMessageBox.critical(self, "Image Load Error", f"Failed to load image:\n{e}")
            self.save_on_close = False; QTimer.singleShot(0, self.reject); return

        if len(self.translated_lines) != len(self.boxes):
             logger.warning(f"Viewer line/box mismatch ({len(self.translated_lines)}/{len(self.boxes)}). Padding/truncating.")
             diff = len(self.boxes) - len(self.translated_lines)
             if diff > 0: self.translated_lines.extend([""] * diff)
             else: self.translated_lines = self.translated_lines[:len(self.boxes)]

        self.setWindowTitle("Translated Image Viewer")
        self.setMinimumSize(600, 500)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)

        self.initUI()
        self.renderTranslatedImage()
        self.updateImageDisplay()

        # --- Load Geometry --- Moved from control_window.py ---
        settings_for_geom = load_settings() # Load full settings to get geometry
        if 'TranslatedImageViewer' in settings_for_geom:
            try:
                geo = settings_for_geom['TranslatedImageViewer']
                if all(k in geo for k in ('x', 'y', 'width', 'height')):
                    self.setGeometry(int(geo['x']), int(geo['y']), int(geo['width']), int(geo['height']))
                    logger.debug(f"Loaded viewer geometry: {geo}")
                else:
                    logger.warning("Incomplete viewer geometry found. Using default size.")
                    self.resize(700, 550) # Default size
            except (ValueError, TypeError, KeyError) as e:
                logger.error(f"Error loading viewer geometry: {e}. Using default size.")
                self.resize(700, 550)
        else:
            logger.debug("No viewer geometry found. Using default size.")
            self.resize(700, 550) # Default size if key missing
        # --- End Load Geometry ---

    def initUI(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #202020; border-radius: 5px;")
        self.image_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.image_label, 1)

        controls_group = QGroupBox("Display Settings")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setSpacing(8)

        # Font Selection
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
                        if not is_standard: display_name += " (Loaded)"
                        if display_name not in self.font_family_to_path:
                             self.font_combo.addItem(display_name)
                             self.font_family_to_path[display_name] = self.font_path
                             current_font_found_in_db = True
                             current_font_display_name = display_name
                    else:
                         logger.debug("QFontDatabase failed for current path, trying PIL.")
                         try:
                             font_pil = ImageFont.truetype(self.font_path, 10)
                             font_family_name_pil = font_pil.getname()[0]
                             display_name = f"{font_family_name_pil} (Loaded Path)"
                             if display_name not in self.font_family_to_path:
                                  self.font_combo.addItem(display_name)
                                  self.font_family_to_path[display_name] = self.font_path
                                  current_font_found_in_db = True
                                  current_font_display_name = display_name
                         except Exception as pil_e:
                             logger.error(f"PIL failed to load font '{self.font_path}': {pil_e}")
                else: logger.warning(f"QFontDatabase couldn't add font: {self.font_path}")
            except Exception as e: logger.error(f"Error preloading current font '{self.font_path}': {e}")
        for family in available_families:
             styles = font_db.styles(family)
             if styles:
                 try:
                    qfont = font_db.font(family, styles[0], 9)
                    font_info = QFontInfo(qfont)
                    resolved_family = font_info.family()
                    guessed_path = get_system_font_path(resolved_family) # Use helper
                    if guessed_path and os.path.exists(guessed_path) and resolved_family not in self.font_family_to_path:
                         self.font_family_to_path[resolved_family] = guessed_path
                         self.font_combo.addItem(resolved_family)
                         if not current_font_found_in_db and self.font_path and guessed_path.lower() == self.font_path.lower():
                              current_font_found_in_db = True
                              current_font_display_name = resolved_family
                 except Exception as font_err:
                     logger.warning(f"Could not process/map font family '{family}': {font_err}")
        if current_font_display_name and self.font_combo.findText(current_font_display_name) != -1:
            self.font_combo.setCurrentText(current_font_display_name)
            logger.debug(f"Set current font in combo: {current_font_display_name}")
        elif self.font_combo.count() > 0:
             logger.warning(f"Could not set '{current_font_display_name}' in combo. Using first item.")
             self.font_combo.setCurrentIndex(0)
             self.updateFont(self.font_combo.currentText())
        else:
            logger.error("No fonts available to populate font combo box!")
        self.font_combo.currentTextChanged.connect(self.updateFont)
        font_layout.addWidget(self.font_combo, 1)
        controls_layout.addLayout(font_layout)

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

        # Color Pickers
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

        # Action Buttons - SECTION REMOVED
        # button_layout = QHBoxLayout()
        # self.reset_btn = QPushButton("Reset Styles")
        # self.reset_btn.setToolTip("Reset colors and font to defaults")
        # self.reset_btn.clicked.connect(self.resetStyles)
        # self.close_btn = QPushButton("Close")
        # self.close_btn.setToolTip("Save styles and close")
        # self.close_btn.clicked.connect(self.accept) # Connect Close button to accept()
        # button_layout.addWidget(self.reset_btn)
        # button_layout.addStretch(1)
        # button_layout.addWidget(self.close_btn)
        # main_layout.addLayout(button_layout) # Also remove adding the layout


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateImageDisplay()

    def updateFont(self, font_display_name):
        new_path = self.font_family_to_path.get(font_display_name)
        if new_path and os.path.exists(new_path):
            if self.font_path != new_path:
                 self.font_path = new_path
                 logger.debug(f"Viewer font updated to: {font_display_name}, Path: {self.font_path}")
                 self.renderTranslatedImage()
                 self.updateImageDisplay()
        else:
             # Check if the display name exists but path is invalid, log warning
             if font_display_name in self.font_family_to_path:
                 logger.warning(f"Path '{self.font_family_to_path.get(font_display_name)}' for font '{font_display_name}' not found/invalid.")
             else:
                 # This case might happen if the text changes unexpectedly
                 logger.warning(f"Font display name '{font_display_name}' not found in known map.")

             # Attempt to find the current font_path in the map to revert the combo box
             current_display_name = next((name for name, path in self.font_family_to_path.items() if path and self.font_path and path.lower() == self.font_path.lower()), None)
             if current_display_name:
                 # Block signals to prevent recursion if setCurrentText triggers the signal again
                 self.font_combo.blockSignals(True)
                 self.font_combo.setCurrentText(current_display_name)
                 self.font_combo.blockSignals(False)
                 logger.debug(f"Reverted combo box to '{current_display_name}' as fallback.")
             else:
                 logger.warning(f"Could not find display name for current path '{self.font_path}' to revert combo box.")
                 # Optionally, could set to index 0 if no match found


    def updateFontSize(self, value):
        if self.font_size != value:
             self.font_size = value
             self.font_size_value_label.setText(f"{value}pt")
             logger.debug(f"Viewer font size updated to: {self.font_size}")
             # Debounce rendering using a timer
             if not hasattr(self, '_render_timer'):
                 self._render_timer = QTimer(self)
                 self._render_timer.setSingleShot(True)
                 self._render_timer.timeout.connect(self._delayedRenderUpdate)
             self._render_timer.start(200) # Render after 200ms of no changes

    def _delayedRenderUpdate(self):
        self.renderTranslatedImage()
        self.updateImageDisplay()

    def updateFontColor(self, color):
        if self.font_color != color:
            self.font_color = color
            logger.debug(f"Viewer font color updated to: {self.font_color.name(QColor.NameFormat.HexArgb)}")
            self.renderTranslatedImage()
            self.updateImageDisplay()

    def updateBgColor(self, color):
        if self.bg_color_outer != color:
            self.bg_color_outer = color
            # Recalculate inner color based on outer
            h, s, v, a = color.getHsvF()
            new_v_inner = max(0, v * 0.9) # Slightly darker
            new_a_inner = min(255, int(color.alpha() * 0.9)) # Slightly less opaque
            self.bg_color_inner = QColor.fromHsvF(h, s, new_v_inner, new_a_inner / 255.0)
            logger.debug(f"Viewer BG color updated - Outer: {self.bg_color_outer.name(QColor.NameFormat.HexArgb)}, Inner: {self.bg_color_inner.name(QColor.NameFormat.HexArgb)}")
            self.renderTranslatedImage()
            self.updateImageDisplay()


    def renderTranslatedImage(self):
        if not self.original_image:
             logger.error("renderTranslatedImage called with no original image loaded.")
             return
        image = self.original_image.copy()
        draw = ImageDraw.Draw(image)

        # Ensure colors are RGBA tuples for Pillow
        font_color_tuple = self.font_color.getRgb() # -> (r, g, b, a)
        bg_outer_tuple = self.bg_color_outer.getRgb() # -> (r, g, b, a)
        # bg_inner_tuple = self.bg_color_inner.getRgb() # Not used directly in this version

        try:
            font = ImageFont.truetype(self.font_path, self.font_size)
        except (IOError, TypeError, OSError) as e: # Added OSError
             logger.warning(f"Failed to load font '{self.font_path}' size {self.font_size} (Error: {e}). Falling back.")
             fallback_path = get_system_font_path("default")
             try:
                 font = ImageFont.truetype(fallback_path, self.font_size)
                 # If fallback works, update self.font_path for consistency
                 if self.font_path != fallback_path:
                     logger.info(f"Updating font path to fallback: {fallback_path}")
                     self.font_path = fallback_path
                     # Also update the combo box to reflect this change
                     fallback_display_name = next((name for name, path in self.font_family_to_path.items() if path and fallback_path and path.lower() == fallback_path.lower()), None)
                     if fallback_display_name:
                         self.font_combo.blockSignals(True)
                         self.font_combo.setCurrentText(fallback_display_name)
                         self.font_combo.blockSignals(False)

             except (IOError, TypeError, OSError) as fb_e: # Added OSError
                 logger.error(f"Failed to load even default fallback font '{fallback_path}' (Error: {fb_e}). Using PIL default.")
                 font = ImageFont.load_default()
                 self.font_path = None # Indicate no valid path
                 # Clear or disable font combo? Or set to a placeholder?
                 self.font_combo.blockSignals(True)
                 self.font_combo.setCurrentIndex(-1) # No selection
                 self.font_combo.setEnabled(False) # Disable selection
                 self.font_combo.blockSignals(False)

             logger.info(f"Using fallback font: {self.font_path if self.font_path else 'PIL Default'}")


        if not self.boxes:
            # Handle case with no detected text boxes
            try:
                no_text_msg = "(No text detected in original image)"
                # Use textbbox if available (newer Pillow) for better centering
                try:
                    # Anchor 'mm' means middle-middle
                    bbox = draw.textbbox((image.width / 2, image.height / 2), no_text_msg, font=font, anchor='mm')
                    text_anchor_nt = 'mm' # For draw.text
                    draw_pos = (image.width / 2, image.height / 2)
                except (TypeError, AttributeError) as e:
                    # Fallback for older Pillow versions without anchor in textbbox
                    logger.debug(f"Pillow version might not support anchor in textbbox: {e}. Using legacy textlength.")
                    try:
                        # Use textlength if available
                        tw = draw.textlength(no_text_msg, font=font)
                    except AttributeError:
                        # Ultimate fallback: estimate from font.getbbox if possible
                        bbox_legacy = font.getbbox(no_text_msg) if hasattr(font, 'getbbox') else (0, 0, 50, 10) # Guess if no method
                        tw = bbox_legacy[2] - bbox_legacy[0]
                        # Estimate height based on font size (crude)
                    th = self.font_size * 1.2 # Estimate line height
                    tx = (image.width - tw) / 2
                    ty = (image.height - th) / 2
                    bbox = (tx, ty, tx + tw, ty + th) # Create bbox tuple
                    text_anchor_nt = None # draw.text needs top-left without anchor
                    draw_pos = (tx, ty)

                # Draw background rectangle slightly larger than text
                bg_pad = 5
                bg_coords = [(bbox[0] - bg_pad, bbox[1] - bg_pad), (bbox[2] + bg_pad, bbox[3] + bg_pad)]
                draw.rectangle(bg_coords, fill=bg_outer_tuple)
                # Draw the text
                draw.text(draw_pos, no_text_msg, font=font, fill=font_color_tuple, anchor=text_anchor_nt)
            except Exception as e:
                logging.error(f"Error rendering no-text message: {e}", exc_info=True)

        else:
            # Process each box and corresponding translated line
            for i, bbox_coords in enumerate(self.boxes):
                if i >= len(self.translated_lines): continue # Safety check

                line = self.translated_lines[i].strip()
                if not line: continue # Skip empty lines

                left, top, right, bottom = bbox_coords
                box_w = right - left
                box_h = bottom - top
                if box_w <= 0 or box_h <= 0: continue # Skip invalid boxes

                # --- Dynamic Font Sizing & Text Wrapping ---
                # Define target area (slightly larger than original box for padding)
                target_width = box_w * 1.5 # Allow text to be wider than original box
                target_height = box_h * 2.0 # Allow text to be taller

                current_font_size = self.font_size # Start with user-selected size
                temp_font = font # Use the initially loaded font object
                rendered_text = line
                text_width = box_w # Initial guess
                text_height = box_h # Initial guess
                best_fit_font = font # Keep track of the font that fit

                while current_font_size >= 8: # Minimum practical font size
                    try:
                        # Load font at the current trial size
                        if self.font_path:
                            temp_font = ImageFont.truetype(self.font_path, current_font_size)
                        else: # Handle case where using PIL default
                            temp_font = ImageFont.load_default(size=current_font_size) # Note: load_default might not support size
                    except (IOError, TypeError, OSError):
                         logger.warning(f"Failed to load font '{self.font_path}' at size {current_font_size} during fitting. Skipping size.")
                         current_font_size -= 1
                         continue # Try next smaller size

                    # Estimate wrap width based on average character width
                    # This is heuristic: Adjust 0.6 factor if needed
                    avg_char_width_est = max(1, current_font_size * 0.6)
                    wrap_width = max(5, int(target_width / avg_char_width_est)) # Chars per line

                    # Wrap the text
                    wrapped_lines = textwrap.wrap(line, width=wrap_width, replace_whitespace=False, drop_whitespace=False)
                    current_rendered_text = "\n".join(wrapped_lines)

                    # Calculate bounding box of the wrapped text with this font size
                    try:
                        # Use textbbox for accurate measurement if available
                        # Use spacing=4 (or adjust) for multi-line text line spacing
                        text_bbox_calc = draw.textbbox((0, 0), current_rendered_text, font=temp_font, spacing=4)
                        current_text_width = text_bbox_calc[2] - text_bbox_calc[0]
                        current_text_height = text_bbox_calc[3] - text_bbox_calc[1]
                    except Exception as e:
                        logger.warning(f"textbbox failed during size check: {e}. Using estimate.")
                        # Estimate if textbbox fails
                        current_text_width = target_width # Assume it might fill width
                        current_text_height = current_font_size * len(wrapped_lines) * 1.2 # Estimate height

                    # Check if it fits within the target area
                    if current_text_width <= target_width and current_text_height <= target_height:
                        # It fits! Store this version and break the loop.
                        rendered_text = current_rendered_text
                        text_width = current_text_width
                        text_height = current_text_height
                        best_fit_font = temp_font # Use this font size
                        logger.debug(f"Box {i}: Text fit at size {current_font_size} (w:{text_width:.0f}<={target_width:.0f}, h:{text_height:.0f}<={target_height:.0f})")
                        break # Found a suitable size

                    # If it doesn't fit, reduce font size and try again
                    current_font_size -= 1
                else:
                    # Loop finished without finding a fit (reached min size)
                    logger.warning(f"Box {i}: Text '{line[:20]}...' wouldn't fit target area even at min size 8. Using smallest attempt.")
                    # Use the last attempted (smallest) size and its wrapped text
                    rendered_text = current_rendered_text
                    text_width = current_text_width
                    text_height = current_text_height
                    best_fit_font = temp_font # Use the smallest font tried

                # --- Drawing ---
                # Calculate final position (centered within the original bbox)
                final_text_x = left + (box_w - text_width) / 2
                final_text_y = top + (box_h - text_height) / 2

                # Calculate background rectangle coordinates based on actual text size
                bg_pad_x, bg_pad_y = 3, 2 # Padding around the text
                bg_left = final_text_x - bg_pad_x
                bg_top = final_text_y - bg_pad_y
                bg_right = final_text_x + text_width + bg_pad_x
                bg_bottom = final_text_y + text_height + bg_pad_y

                # Clamp background coordinates to image boundaries
                bg_left = max(0, bg_left)
                bg_top = max(0, bg_top)
                bg_right = min(image.width, bg_right)
                bg_bottom = min(image.height, bg_bottom)

                try:
                    # Draw the semi-transparent background
                    draw.rectangle([(bg_left, bg_top), (bg_right, bg_bottom)], fill=bg_outer_tuple)
                    # Draw the (potentially wrapped) text using the determined best_fit_font
                    draw.text((final_text_x, final_text_y), rendered_text, font=best_fit_font, fill=font_color_tuple, spacing=4) # Added spacing
                except Exception as draw_err:
                     logger.error(f"Error drawing text/bg for box {i}: {draw_err}", exc_info=True)

        self.rendered_image = image
        logger.debug("Image rendering complete.")

    def updateImageDisplay(self):
        if not self.rendered_image or not self.image_label: return
        try:
            im = self.rendered_image
            # Ensure image is RGBA for QImage format
            if im.mode != "RGBA":
                im = im.convert("RGBA")

            # Create QImage from PIL image bytes
            qimage = QImage(im.tobytes(), im.width, im.height, QImage.Format.Format_RGBA8888)

            if qimage.isNull():
                 logger.error("Failed to create QImage from rendered PIL image.")
                 return

            pixmap = QPixmap.fromImage(qimage)

            # Scale pixmap to fit label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)

            self.image_label.setPixmap(scaled_pixmap)
        except Exception as e:
            logger.error(f"Error updating image display: {e}", exc_info=True)

    def auto_save_image(self):
        save_path = None
        if self.rendered_image and self.save_on_close:
            try:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                ensure_support_folder() # Make sure the folder exists
                base_name = os.path.splitext(os.path.basename(self.image_path))[0]
                # Determine suffix based on original filename pattern
                suffix = "translated_snip" if "snip_" in base_name else "translated_capture"
                # Clean base name
                clean_base = base_name.replace("capture_", "").replace("snip_", "")
                save_filename = f"{clean_base}_{suffix}_{timestamp}.png"
                save_path = os.path.join(SUPPORT_FOLDER, save_filename)
                logger.info(f"Auto-saving translated image to: {save_path}")
                # Save as PNG to preserve transparency
                self.rendered_image.save(save_path, format='PNG')
            except Exception as e:
                error_location = save_path if save_path else "unknown path"
                logger.error(f"Failed to auto-save image to {error_location}: {e}", exc_info=True)
                # Optionally notify user via tray icon if available
                parent_window = self.control_window_ref
                if parent_window and hasattr(parent_window, 'tray_icon') and parent_window.tray_icon and parent_window.tray_icon.isVisible():
                     failed_filename = os.path.basename(save_path) if save_path else "image"
                     parent_window.tray_icon.showMessage(
                         "Save Error", f"Failed to save {failed_filename}.",
                         QSystemTrayIcon.MessageIcon.Warning, 3000 # Show warning for 3 seconds
                     )
        elif not self.save_on_close:
            logger.debug("Auto-save skipped because save_on_close is False.")
        else:
             logger.warning("Auto-save skipped: No rendered image available.")

    def get_viewer_settings(self):
        # (This method remains the same)
        settings = {
            'font_color': list(self.font_color.getRgb()),
            'bg_color_outer': list(self.bg_color_outer.getRgb()),
            'font_path': self.font_path,
            'font_size': self.font_size
        }
        logger.debug(f"get_viewer_settings returning: {settings}")
        return settings

    def get_geometry_settings(self):
        # (This method remains the same)
        return { 'x': self.x(), 'y': self.y(), 'width': self.width(), 'height': self.height() }


    def closeEvent(self, event):
        """Override close event to save styles, geometry, and image."""
        logger.debug("TranslatedImageViewer closeEvent triggered.")
        # --- Update style settings in ControlWindow ---
        if self.control_window_ref and hasattr(self.control_window_ref, 'update_last_viewer_settings'):
            current_style_settings = self.get_viewer_settings()
            self.control_window_ref.update_last_viewer_settings(current_style_settings)
            logger.debug("Updated ControlWindow's last viewer style settings.")
        else:
            logger.warning("Could not update last viewer style settings: ControlWindow reference missing.")
        # --- End Update Style Settings ---

        # --- Auto-save image ---
        self.auto_save_image()
        # --- End Auto-save ---

        # --- Note: Geometry saving happens centrally in ControlWindow.gather_current_state ---
        # No need to save geometry directly here, but it's captured when the main app saves.

        super().closeEvent(event) # Proceed with closing

    def accept(self):
        """Handle OK/Close button press."""
        logger.debug("TranslatedImageViewer accepted (Close button).")
        # Settings are now saved via closeEvent, just accept the dialog.
        super().accept() # Call the original accept method (which triggers closeEvent)

    # --- MODIFIED reject ---
    def reject(self):
        """Handle dialog rejection (e.g., Esc, 'X' button)."""
        logger.debug("TranslatedImageViewer rejected (Esc/'X').")
        # Settings are now saved via closeEvent, just reject the dialog.
        super().reject() # Call the original reject method (which triggers closeEvent)
        
# --- Example Usage (requires a valid image path) ---
if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)

    # Create dummy data
    img_path = "test_image.png" # <<< REPLACE WITH A REAL IMAGE PATH
    # Create a dummy image if it doesn't exist
    if not os.path.exists(img_path):
        try:
            dummy_img = Image.new('RGB', (400, 300), color = (73, 109, 137))
            d = ImageDraw.Draw(dummy_img)
            d.text((10,10), "Hello World", fill=(255,255,0))
            dummy_img.save(img_path)
            print(f"Created dummy image: {img_path}")
        except Exception as e:
            print(f"Could not create dummy image: {e}")
            sys.exit(1)


    boxes = [
        [50, 50, 150, 80],
        [100, 120, 300, 180]
    ]
    translated = [
        "Bonjour le Monde",
        "Ceci est une ligne de texte plus longue qui pourrait nécessiter un retour à la ligne."
    ]
    initial_font_size = 20
    lang = 'fr'
    # Dummy control window reference (can be None or a mock object)
    class MockControlWindow:
        last_viewer_settings = load_settings().get('viewer_settings', {}) # Load initial if available
        default_font_size = 18 # Example attribute
        tray_icon = None # No tray icon in mock
        def update_last_viewer_settings(self, settings):
            print(f"MockControlWindow: Received settings update: {settings}")
            self.last_viewer_settings = settings
            # In a real app, you might save settings here too
            # save_settings({'viewer_settings': settings}) # Example
    mock_control = MockControlWindow()

    viewer = TranslatedImageViewer(img_path, boxes, translated, initial_font_size, lang, mock_control)
    result = viewer.exec_() # Show the dialog modally

    print(f"Dialog closed with result: {result}") # 0 = Rejected, 1 = Accepted
    print(f"Final settings in mock control: {mock_control.last_viewer_settings}")

    sys.exit(app.exec_())
