# gui/control_window.py
import os
import platform
import subprocess
import webbrowser
import datetime
import shutil
import json
import logging
import time
import zipfile
import keyring # Moved here

from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QInputDialog, QSlider, QMessageBox, QProgressBar, QSystemTrayIcon, QMenu,
    QFileDialog, QGroupBox, QCheckBox, QLineEdit, QApplication, QMenuBar, QDialog, # Added QApplication, QMenuBar
 # Explicit import
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize, QPropertyAnimation, QPoint, QRect, QEasingCurve, QThread # Added QThread for worker check
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QColor, QFont, QActionGroup  # Added QFont
from PySide6.QtGui import QShortcut, QAction # Explicitly import QShortcut, QAction

# Internal imports (relative)
from .capture_widget import CaptureWidget
from .snipping_tool import SnippingTool
from .dialogs import IntroDialog, ChatWindow, LiveTranslationWindow, ThemeDialog # Import necessary dialogs
from .resource_monitor import ResourceMonitorWidget # Import the new monitor

# Worker imports
from workers import TranslationWorker

# Utility imports
from utils.config import SUPPORT_FOLDER, ai_api_config, ensure_support_folder, MIN_OPACITY, PROJECT_ROOT, PREDEFINED_THEMES, DEFAULT_THEME, logger, get_current_theme, update_current_theme
from utils.helpers import (
    load_settings, save_settings, apply_theme, choose_font_for_text, get_system_font_path # Import helpers
)
from utils.ocr_utils import initialize_paddle_ocr # Import OCR initializer

# Import PIL for saving metadata check
from PIL import Image

class ControlWindow(QMainWindow):
    translation_error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        logger.info("Initializing ControlWindow...")
        self.live_translation_popout = None
        self.chat_window = None
        self.source_language = 'auto' # Default source
        self.target_language = 'en' # Default target
        self.tray_icon = None
        self.default_font_size = 20
        self.default_font_type = "default"
        self.translate_with_ai_enabled = False
        self.capture_widget = None
        self.snipping_tool = None
        self.font_size = 16 # For live preview label in this window
        self.translation_worker = None
        self.is_live_capturing = False
        self.current_settings = {} # To hold loaded settings

        # --- State for window visibility on restore ---
        self.chat_window_was_visible = False
        self.live_translation_popout_was_visible = False
        # --- End State ---
        # --- State for last viewer settings --- ## ADDED ##
        self.last_viewer_settings = {}
        # --- End State ---

        # Load initial settings (including AI config and theme)
        self.current_settings = load_settings()
        # --- Load last viewer settings from loaded config --- ## ADDED ##
        self.last_viewer_settings = self.current_settings.get("viewer_settings", {})
        logger.debug(f"Loaded initial last_viewer_settings: {self.last_viewer_settings}")
        # --- End Load ---


        # Show intro dialog first (parented to self)
        self.showIntroDialog()

        # Now initialize CaptureWidget and SnippingTool
        try:
            # Pass self (ControlWindow) to CaptureWidget
            self.capture_widget = CaptureWidget(control_window=self)
            self.snipping_tool = SnippingTool(self.capture_widget)
        except Exception as e:
             logger.critical(f"Failed to initialize CaptureWidget/SnippingTool: {e}", exc_info=True)
             QMessageBox.critical(self, "Startup Error", f"Failed to initialize core components:\n{e}")
             # Graceful exit? For now, continue but things might break.
             # sys.exit(1) # Or perhaps raise the error

        self.initUI() # Initialize main UI elements
        self.setupGlobalShortcuts()
        self.load_state_from_settings() # Apply loaded geometry, opacity, etc.
        ensure_support_folder() # Redundant check, but safe

        # Connect error signal from this window
        self.translation_error_occurred.connect(self.displayTranslationError)
        logger.info("ControlWindow initialization complete.")

    def showIntroDialog(self):
        # (Keep the existing showIntroDialog method here)
        # Ensure IntroDialog is imported from .dialogs
        intro_dialog = IntroDialog(self)
        intro_dialog.exec()

    # Removed load_ai_api_config - handled by load_settings

    def initUI(self):
        self.setWindowTitle('Overlay Translate Control')
        # Use standard window flags, allow resizing
        flags = Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
        self.setWindowFlags(flags)

        # --- Central Widget and Layout ---
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # --- Capture Controls Group ---
        capture_group = QGroupBox("Capture Controls")
        capture_layout = QHBoxLayout()
        # Buttons created using helper method
        self.capture_btn = self._createButton('Capture (F1)', self.captureScreen, 'capture.svg', "Capture selected area and translate")
        self.live_capture_btn = self._createButton('Live (F3)', self.toggleLiveCapture, 'live.svg', "Toggle continuous live translation", checkable=True) # Make checkable
        self.snip_btn = self._createButton('Snip (F4)', self.activateSnippingTool, 'snip.svg', "Select a new area with snipping tool")
        capture_layout.addWidget(self.capture_btn)
        capture_layout.addWidget(self.live_capture_btn)
        capture_layout.addWidget(self.snip_btn)
        capture_group.setLayout(capture_layout)
        main_layout.addWidget(capture_group)

        # --- Live Translation Preview Group ---
        live_display_group = QGroupBox("Live Translation Preview")
        live_display_layout = QVBoxLayout()
        self.live_translation_label = QLabel("Live translation disabled.", self)
        self.live_translation_label.setWordWrap(True)
        self.live_translation_label.setAlignment(Qt.AlignCenter)
        self.live_translation_label.setObjectName("ControlWindowLiveLabel") # For specific styling if needed
        # Initial style set here, but theme will override most
        self.live_translation_label.setStyleSheet("""
            QLabel#ControlWindowLiveLabel {
                border-radius: 10px;
                padding: 15px;
                font-size: 16px;
                min-height: 50px;
                /* Background/color handled by global theme */
            }
        """)
        # Opacity effect for fade-in/out
        self.label_opacity_effect = QtWidgets.QGraphicsOpacityEffect(self.live_translation_label)
        self.live_translation_label.setGraphicsEffect(self.label_opacity_effect)
        self.label_fade_anim = QPropertyAnimation(self.label_opacity_effect, b"opacity", self)
        self.label_fade_anim.setDuration(400)
        self.label_fade_anim.setStartValue(0.0)
        self.label_fade_anim.setEndValue(1.0)
        self.label_fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        live_display_layout.addWidget(self.live_translation_label)

        # Font Size Controls for Preview
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("Preview Size:", self))
        font_layout.addStretch(1)
        self.decrease_font_btn = self._createButton('-', self.decreaseFontSize, 'zoom_out.svg', "Decrease preview font size", fixed_size=QSize(40, 40))
        self.increase_font_btn = self._createButton('+', self.increaseFontSize, 'zoom_in.svg', "Increase preview font size", fixed_size=QSize(40, 40))
        font_layout.addWidget(self.decrease_font_btn)
        font_layout.addWidget(self.increase_font_btn)
        live_display_layout.addLayout(font_layout)
        live_display_group.setLayout(live_display_layout)
        main_layout.addWidget(live_display_group)

        # --- Settings Group ---
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(10)
        # Click-Through Toggle
        initial_tooltip = "Allow mouse clicks to pass through the overlay"
        self.toggle_btn = self._createButton('Make Click-Through (F2)', self.toggleCaptureWidgetClickThrough, 'click.svg', initial_tooltip)
        settings_layout.addWidget(self.toggle_btn)
        # Opacity Slider
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Overlay Opacity:", self))
        self.opacity_slider = QSlider(Qt.Horizontal, self)
        # Range from MIN_OPACITY*100 to 100
        min_opacity_int = max(1, int(MIN_OPACITY * 100)) # Ensure minimum is at least 1
        self.opacity_slider.setRange(min_opacity_int, 100)
        self.opacity_slider.valueChanged.connect(self.adjustCaptureWidgetOpacity)
        opacity_layout.addWidget(self.opacity_slider)
        settings_layout.addLayout(opacity_layout)
        # Translate with AI Toggle
        self.translate_with_ai_toggle = QPushButton('Use AI Translation: OFF', self)
        self.translate_with_ai_toggle.setCheckable(True)
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
        self.translation_progress_bar.setVisible(False)
        main_layout.addWidget(self.translation_progress_bar)

        # --- Menu Bar ---
        self.setMenuBar(self.createMenuBar())

        # --- Status Bar ---
        self.statusBar = QtWidgets.QStatusBar(self)
        self.setStatusBar(self.statusBar)
        self.statusBar.setSizeGripEnabled(False) # Disable corner grip

        # Add Resource Monitor to Status Bar
        self.resource_monitor_widget = ResourceMonitorWidget(self)
        self.statusBar.addPermanentWidget(self.resource_monitor_widget)
        self.statusBar.show() # Ensure status bar is visible

        # --- Show Capture Widget ---
        if self.capture_widget:
            self.capture_widget.show()
        else:
            logger.error("CaptureWidget not initialized before attempting to show!")
            # QMessageBox.critical(self, "Startup Error", "Failed to show capture overlay.")

        # --- Live Capture Timer ---
        self.live_capture_timer = QTimer(self)
        self.live_capture_timer.timeout.connect(self.captureScreenForLiveTranslation)
        # Reduced interval for more responsive live updates
        self.live_capture_timer.setInterval(3000) # 3 seconds

        # --- Tray Icon ---
        self.initTrayIcon()

        # Apply initial state loaded earlier
        self.apply_initial_settings()


    def apply_initial_settings(self):
        """Applies settings loaded during __init__."""
        # AI Toggle State
        self.translate_with_ai_enabled = self.current_settings.get('settings', {}).get('translate_with_ai', False)
        self.translate_with_ai_toggle.setChecked(self.translate_with_ai_enabled)
        self._update_ai_toggle_style() # Update button appearance
        logger.info(f"Applied initial AI toggle state: {self.translate_with_ai_enabled}")

        # Font settings
        fs = self.current_settings.get('font_settings', {})
        self.default_font_size = fs.get('size', 20)
        self.default_font_type = fs.get('type', 'default')
        if self.capture_widget:
            self.capture_widget.default_font_size = self.default_font_size
            self.capture_widget.default_font_type = self.default_font_type
        logger.info(f"Applied initial font settings: Size={self.default_font_size}, Type={self.default_font_type}")

        # Opacity (Slider value set based on loaded CaptureWidget state)
        capture_state = self.current_settings.get('CaptureWidget', {})
        loaded_opacity = capture_state.get('opacity', 0.8)
        # Clamp loaded opacity to slider range before setting
        min_slider_val = self.opacity_slider.minimum()
        max_slider_val = self.opacity_slider.maximum()
        slider_value = int(max(min_slider_val / 100.0, min(max_slider_val / 100.0, loaded_opacity)) * 100)
        self.opacity_slider.setValue(slider_value)
        # Initial opacity application happens in CaptureWidget.load_state

        # Live capture button state (should default to off)
        self.live_capture_btn.setChecked(False)
        self._update_live_button_style(False) # Set initial style

    def load_state_from_settings(self):
        """Loads geometry for ControlWindow from the loaded settings."""
        if 'ControlWindow' in self.current_settings:
            try:
                geometry = self.current_settings['ControlWindow']
                if all(k in geometry for k in ('x', 'y', 'width', 'height')):
                    self.setGeometry(int(geometry['x']), int(geometry['y']), int(geometry['width']), int(geometry['height']))
                    logger.debug(f"Loaded ControlWindow geometry: {geometry}")
                else:
                    logger.warning("ControlWindow geometry incomplete. Using default.")
                    self.resize(500, 650) # Default size
            except (ValueError, TypeError, KeyError) as e:
                 logger.error(f"Error loading ControlWindow geometry: {e}. Using default.")
                 self.resize(500, 650)
        else:
            logger.info("No ControlWindow geometry found. Using default size.")
            self.resize(500, 650) # Default size


    def createMenuBar(self):
        # (Keep the existing createMenuBar method here)
        # Ensure ThemeDialog is imported from .dialogs
        # Ensure ChatWindow is imported from .dialogs
        # Ensure LiveTranslationWindow is imported from .dialogs
        # Ensure QAction, QKeySequence are imported
        menu_bar = QMenuBar(self)

        # File Menu
        # --- File Menu (Keep as is) ---
        file_menu = menu_bar.addMenu("&File")
        tray_action = QAction("Minimize to Tray", self)
        tray_action.triggered.connect(self.minimizeToTray)
        file_menu.addAction(tray_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.closeApplication)
        exit_action.setShortcut(QKeySequence.Quit)
        file_menu.addAction(exit_action)

        # --- Settings Menu (Modified Theme part) ---
        settings_menu = menu_bar.addMenu("&Settings")
        # ... (Keep Language, Font, AI, Server items) ...
        lang_menu = settings_menu.addMenu("Translation Languages")
        src_lang_action = QAction("Set Source Language...", self)
        src_lang_action.triggered.connect(self.selectSourceLanguage)
        lang_menu.addAction(src_lang_action)
        tgt_lang_action = QAction("Set Target Language...", self)
        tgt_lang_action.triggered.connect(self.selectTargetLanguage)
        lang_menu.addAction(tgt_lang_action)

        font_menu = settings_menu.addMenu("Translation Font")
        font_size_action = QAction("Set Default Font Size...", self)
        font_size_action.triggered.connect(self.setDefaultFontSize)
        font_menu.addAction(font_size_action)
        font_type_action = QAction("Set Default Font Type...", self)
        font_type_action.triggered.connect(self.setDefaultFontType)
        font_menu.addAction(font_type_action)

        settings_menu.addSeparator()
        ai_menu = settings_menu.addMenu("AI Configuration")
        config_ai_action = QAction("Configure AI Provider...", self)
        config_ai_action.triggered.connect(self.configureAIAPI)
        ai_menu.addAction(config_ai_action)
        toggle_ai_action = QAction("Toggle AI Translation", self)
        toggle_ai_action.setCheckable(True)
        toggle_ai_action.setChecked(self.translate_with_ai_enabled)
        toggle_ai_action.toggled.connect(self.translate_with_ai_toggle.setChecked) # Link check states
        self.translate_with_ai_toggle.toggled.connect(toggle_ai_action.setChecked)
        ai_menu.addAction(toggle_ai_action)

        settings_menu.addSeparator()
        server_action = QAction("Open Translation Server UI", self)
        server_action.triggered.connect(self.openServer)
        settings_menu.addAction(server_action)

        settings_menu.addSeparator() # Separator before Theme menu

        # --- NEW: Theme Selection Submenu ---
        theme_menu = settings_menu.addMenu("Select Theme")
        self.theme_action_group = QActionGroup(self) # Group for exclusivity
        self.theme_action_group.setExclusive(True)

        # Ensure get_current_theme() is accessible here (it should be via import)
        current_theme_name = get_current_theme().get("name", DEFAULT_THEME["name"])

        # Dynamically create actions for each predefined theme
        for theme_name in PREDEFINED_THEMES.keys():
            action = QAction(theme_name, self, checkable=True)
            # Use lambda to capture the correct theme_name for the slot
            action.triggered.connect(lambda checked=False, name=theme_name: self.switch_theme(name))
            if theme_name == current_theme_name:
                action.setChecked(True)
            theme_menu.addAction(action)
            self.theme_action_group.addAction(action) # Add to group

        # --- Tools Menu (Keep as is) ---
        tools_menu = menu_bar.addMenu("&Tools")
        chat_action = QAction("Open AI Chat", self)
        chat_action.triggered.connect(self.openChatWindow)
        chat_action.setShortcut(QKeySequence("Ctrl+T"))
        tools_menu.addAction(chat_action)
        live_popout_action = QAction("Pop Out Live Translation", self)
        live_popout_action.triggered.connect(self.popOutLiveTranslation)
        tools_menu.addAction(live_popout_action)


        # Help Menu
        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.showAboutDialog)
        help_menu.addAction(about_action)
        folder_action = QAction("Open Support Folder", self) # Keep this
        folder_action.triggered.connect(self.openSupportFolder)
        help_menu.addAction(folder_action)

        return menu_bar

    def openSupportFolder(self):
        # (Keep the existing openSupportFolder method here)
        folder_path = SUPPORT_FOLDER
        logger.info(f"Opening Support Folder: {folder_path}")
        try:
            if not os.path.exists(folder_path):
                logger.warning(f"Support folder does not exist at {folder_path}. Attempting to create.")
                ensure_support_folder()
                if not os.path.exists(folder_path):
                    QMessageBox.warning(self, "Folder Not Found", f"The Support folder could not be found or created at:\n{folder_path}")
                    return

            system = platform.system()
            if system == "Windows":
                os.startfile(folder_path)
            elif system == "Darwin":
                subprocess.Popen(["open", folder_path])
            else:
                subprocess.Popen(["xdg-open", folder_path])
        except FileNotFoundError:
             QMessageBox.warning(self, "File Explorer Error", f"Could not find the file explorer application to open:\n{folder_path}")
        except Exception as e:
             logger.error(f"Failed to open support folder '{folder_path}': {e}", exc_info=True)
             QMessageBox.warning(self, "Error", f"Could not open the Support folder.\nError: {e}")

    # --- NEW: Slot to Switch Theme ---
    def switch_theme(self, theme_name):
        """Applies the selected predefined theme."""
        if theme_name in PREDEFINED_THEMES:
            selected_theme_dict = PREDEFINED_THEMES[theme_name]
            current_theme_name = get_current_theme().get("name")

            if current_theme_name != theme_name:
                logger.info(f"Switching theme to: '{theme_name}'")
                update_current_theme(selected_theme_dict) # Update global state
                apply_theme() # Apply the new theme stylesheet globally

                # Update the check state in the menu (ActionGroup might do this automatically)
                for action in self.theme_action_group.actions():
                    if action.text() == theme_name:
                        # Check if already checked to avoid redundant signals
                        if not action.isChecked():
                             action.setChecked(True)
                        break
            else:
                logger.debug(f"Theme '{theme_name}' is already active.")
                # Ensure the correct action is checked even if theme name didn't change (e.g., on startup)
                for action in self.theme_action_group.actions():
                     action.setChecked(action.text() == theme_name)

        else:
            logger.error(f"Attempted to switch to unknown theme: '{theme_name}'")


    def _createButton(self, text, callback, icon_name, tooltip="", fixed_size=None, checkable=False):
        """Internal helper to create themed buttons."""
        button = QPushButton(text, self)
        if icon_name:
            icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", icon_name)
            if os.path.exists(icon_path):
                button.setIcon(QIcon(icon_path))
                button.setIconSize(QSize(18, 18))
            else:
                logger.warning(f"Icon not found for button '{text}': {icon_path}")

        button.clicked.connect(callback)
        button.setToolTip(tooltip)
        button.setCheckable(checkable) # Set checkable property

        # Styling is now primarily handled by the global theme stylesheet
        # We might add object names for very specific overrides if needed
        # button.setObjectName(f"ControlBtn_{text.replace(' ','')}")

        if fixed_size:
            button.setFixedSize(fixed_size)
        else:
            # Ensure reasonable minimum size even if text/icon is small
             button.setMinimumHeight(35)
             button.setMinimumWidth(60)

        # Optional: Add shadow effect from theme if desired (less common for internal buttons)
        # shadow = QtWidgets.QGraphicsDropShadowEffect()
        # shadow.setBlurRadius(10)
        # shadow.setColor(QColor(0, 0, 0, 80))
        # shadow.setOffset(1, 1)
        # button.setGraphicsEffect(shadow)

        return button

    def _update_ai_toggle_style(self):
        # (Keep the existing update_ai_toggle_style method here, renamed with _)
        # Uses setStyleSheet, relies on specificity or !important to override base theme if needed
        # Or preferably, use properties/pseudo-states if the theme supports it.
        base_style = """
            QPushButton { /* Base properties from theme */ }
            QPushButton:checked { /* Checked state styles */ }
            QPushButton:hover { /* Hover styles */ }
            QPushButton:pressed { /* Pressed styles */ }
        """ # Placeholder - actual style comes from global stylesheet

        if self.translate_with_ai_toggle.isChecked():
            self.translate_with_ai_toggle.setText('Use AI Translation: ON')
            # Apply a specific object name or property for styling checked state
            self.translate_with_ai_toggle.setProperty("aiActive", True)
        else:
            self.translate_with_ai_toggle.setText('Use AI Translation: OFF')
            self.translate_with_ai_toggle.setProperty("aiActive", False)

        # Re-polish to apply property-based styles from the main stylesheet
        self.translate_with_ai_toggle.style().unpolish(self.translate_with_ai_toggle)
        self.translate_with_ai_toggle.style().polish(self.translate_with_ai_toggle)

        # Example inline style override (less ideal than theme):
        # style_on = "background-color: #2ECC71;"
        # style_off = "background-color: #E74C3C;"
        # self.translate_with_ai_toggle.setStyleSheet(style_on if self.translate_with_ai_toggle.isChecked() else style_off)


    def _update_live_button_style(self, is_live):
        """Updates the Live Capture button style and text."""
        if is_live:
            self.live_capture_btn.setText('Stop (F3)')
            icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "stop.svg")
            if os.path.exists(icon_path): self.live_capture_btn.setIcon(QIcon(icon_path))
            self.live_capture_btn.setToolTip("Stop continuous live translation")
            # Apply a property or specific style for 'active' state
            self.live_capture_btn.setProperty("liveActive", True)
        else:
            self.live_capture_btn.setText('Live (F3)')
            icon_path = os.path.join(PROJECT_ROOT, "assets", "icons", "live.svg")
            if os.path.exists(icon_path): self.live_capture_btn.setIcon(QIcon(icon_path))
            self.live_capture_btn.setToolTip("Toggle continuous live translation")
            self.live_capture_btn.setProperty("liveActive", False)

        # Re-polish to apply property-based styles
        self.live_capture_btn.style().unpolish(self.live_capture_btn)
        self.live_capture_btn.style().polish(self.live_capture_btn)

    def toggleTranslateWithAI(self, checked):
        # (Keep the existing toggleTranslateWithAI method here)
        logger.debug(f"AI Toggle changed: {checked}")
        if checked:
            # Disable AI if live capture is running
            if self.is_live_capturing:
                QMessageBox.warning(self, "Live Capture Active", "AI translation is disabled during live capture.")
                self.translate_with_ai_toggle.setChecked(False) # Revert button state
                return # Prevent enabling AI
            # Check if AI is configured
            if not ai_api_config.get("provider"):
                QMessageBox.warning(self, "AI Not Configured", "Please configure an AI API provider first in Settings > AI Configuration.")
                self.translate_with_ai_toggle.setChecked(False) # Revert button state
                return # Prevent enabling AI

        self.translate_with_ai_enabled = checked
        self._update_ai_toggle_style() # Update visual style
        logger.info(f"Translate with AI {'enabled' if checked else 'disabled'}")
        # Saving handled on exit

    def toggleLiveCapture(self):
        # (Keep the existing toggleLiveCapture method here)
        if self.is_live_capturing:
            # --- Stop Live Capture ---
            self.live_capture_timer.stop()
            self.is_live_capturing = False
            self._update_live_button_style(False) # Update button style/text
            self.live_translation_label.setText("Live translation disabled.")
            # Ensure fade animation is reset or label is visible
            self.label_opacity_effect.setOpacity(1.0)

            # Stop any running translation worker associated with live capture
            if self.translation_worker and self.translation_worker.isRunning() and self.translation_worker.live:
                 logger.info("Stopping active live translation worker.")
                 self.translation_worker.stop()
            logger.info("Live capture stopped.")

        else:
            # --- Start Live Capture ---
            # Automatically disable AI if it was enabled
            if self.translate_with_ai_enabled:
                 # No message box needed, just disable it silently
                 self.translate_with_ai_toggle.setChecked(False)
                 logger.info("AI translation disabled automatically for live capture.")

            # Check if capture widget exists and is visible
            if not self.capture_widget or not self.capture_widget.isVisible():
                 QMessageBox.warning(self, "Overlay Hidden", "Please ensure the capture overlay is visible before starting live capture.")
                 self.live_capture_btn.setChecked(False) # Uncheck the button
                 return

            # Start the timer and update state
            self.live_capture_timer.start()
            self.is_live_capturing = True
            self._update_live_button_style(True) # Update button style/text
            self.live_translation_label.setText("Live capture active...")
            # Ensure fade animation is reset or label is visible
            self.label_opacity_effect.setOpacity(1.0)
            # Trigger initial capture immediately
            QTimer.singleShot(50, self.captureScreenForLiveTranslation)
            logger.info("Live capture started.")


    def captureScreen(self):
        # (Keep the existing captureScreen method here)
        # Ensure SUPPORT_FOLDER, logger are imported
        # Ensure QMessageBox, QApplication are imported
        # Ensure Image is imported from PIL
        if not self.capture_widget or not self.capture_widget.isVisible():
            QMessageBox.warning(self, "Overlay Hidden", "Please ensure the capture overlay is visible.")
            return

        # Show progress
        self.translation_progress_bar.setVisible(True)
        self.translation_progress_bar.setValue(0)
        self.translation_progress_bar.setFormat("Capturing...")
        QApplication.processEvents() # Update UI to show progress bar

        screenshot = None
        fileName = ""
        try:
            overlay_geometry = self.capture_widget.geometry()
            screen = QApplication.primaryScreen()
            if not screen:
                raise Exception("Could not get primary screen.")

            # Short delay and hide overlay *before* capture for cleaner shots
            self.capture_widget.hide()
            QApplication.processEvents()
            time.sleep(0.08) # Small delay after hide

            logger.debug(f"Grabbing screen area: {overlay_geometry}")
            # Capture desktop content (window ID 0) within the geometry
            screenshot = screen.grabWindow(0, overlay_geometry.x(), overlay_geometry.y(), overlay_geometry.width(), overlay_geometry.height())

            # Show overlay again immediately
            self.capture_widget.show()
            QApplication.processEvents()

            if screenshot.isNull():
                raise Exception("Failed to grab screenshot (returned null pixmap).")

            # Save screenshot
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            ensure_support_folder() # Use helper
            fileName = os.path.join(SUPPORT_FOLDER, f"capture_{timestamp}.png") # Use constant

            if not screenshot.save(fileName, "PNG", quality=95): # Good quality PNG
                raise Exception(f"Failed to save screenshot to {fileName}.")

            # Basic validation
            if not os.path.exists(fileName) or os.path.getsize(fileName) == 0:
                time.sleep(0.1) # Wait briefly in case of filesystem lag
                if not os.path.exists(fileName) or os.path.getsize(fileName) == 0:
                    raise Exception(f"Screenshot file is empty or non-existent after saving: {fileName}")

            # Deeper validation (optional, but good practice)
            try:
                with Image.open(fileName) as img:
                    img.verify() # Check if Pillow can read metadata
                logger.debug(f"Screenshot verified: {fileName}")
            except Exception as img_err:
                raise Exception(f"Screenshot file validation failed: {img_err}")

            logger.info(f"Screen captured successfully: {fileName}")
            # Store path in capture widget for metadata saving
            self.capture_widget.current_capture_path = fileName

            # Update progress bar and start translation
            self.translation_progress_bar.setFormat("Translating... %p%")
            self.translation_progress_bar.setValue(10)
            self.initiate_translation_from_file(fileName, is_snip=False) # Use helper method

        except Exception as e:
            logger.error(f"Screen grab failed: {e}", exc_info=True)
            self.translation_progress_bar.setFormat("Capture Failed")
            self.translation_progress_bar.setValue(0)
            # Ensure capture widget is shown if hidden during error
            if self.capture_widget and not self.capture_widget.isVisible():
                 self.capture_widget.show()
            QMessageBox.critical(self, "Capture Error", f"Screen capture failed.\n\nError: {e}")

        finally:
            # Clean up screenshot object from memory if it exists
            if screenshot:
                del screenshot


    def captureScreenForLiveTranslation(self):
        # (Keep the existing captureScreenForLiveTranslation method here)
        # Ensure SUPPORT_FOLDER, logger are imported
        # Ensure QApplication is imported
        if not self.is_live_capturing: # Extra check
            return
        if not self.capture_widget or not self.capture_widget.isVisible():
            logger.warning("Live capture skipped: Overlay widget not ready or hidden.")
            return

        screenshot = None
        tempFile = ""
        try:
            overlay_geometry = self.capture_widget.geometry()
            screen = QApplication.primaryScreen()
            if not screen:
                raise Exception("Could not get primary screen for live capture.")

            # Capture without hiding for live view speed
            logger.debug(f"Grabbing screen area for live: {overlay_geometry}")
            screenshot = screen.grabWindow(0, overlay_geometry.x(), overlay_geometry.y(), overlay_geometry.width(), overlay_geometry.height())

            if screenshot.isNull():
                raise Exception("Failed to grab live screenshot (null pixmap).")

            # Use a consistent temporary file name in the support/temp folder
            ensure_support_folder() # Ensure base folder exists
            temp_live_dir = os.path.join(SUPPORT_FOLDER, "temp")
            if not os.path.exists(temp_live_dir): os.makedirs(temp_live_dir)
            tempFile = os.path.join(temp_live_dir, 'live_capture.png')

            # Save efficiently (PNG quality -1 for speed)
            if not screenshot.save(tempFile, "PNG", quality=-1):
                raise Exception("Failed to save live screenshot.")

            if not os.path.exists(tempFile):
                raise Exception("Live screenshot file does not exist after saving.")

            # Start translation worker only if the previous one (if any) has finished
            if self.translation_worker is None or not self.translation_worker.isRunning():
                self.initiate_translation_from_file(tempFile, is_live=True)
            else:
                logger.debug("Skipping live translation start: Previous worker still running.")

        except Exception as e:
            error_text = f"Live Capture Error: {str(e)[:100]}" # Limit length
            logger.error(f"Live capture failed: {e}", exc_info=True)
            # Display error in the live preview area
            if self.live_translation_popout and self.live_translation_popout.isVisible():
                self.live_translation_popout.updateTranslation(error_text)
                # Optionally trigger fade for error? Or keep it static?
            else:
                self.live_translation_label.setText(error_text)
                self.label_opacity_effect.setOpacity(1.0) # Make sure error is visible

        finally:
            if screenshot:
                del screenshot

    def initiate_translation_from_file(self, file_path, is_live=False, is_snip=False):
        """Starts the TranslationWorker for a given file."""
        # ... (checks for running worker, AI, contrast, etc. remain the same) ...
        if self.translation_worker and self.translation_worker.isRunning():
             if not is_live:
                 logger.warning("Previous translation worker running. Stopping it.")
                 self.translation_worker.stop()
                 if not self.translation_worker.wait(1000):
                      logger.error("Previous translation worker did not stop in time!")
             else:
                 logger.debug("Skipping start of new live worker as previous is running.")
                 return
        use_ai = self.translate_with_ai_enabled and not is_live
        contrast = 1.0
        if self.capture_widget: contrast = self.capture_widget.contrast_factor
        logger.info(f"Starting TranslationWorker (Live: {is_live}, AI: {use_ai}, Snip: {is_snip}) for: {os.path.basename(file_path)}")
        if not is_live and self.capture_widget:
            self.capture_widget.current_capture_path = file_path
            logger.debug(f"Set capture_widget.current_capture_path = {file_path}")
        fonts_to_pass = self.capture_widget.fonts if self.capture_widget else {}
        if not fonts_to_pass: logger.error("Fonts not available in capture_widget! Translation rendering may fail.")

        self.translation_worker = TranslationWorker(
            file_name=file_path, source_language=self.source_language, target_language=self.target_language,
            fonts=fonts_to_pass, use_translate_with_ai=use_ai, contrast_factor=contrast, live=is_live, parent=self
        )
        self.translation_worker.translation_complete.connect(self.handleTranslationResult, Qt.QueuedConnection)
        self.translation_worker.error.connect(self.handleTranslationError, Qt.QueuedConnection)
        self.translation_worker.finished.connect(self.onTranslationWorkerFinished, Qt.QueuedConnection)

        # --- MODIFIED UI Update ---
        if not is_live:
             if not self.translation_progress_bar.isVisible():
                 self.translation_progress_bar.setVisible(True)
             progress_format = "Translating Snip... %p%" if is_snip else "Translating... %p%"
             self.translation_progress_bar.setFormat(progress_format)
             self.translation_progress_bar.setValue(15)
        else:
            # --- REMOVED setting text to "Processing..." for internal label ---
            # Check if popout is visible to potentially update internal label state later?
            # For now, just don't update *either* label to "Processing..."
            # if not (self.live_translation_popout and self.live_translation_popout.isVisible()):
            #     processing_text = "Processing..."
            #     self.live_translation_label.setText(processing_text)
            #     self.label_opacity_effect.setOpacity(1.0)
            pass # Do nothing here, wait for results
            # --- END REMOVED ---
        # --- END MODIFIED ---
        self.translation_worker.start()

    def handleTranslationResult(self, result):
        # ... (initial checks for result type, is_live, error_message remain same) ...
        if not isinstance(result, dict):
            logger.error(f"Received invalid result type: {type(result)}")
            self.handleTranslationError("Internal error: Invalid result format.")
            return
        is_live = result.get('live', False)
        error_message = result.get('error_message', '')
        translated_text = result.get('translated_text', '')
        processed_file_name = result.get('file_name', '')
        log_prefix = "[Live]" if is_live else "[Capture/Snip]"
        logger.info(f"{log_prefix} Handling translation result for: {os.path.basename(processed_file_name)}")
        logger.debug(f"Result Data: Error='{error_message}', Text='{translated_text[:50]}...'")
        if error_message:
            logger.warning(f"{log_prefix} Result contains error: {error_message}")
            self.handleTranslationError(f"Processing Error: {error_message}")
            return

        # --- Success ---
        if is_live:
            # --- Update Live Display ---
            compact_text = translated_text.replace('\n', ' ').strip()
            logger.debug(f"Updating live display. Raw text: '{translated_text[:50]}...', Compact: '{compact_text}'")

            # --- MODIFIED: Only update/fade if we have valid text ---
            if compact_text and "Translation Failed" not in compact_text and "Error:" not in compact_text:
                target_label = None
                target_opacity_effect = None
                target_fade_anim = None
                target_widget_instance = None

                if self.live_translation_popout and self.live_translation_popout.isVisible():
                    target_widget_instance = self.live_translation_popout
                else:
                    target_label = self.live_translation_label
                    target_opacity_effect = self.label_opacity_effect
                    target_fade_anim = self.label_fade_anim

                # --- Apply Update and Fade ---
                if target_widget_instance:
                     target_widget_instance.updateTranslation(compact_text)
                     target_widget_instance.trigger_fade_in() # Call popout's fade method
                elif target_label:
                     target_label.setText(compact_text)
                     target_label.setFont(choose_font_for_text(compact_text, font_size=self.font_size))
                     if target_fade_anim and target_opacity_effect:
                          target_fade_anim.stop()
                          target_opacity_effect.setOpacity(0.0)
                          target_fade_anim.start()
                     else:
                          target_label.setGraphicsEffect(None); target_label.setVisible(True)
                          target_opacity_effect.setOpacity(1.0) # Should already be set
            elif not compact_text:
                 logger.debug("Live result was empty or only whitespace, not updating display.")
                 # Optionally update to "..." or clear the label if desired
                 # if self.live_translation_popout and self.live_translation_popout.isVisible():
                 #     self.live_translation_popout.updateTranslation("...")
                 # else:
                 #     self.live_translation_label.setText("...")

            else: # Handle "Translation Failed" or other non-error messages without fade
                 logger.debug(f"Displaying non-error message without fade: '{compact_text}'")
                 if self.live_translation_popout and self.live_translation_popout.isVisible():
                     self.live_translation_popout.updateTranslation(compact_text)
                     self.live_translation_popout.label_opacity_effect.setOpacity(1.0) # Ensure visible
                 else:
                     self.live_translation_label.setText(compact_text)
                     self.label_opacity_effect.setOpacity(1.0) # Ensure visible

            # --- END MODIFIED ---

        else:
            # --- Handle Non-Live Result (Display in Viewer) ---
            # ... (This part remains the same) ...
            logger.info("Processing non-live result for viewer.")
            if self.translation_progress_bar.isVisible():
                 self.translation_progress_bar.setValue(100)
                 self.translation_progress_bar.setFormat("Complete!")
                 QTimer.singleShot(2000, lambda: self.translation_progress_bar.setVisible(False))
            try:
                original_image_path = self.capture_widget.current_capture_path if self.capture_widget else None
                if original_image_path and os.path.exists(original_image_path):
                    base_img_name = os.path.splitext(os.path.basename(original_image_path))[0]
                    txt_filename = f"{base_img_name}.txt"
                    txt_filepath = os.path.join(SUPPORT_FOLDER, txt_filename)
                    timestamp_dt = result.get('timestamp', datetime.datetime.now())
                    timestamp_str = timestamp_dt.strftime("%Y-%m-%d %H:%M:%S")
                    original_text = result.get('original_text', 'N/A')
                    translated_text_final = result.get('translated_text', 'N/A')
                    metadata_content = (f"Timestamp: {timestamp_str}\n...") # Keep metadata
                    with open(txt_filepath, 'w', encoding='utf-8') as f: f.write(metadata_content)
                    logger.info(f"Saved capture metadata to: {txt_filepath}")
                else: logger.warning(f"Could not save metadata: Original image path invalid or missing ('{original_image_path}')")
            except Exception as meta_err: logger.error(f"Failed to save metadata text file: {meta_err}", exc_info=True)
            if self.capture_widget:
                 viewer_file_path = self.capture_widget.current_capture_path
                 logger.debug(f"Calling displayTranslatedImage with path: {viewer_file_path}")
                 if not viewer_file_path or not os.path.exists(viewer_file_path):
                      logger.error(f"Viewer Error: Processed file path '{viewer_file_path}' is invalid.")
                      QMessageBox.critical(self, "Viewer Error", "Cannot display result: Invalid image path.")
                 else:
                      self.capture_widget.displayTranslatedImage(result, viewer_file_path, self.target_language)
            else:
                 logger.error("Cannot display translated image: CaptureWidget is None.")
                 QMessageBox.critical(self, "Error", "Cannot display result, capture overlay not available.")


    def handleTranslationError(self, error_message):
        # (handleTranslationError remains the same - display error appropriately)
        logger.error(f"Translation Worker Error received: {error_message}")
        self.translation_error_occurred.emit(error_message)


    def displayTranslationError(self, error_message):
        # (displayTranslationError remains the same - ensure popout shows errors)
        is_currently_live = self.is_live_capturing
        error_text = f"Error: {error_message[:100]}" # Limit length

        if is_currently_live:
             if self.live_translation_popout and self.live_translation_popout.isVisible():
                 self.live_translation_popout.updateTranslation(error_text)
                 self.live_translation_popout.label_opacity_effect.setOpacity(1.0) # Ensure visible
             else:
                 self.live_translation_label.setText(error_text)
                 self.label_opacity_effect.setOpacity(1.0) # Ensure visible
        else:
             if self.translation_progress_bar.isVisible():
                 self.translation_progress_bar.setFormat("Error")
                 self.translation_progress_bar.setValue(0)
                 QTimer.singleShot(3000, lambda: self.translation_progress_bar.setVisible(False))
             QMessageBox.warning(self, "Translation Error", f"An error occurred:\n\n{error_message}")


    def handleTranslationError(self, error_message):
        # (Keep the existing handleTranslationError method here)
        logger.error(f"Translation Worker Error received: {error_message}")
        # Emit the signal to handle the display in displayTranslationError
        self.translation_error_occurred.emit(error_message)


    def displayTranslationError(self, error_message):
        # (Keep the existing displayTranslationError method here)
        is_currently_live = self.is_live_capturing

        if is_currently_live:
             # Display error in the live preview area
             error_text = f"Error: {error_message[:100]}" # Limit length
             if self.live_translation_popout and self.live_translation_popout.isVisible():
                 self.live_translation_popout.updateTranslation(error_text)
                 self.live_translation_popout.label_opacity_effect.setOpacity(1.0) # Ensure visible
             else:
                 self.live_translation_label.setText(error_text)
                 self.label_opacity_effect.setOpacity(1.0) # Ensure visible
        else:
             # Display error in progress bar and message box for non-live
             if self.translation_progress_bar.isVisible():
                 self.translation_progress_bar.setFormat("Error")
                 self.translation_progress_bar.setValue(0) # Reset progress
                 # Hide progress bar after a delay
                 QTimer.singleShot(3000, lambda: self.translation_progress_bar.setVisible(False))
             # Show message box
             QMessageBox.warning(self, "Translation Error", f"An error occurred:\n\n{error_message}")


    def onTranslationWorkerFinished(self):
        # (Keep the existing onTranslationWorkerFinished method here)
        logger.debug("TranslationWorker thread finished.")
        # Clean up progress bar if it was for a non-live task and wasn't marked complete/error handled it
        if not self.is_live_capturing and self.translation_progress_bar.isVisible():
             # Check conditions under which it should be hidden now
             is_complete = self.translation_progress_bar.value() == 100
             is_error = "Error" in self.translation_progress_bar.format() or "Failed" in self.translation_progress_bar.format()
             if not is_complete and not is_error:
                 # If worker finished but progress wasn't 100 or error, hide it after delay
                 logger.debug("Hiding progress bar as worker finished unexpectedly.")
                 QTimer.singleShot(2000, lambda: self.translation_progress_bar.setVisible(False))
             # If it was complete/error, handleTranslationResult/Error already scheduled its hiding

        # Clear the worker reference
        self.translation_worker = None


    def initTrayIcon(self):
        # (Keep the existing initTrayIcon method here)
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.png")
        if not os.path.exists(icon_path):
             logger.error(f"Tray icon not found at {icon_path}. Tray functionality disabled.")
             return

        self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self)
        self.tray_icon.setToolTip("Overlay Translate")

        tray_menu = QMenu(self) # Parent menu to self

        restore_action = QAction("Show Controls", self) # Use QAction
        restore_action.triggered.connect(self.restoreFromTray)
        tray_menu.addAction(restore_action)

        capture_action = QAction("Capture (F1)", self) # Use QAction
        capture_action.triggered.connect(self.captureScreen)
        tray_menu.addAction(capture_action)

        snip_action = QAction("Snip (F4)", self) # Use QAction
        snip_action.triggered.connect(self.activateSnippingTool)
        tray_menu.addAction(snip_action)

        tray_menu.addSeparator()

        exit_action = QAction("Exit", self) # Use QAction
        exit_action.triggered.connect(self.closeApplication)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.trayIconActivated)
        self.tray_icon.show()
        logger.info("System tray icon initialized.")

    def trayIconActivated(self, reason):
        # (Keep the existing trayIconActivated method here)
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
             self.restoreFromTray()

    def minimizeToTray(self):
        # --- Save window visibility state BEFORE hiding ---
        self.chat_window_was_visible = bool(self.chat_window and self.chat_window.isVisible())
        self.live_translation_popout_was_visible = bool(self.live_translation_popout and self.live_translation_popout.isVisible())
        logger.debug(f"Minimizing: ChatVisible={self.chat_window_was_visible}, LivePopoutVisible={self.live_translation_popout_was_visible}")
        # --- End Save State ---

        self.hide()
        if self.capture_widget:
            self.capture_widget.hide()
        # Also hide chat and live popout if they are open
        if self.chat_window and self.chat_window.isVisible():
            self.chat_window.hide()
        if self.live_translation_popout and self.live_translation_popout.isVisible():
            self.live_translation_popout.hide()

        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                "Overlay Translate",
                "Minimized to tray. Click icon to restore.",
                QSystemTrayIcon.MessageIcon.Information,
                3000 # milliseconds
            )
        logger.info("Application minimized to tray.")

    def restoreFromTray(self):
        # --- Restore based on saved visibility state ---
        logger.debug(f"Restoring: ChatShouldBeVisible={self.chat_window_was_visible}, LivePopoutShouldBeVisible={self.live_translation_popout_was_visible}")
        self.show()
        # Restore capture widget
        if self.capture_widget:
             self.capture_widget.show()
        # Restore other windows ONLY if they existed AND were visible before minimize
        if self.chat_window and self.chat_window_was_visible: # Check if instance exists and was visible
            self.chat_window.show()
        if self.live_translation_popout and self.live_translation_popout_was_visible: # Check if instance exists and was visible
            self.live_translation_popout.show()
        # --- End Restore based on state ---

        self.raise_() # Bring window to front
        self.activateWindow()
        logger.info("Application restored from tray.")

    # ADDED Method to update viewer settings
    def update_last_viewer_settings(self, settings_dict):
        """Stores the settings from the last closed viewer."""
        if isinstance(settings_dict, dict):
            self.last_viewer_settings = settings_dict
            logger.debug(f"Updated last_viewer_settings: {self.last_viewer_settings}")
        else:
            logger.warning("Attempted to update viewer settings with invalid data type.")


    def gather_current_state(self):
        """Gathers state from all components into a dictionary."""
        state = {}
        # Control window geometry
        state['ControlWindow'] = { 'x': self.x(), 'y': self.y(), 'width': self.width(), 'height': self.height() }
        # Capture widget state
        if self.capture_widget:
             state['CaptureWidget'] = self.capture_widget.get_state()
        # Live translation popout geometry
        if self.live_translation_popout:
             state['LiveTranslationWindow'] = self.live_translation_popout.save_geometry()
        # Chat window geometry
        if self.chat_window:
             state['ChatWindow'] = self.chat_window.save_geometry()

        # --- ADDED: Include last viewer settings ---
        state['viewer_settings'] = self.last_viewer_settings
        # --- End ADDED ---

        # Font settings
        state['font_settings'] = { 'size': self.default_font_size, 'type': self.default_font_type }
        # App settings
        state['settings'] = { 'translate_with_ai': self.translate_with_ai_enabled }
        # AI API config is handled directly by save_settings using global state
        # Theme is handled directly by save_settings using global state

        return state


    def closeApplication(self):
        logger.info("Close application requested.")

        # Stop ongoing processes FIRST
        if self.is_live_capturing:
            self.live_capture_timer.stop()
            logger.debug("Stopped live capture timer.")
        if self.translation_worker and self.translation_worker.isRunning():
            logger.debug("Stopping active translation worker...")
            self.translation_worker.stop()
            if not self.translation_worker.wait(1500):
                 logger.warning("Translation worker did not stop gracefully.")

        # Stop resource monitor timer
        if self.resource_monitor_widget:
            self.resource_monitor_widget.stop_updates()

        # Close child windows
        if self.chat_window and self.chat_window.isVisible():
            logger.debug("Closing chat window...")
            self.chat_window.close() # Triggers viewer closeEvent if open via chat
        if self.live_translation_popout and self.live_translation_popout.isVisible():
            logger.debug("Closing live translation popout...")
            self.live_translation_popout.close()

        # --- FIX: Gather state BEFORE closing widgets ---
        final_state = self.gather_current_state() # This now includes viewer settings
        # --- End FIX ---

        # Cleanup and close CaptureWidget (calls its shutdown_flask_server)
        if self.capture_widget:
            logger.debug("Cleaning up and closing capture widget...")
            self.capture_widget.cleanup()
            self.capture_widget.close()

        # Hide tray icon
        if self.tray_icon:
            self.tray_icon.hide()
            logger.debug("Hid tray icon.")

        # --- Centralized Save on Exit ---
        logger.info("Saving final application state...")
        try:
            # --- FIX: Pass the gathered state directly to save_settings ---
            save_settings(final_state) # Save the collected final_state
            # --- End FIX ---
        except Exception as save_err:
            logger.error(f"Error during final save operation: {save_err}", exc_info=True)


        # --- Shutdown logging BEFORE attempting folder manipulation ---
        logger.info("Shutting down logging handlers...")
        print("Shutting down logging...") # Use print as logger is closing
        # Get the specific logger instance used throughout the app
        logger_instance = logging.getLogger("OverlayTranslate") # Use the name defined in config
        handlers = logger_instance.handlers[:] # Iterate over a copy
        for handler in handlers:
            try:
                handler.close()
                logger_instance.removeHandler(handler)
                print(f"Closed and removed handler: {handler}")
            except Exception as log_close_err:
                # Use print because logger might be partially closed
                print(f"Error closing/removing log handler {handler}: {log_close_err}")
        # Alternatively, just call logging.shutdown() which attempts to close all handlers
        # logging.shutdown() # This might be sufficient, but manual closing is more explicit

        # --- Support Folder Cleanup (Now logging should be closed) ---
        # ... (cleanup logic remains the same) ...
        if os.path.exists(SUPPORT_FOLDER):
            print(f"Prompting user for Support folder cleanup options for: {SUPPORT_FOLDER}") # Use print

            msgBox = QMessageBox(self)
            # Prevent the main window from being interactive while this dialog is up
            msgBox.setWindowModality(Qt.WindowModal)
            msgBox.setWindowTitle("Clean Up Support Folder?")
            msg_text = (f"The Support folder contains logs, captures, and metadata:\n\n"
                        f"<i>{SUPPORT_FOLDER}</i>\n\n"
                        f"<b>Warning:</b> Deleting cannot be undone.\n"
                        f"What would you like to do?")
            msgBox.setTextFormat(Qt.RichText) # Allow simple HTML like italic/bold
            msgBox.setText(msg_text)
            msgBox.setIcon(QMessageBox.Icon.Question)

            zipDeleteButton = msgBox.addButton("Zip & Delete", QMessageBox.ButtonRole.ActionRole)
            deleteButton = msgBox.addButton("Delete Folder", QMessageBox.ButtonRole.DestructiveRole)
            keepButton = msgBox.addButton("Just Close", QMessageBox.ButtonRole.AcceptRole)

            msgBox.setDefaultButton(keepButton)
            msgBox.exec()
            clickedBtn = msgBox.clickedButton()

            # --- Zip / Delete / Keep logic ---
            if clickedBtn == zipDeleteButton:
                print("User chose to Zip and Delete the Support folder.")
                zip_success = False; zip_filename = ""
                try:
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    # Save zip to Desktop, not inside the folder being zipped!
                    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
                    zip_filename = os.path.join(desktop_path, f"OverlayTranslate_Support_{timestamp}.zip")
                    print(f"Creating zip archive: {zip_filename}")
                    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(SUPPORT_FOLDER):
                             # Arcname is the path inside the zip file, relative to SUPPORT_FOLDER
                            relative_root = os.path.relpath(root, SUPPORT_FOLDER)
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.join(relative_root, file)
                                # Basic check to avoid zipping the zip file itself if saved in source (shouldn't happen now)
                                if os.path.abspath(file_path) != os.path.abspath(zip_filename):
                                    zipf.write(file_path, arcname)
                                else:
                                     print(f"Skipping zip file itself: {file_path}")

                    zip_success = True
                    print(f"Successfully created zip archive: {zip_filename}")
                    QMessageBox.information(self, "Zip Created", f"Support folder archived to:\n{zip_filename}") # Show this before deletion attempt
                except Exception as e:
                    print(f"ERROR: Failed to create zip archive of {SUPPORT_FOLDER}: {e}")
                    QMessageBox.critical(self, "Zip Error", f"Could not create zip archive.\nError: {e}\n\nThe Support folder will NOT be deleted.")

                if zip_success:
                    print(f"Attempting to delete original Support folder: {SUPPORT_FOLDER}")
                    try:
                        shutil.rmtree(SUPPORT_FOLDER) # No ignore_errors=False needed, let it raise error if fails
                        print(f"Support folder deleted successfully after zipping.")
                        # No need for another message box here, previous one confirmed zip creation
                    except Exception as e:
                        print(f"ERROR: Failed to delete Support folder {SUPPORT_FOLDER} after zipping: {e}")
                        QMessageBox.warning(self, "Cleanup Error", f"Could not delete the original Support folder after zipping:\n{e}")

            elif clickedBtn == deleteButton:
                print(f"User chose to Delete the Support folder: {SUPPORT_FOLDER}")
                try:
                    shutil.rmtree(SUPPORT_FOLDER)
                    print(f"Support folder deleted successfully.")
                    QMessageBox.information(self, "Folder Deleted", "Support folder has been deleted.")
                except Exception as e:
                    print(f"ERROR: Failed to delete Support folder {SUPPORT_FOLDER}: {e}")
                    # Show error message to user
                    QMessageBox.warning(self, "Cleanup Error", f"Could not delete the Support folder:\nError: {e}\n\nIt might be in use by another application, or file permissions are preventing deletion.")

            elif clickedBtn == keepButton:
                print("User chose to keep the Support folder.")

            else: # Handles closing the dialog via 'X' button or Esc
                 print("Support folder cleanup dialog closed or cancelled. Folder kept.")

        else:
            print("Support folder does not exist, skipping cleanup prompt.") # Use print


        print("Exiting application.") # Use print
        QApplication.quit() # Proper way to exit Qt application


    def closeEvent(self, event):
        # (Keep the existing closeEvent method - minimize to tray)
        # Minimize to tray instead of closing by default
        event.ignore() # Prevent the window from closing
        self.minimizeToTray()

    def activateSnippingTool(self):
        # (Keep the existing activateSnippingTool method here)
        if not self.snipping_tool:
             logger.error("Snipping tool not initialized.")
             return
        # Hide capture widget before showing snipping tool
        if self.capture_widget and self.capture_widget.isVisible():
            self.capture_widget.hide()
        self.snipping_tool.show() # Show the fullscreen snipping overlay
        logger.debug("Activated snipping tool.")

    def openChatWindow(self):
        # (Keep the existing openChatWindow method here)
        # Ensure ChatWindow is imported from .dialogs
        # Ensure ai_api_config is imported from utils.config
        # Ensure load_settings is imported from utils.helpers
        logger.debug("Request to open ChatWindow")
        if not ai_api_config.get("provider"):
            QMessageBox.warning(self, "AI Not Configured", "AI Chat requires an AI provider to be configured in Settings > AI Configuration.")
            return

        if self.chat_window is None: # Create only if it doesn't exist
            try:
                self.chat_window = ChatWindow(parent=self)
                # Geometry loading happens inside ChatWindow's init
                logger.debug("ChatWindow created.")
            except Exception as e:
                logger.error(f"Failed to create ChatWindow: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Could not open AI Chat window:\n{e}")
                self.chat_window = None # Reset if creation failed
                return

        # Show the chat window (whether newly created or existing)
        if self.chat_window:
             self.chat_window.show()
             self.chat_window.raise_()
             self.chat_window.activateWindow()
             logger.debug("ChatWindow shown/activated.")


    def increaseFontSize(self):
        # (Keep the existing increaseFontSize method here)
        self.font_size = min(self.font_size + 2, 36) # Increase font size for preview label
        # Update the stylesheet for the specific label
        # Note: This inline style might override theme if not specific enough in theme
        self.live_translation_label.setStyleSheet(f"QLabel#ControlWindowLiveLabel {{ font-size: {self.font_size}px; /* Keep other styles */ }}")
        # Re-applying the entire theme might be safer if styles are complex
        # apply_theme() # Re-apply globally if needed
        logger.debug(f"Live preview font size increased to {self.font_size}px")

    def decreaseFontSize(self):
        # (Keep the existing decreaseFontSize method here)
        self.font_size = max(self.font_size - 2, 10) # Decrease font size for preview label
        self.live_translation_label.setStyleSheet(f"QLabel#ControlWindowLiveLabel {{ font-size: {self.font_size}px; /* Keep other styles */ }}")
        logger.debug(f"Live preview font size decreased to {self.font_size}px")

    def popOutLiveTranslation(self):
        # (Keep the existing popOutLiveTranslation method here)
        # Ensure LiveTranslationWindow is imported from .dialogs
        if self.live_translation_popout is None: # Create if it doesn't exist
             logger.debug("Popping out live translation.")
             self.live_translation_popout = LiveTranslationWindow(self) # Parent to control window
             current_text = self.live_translation_label.text()
             # Set initial text in popout
             if current_text in ["Live translation disabled.", "Live capture active...", "Processing...", "Live view popped out."]:
                 self.live_translation_popout.updateTranslation("Waiting for live data...")
             else:
                 # Transfer current actual translation if available
                 self.live_translation_popout.updateTranslation(current_text)
             self.live_translation_popout.show()
             self.live_translation_label.setText("Live view popped out.") # Update internal label
             self.label_opacity_effect.setOpacity(1.0) # Make sure text is visible

        elif not self.live_translation_popout.isVisible(): # If exists but hidden, just show it
             logger.debug("Showing existing popped out live translation.")
             self.live_translation_popout.show()
             self.live_translation_label.setText("Live view popped out.") # Update internal label
             self.label_opacity_effect.setOpacity(1.0)

        else: # If exists and visible, close it
            logger.debug("Closing live translation popout.")
            # Closing the popout handles its state saving via its closeEvent
            self.live_translation_popout.close()
            self.live_translation_popout = None # Clear reference
            # Restore text on internal label based on live state
            if self.is_live_capturing:
                 self.live_translation_label.setText("Live capture active...")
            else:
                 self.live_translation_label.setText("Live translation disabled.")
            self.label_opacity_effect.setOpacity(1.0) # Make sure text is visible


    def configureAIAPI(self):
        # (Keep the existing configureAIAPI method here)
        # Ensure QDialog, QVBoxLayout, etc. are imported
        # Ensure ai_api_config, logger are imported from utils.config
        # Ensure keyring is imported
        dialog = QDialog(self)
        dialog.setWindowTitle("Configure AI API Provider")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        api_group = QGroupBox("Select AI Provider & Settings")
        api_layout = QVBoxLayout()
        api_layout.setSpacing(10)

        # Radio buttons for single selection
        self.api_radio_group = QtWidgets.QButtonGroup(dialog)

        self.no_api_radio = QtWidgets.QRadioButton("None (Disable AI Features)")
        self.no_api_radio.setChecked(ai_api_config["provider"] is None)
        self.api_radio_group.addButton(self.no_api_radio, 0)
        api_layout.addWidget(self.no_api_radio)
        api_layout.addWidget(QLabel("------------------------------------")) # Separator

        # OpenAI Option
        self.openai_radio = QtWidgets.QRadioButton("OpenAI (api.openai.com)")
        self.openai_radio.setChecked(ai_api_config["provider"] == "OpenAI")
        self.api_radio_group.addButton(self.openai_radio, 1)
        openai_key_layout = QHBoxLayout()
        openai_key_layout.addWidget(QLabel("API Key:"))
        self.openai_key_input = QLineEdit()
        self.openai_key_input.setEchoMode(QLineEdit.Password)
        self.openai_key_input.setPlaceholderText("Required")
        if ai_api_config["provider"] == "OpenAI": # Only show stored key if OpenAI is selected
            try:
                 key = keyring.get_password("OverlayTranslate", "OpenAI")
                 if key: self.openai_key_input.setText(key)
            except Exception as e: logger.warning(f"Could not get OpenAI key from keyring: {e}")
        openai_key_layout.addWidget(self.openai_key_input)
        api_layout.addWidget(self.openai_radio)
        api_layout.addLayout(openai_key_layout)
        api_layout.addWidget(QLabel("------------------------------------"))

        # Ollama Option
        self.ollama_radio = QtWidgets.QRadioButton("Ollama (Local)")
        self.ollama_radio.setChecked(ai_api_config["provider"] == "Ollama")
        self.api_radio_group.addButton(self.ollama_radio, 2)
        ollama_endpoint_layout = QHBoxLayout()
        ollama_endpoint_layout.addWidget(QLabel("Endpoint:"))
        default_ollama_endpoint = "http://localhost:11434/api/chat"
        current_ollama_endpoint = ai_api_config.get("endpoint", default_ollama_endpoint) if ai_api_config.get("provider") == "Ollama" else default_ollama_endpoint
        self.ollama_endpoint_input = QLineEdit(current_ollama_endpoint)
        self.ollama_endpoint_input.setPlaceholderText(default_ollama_endpoint)
        ollama_endpoint_layout.addWidget(self.ollama_endpoint_input)
        api_layout.addWidget(self.ollama_radio)
        api_layout.addLayout(ollama_endpoint_layout)
        api_layout.addWidget(QLabel("------------------------------------"))

        # LM Studio Option
        self.lmstudio_radio = QtWidgets.QRadioButton("LM Studio (Local)")
        self.lmstudio_radio.setChecked(ai_api_config["provider"] == "LM Studio")
        self.api_radio_group.addButton(self.lmstudio_radio, 3)
        lmstudio_key_layout = QHBoxLayout()
        lmstudio_key_layout.addWidget(QLabel("API Key (Optional):"))
        self.lmstudio_key_input = QLineEdit()
        self.lmstudio_key_input.setEchoMode(QLineEdit.Password)
        self.lmstudio_key_input.setPlaceholderText("Usually not needed")
        if ai_api_config["provider"] == "LM Studio": # Only show stored key if LM Studio is selected
            try:
                 key = keyring.get_password("OverlayTranslate", "LM Studio")
                 if key: self.lmstudio_key_input.setText(key)
            except Exception as e: logger.warning(f"Could not get LM Studio key from keyring: {e}")
        lmstudio_key_layout.addWidget(self.lmstudio_key_input)
        api_layout.addWidget(self.lmstudio_radio)
        api_layout.addLayout(lmstudio_key_layout)

        # Enable/disable inputs based on radio selection
        def update_inputs():
            self.openai_key_input.setEnabled(self.openai_radio.isChecked())
            self.ollama_endpoint_input.setEnabled(self.ollama_radio.isChecked())
            self.lmstudio_key_input.setEnabled(self.lmstudio_radio.isChecked())
        self.api_radio_group.buttonClicked.connect(update_inputs)
        update_inputs() # Set initial state

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # Standard Dialog Buttons
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(lambda: self.save_api_settings(dialog)) # Connect OK to save
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)
        dialog.exec()

    def save_api_settings(self, dialog):
        # (Keep the existing save_api_settings method here)
        # Ensure ai_api_config is imported from utils.config
        # Ensure keyring is imported
        # Ensure QMessageBox is imported
        selected_id = self.api_radio_group.checkedId()
        provider_name = "None"
        new_provider = None
        new_endpoint = None
        new_key = None
        provider_key_name = None # Key name for keyring
        success = False
        error_msg = ""

        try:
            if selected_id == 0: # None
                new_provider = None
                new_endpoint = None
                provider_name = "None"
                success = True
            elif selected_id == 1: # OpenAI
                api_key = self.openai_key_input.text().strip()
                if not api_key: raise ValueError("OpenAI requires an API Key.")
                new_provider = "OpenAI"
                new_endpoint = "https://api.openai.com/v1/chat/completions"
                new_key = api_key
                provider_key_name = "OpenAI"
                provider_name = "OpenAI"
                success = True
            elif selected_id == 2: # Ollama
                endpoint = self.ollama_endpoint_input.text().strip()
                if not endpoint: raise ValueError("Ollama requires an Endpoint URL.")
                if not (endpoint.startswith("http://") or endpoint.startswith("https://")) or not ('/api/chat' in endpoint or '/api/generate' in endpoint):
                     raise ValueError("Invalid Ollama endpoint format. Use http://host:port/api/chat or /api/generate")
                new_provider = "Ollama"
                new_endpoint = endpoint
                provider_key_name = "Ollama" # Though key isn't used, clear old one
                provider_name = "Ollama"
                success = True
            elif selected_id == 3: # LM Studio
                api_key = self.lmstudio_key_input.text().strip()
                new_provider = "LM Studio"
                new_endpoint = "http://localhost:1234/v1/chat/completions" # Default LM Studio endpoint
                new_key = api_key # Can be empty
                provider_key_name = "LM Studio"
                provider_name = "LM Studio"
                success = True
            else:
                raise ValueError("No provider selected.")

            # If successful, update global config and keyring
            if success:
                # Clear old keys first
                for prov in ["OpenAI", "Ollama", "LM Studio"]:
                    if prov != provider_key_name: # Don't clear the one we might be setting
                        try: keyring.delete_password("OverlayTranslate", prov)
                        except Exception: pass # Ignore errors if key doesn't exist

                # Set new key if provided
                if new_key and provider_key_name:
                     keyring.set_password("OverlayTranslate", provider_key_name, new_key)
                     ai_api_config["key_stored"] = True
                elif provider_key_name: # Clear key if provider selected but no key given (e.g. LM Studio optional)
                     try: keyring.delete_password("OverlayTranslate", provider_key_name)
                     except Exception: pass
                     ai_api_config["key_stored"] = False
                else: # No provider selected
                    ai_api_config["key_stored"] = False


                # Update global config dictionary
                ai_api_config["provider"] = new_provider
                ai_api_config["endpoint"] = new_endpoint

                logger.info(f"AI API configuration updated: Provider={provider_name}, Endpoint={new_endpoint}, KeyStored={ai_api_config['key_stored']}")

        except ValueError as ve:
             error_msg = str(ve)
             QMessageBox.warning(dialog, "Configuration Error", error_msg)
             success = False # Explicitly mark as failed
        except Exception as e:
             error_msg = f"An unexpected error occurred: {e}"
             logger.error(f"Error saving API settings: {e}", exc_info=True)
             QMessageBox.critical(dialog, "Error", error_msg)
             success = False # Explicitly mark as failed

        if success:
            # Saving to file is handled by ControlWindow on exit
            QMessageBox.information(dialog, "Configuration Saved", f"AI Provider set to: {provider_name}\nSettings will be fully saved on application exit.")
            # Disable the AI toggle button if "None" was selected
            if ai_api_config["provider"] is None and self.translate_with_ai_enabled:
                self.translate_with_ai_toggle.setChecked(False)
            dialog.accept() # Close the dialog

    # Removed saveAPISettingsToFile - saving is centralized

    def setDefaultFontSize(self):
        # (Keep the existing setDefaultFontSize method here)
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Set Default Font Size")
        dialog.setLabelText("Enter default font size for text in viewer (e.g., 10-72):")
        dialog.setInputMode(QInputDialog.InputMode.IntInput)
        dialog.setIntValue(self.default_font_size)
        dialog.setIntMinimum(8)
        dialog.setIntMaximum(72)
        ok = dialog.exec()
        if ok:
            size = dialog.intValue()
            self.default_font_size = size
            if self.capture_widget:
                self.capture_widget.default_font_size = size # Update capture widget too
            logger.info(f"Default translation font size set to: {size}")
            # Saving handled on exit
        else:
            logger.debug("Font size selection cancelled.")

    def setDefaultFontType(self):
        # (Keep the existing setDefaultFontType method here)
        # Ensure get_system_font_path is imported
        font_options = {
            "Roboto (Default Latin)": "default",
            "Arial (Fallback)": "Arial",
            "Microsoft YaHei (Chinese)": "zh", # Use 'zh' for consistency
            "MS Gothic (Japanese)": "ja",
            "Malgun Gothic (Korean)": "ko"
        }
        # Add more based on what get_system_font_path supports and finds
        # e.g., check if "Segoe UI" exists on Windows

        current_key = next((key for key, value in font_options.items() if value == self.default_font_type), "Roboto (Default Latin)")

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Set Default Font Category")
        dialog.setLabelText("Choose default font category for translated text viewer:")
        dialog.setComboBoxItems(list(font_options.keys()))
        dialog.setTextValue(current_key)
        ok = dialog.exec()
        if ok:
            font_display_name = dialog.textValue()
            if font_display_name in font_options:
                self.default_font_type = font_options[font_display_name]
                if self.capture_widget:
                    self.capture_widget.default_font_type = self.default_font_type # Update capture widget
                logger.info(f"Default translation font type set to: {self.default_font_type} ({font_display_name})")
                # Saving handled on exit
            else:
                 logger.warning(f"Invalid font type selected: {font_display_name}")
        else:
             logger.debug("Font type selection cancelled.")

    # Removed saveFontSettings - saving is centralized

    def adjustCaptureWidgetOpacity(self, value):
        # (Keep the existing adjustCaptureWidgetOpacity method here)
        # Ensure MIN_OPACITY is imported from utils.config
        if self.capture_widget:
            # Calculate opacity, ensuring it doesn't go below MIN_OPACITY
            min_slider_val = max(1, int(MIN_OPACITY * 100))
            if value < min_slider_val:
                 value = min_slider_val # Clamp value at the slider's minimum
            opacity = value / 100.0

            self.capture_widget.setWindowOpacity(opacity)
            self.capture_widget.updateClickThroughState() # Update click-through based on new opacity
            logger.debug(f"Capture widget opacity set to {opacity:.2f}")
            # Saving handled on exit

    def selectSourceLanguage(self):
        # (Keep the existing selectSourceLanguage method here)
        # Ensure initialize_paddle_ocr is imported from utils.ocr_utils
        # Ensure QMessageBox, QInputDialog, QApplication are imported
        languages = {
             "Auto Detect": "auto", "English": "en", "Spanish": "es", "French": "fr",
             "German": "de", "Italian": "it", "Portuguese": "pt", "Russian": "ru",
             "Chinese": "ch", # Paddle uses 'ch' for general Chinese
             "Japanese": "ja", "Korean": "ko"
             # Add more languages supported by PaddleOCR if needed
         }
        current_name = next((name for name, code in languages.items() if code == self.source_language), "Auto Detect")

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Select Source Language")
        dialog.setLabelText("Choose source language for OCR and Translation:")
        dialog.setComboBoxItems(list(languages.keys()))
        dialog.setTextValue(current_name)
        ok = dialog.exec()

        if ok:
            selected_name = dialog.textValue()
            if selected_name in languages:
                new_lang_code = languages[selected_name]
                if self.source_language != new_lang_code:
                    self.source_language = new_lang_code
                    logger.info(f"Source language setting changed to: {self.source_language} ({selected_name})")

                    # Re-initialize OCR engine in a separate thread to avoid blocking GUI
                    # Determine the language to initialize OCR with ('en' if auto)
                    ocr_init_lang = 'en' if self.source_language == 'auto' else self.source_language

                    # Show a non-blocking message
                    QMessageBox.information(self, "Updating OCR", f"Updating OCR engine for '{selected_name}' in the background...")
                    QApplication.processEvents() # Process events to show the message

                    # Use QTimer to run initialization after returning to event loop
                    QTimer.singleShot(100, lambda: self.reinitialize_ocr_async(ocr_init_lang, selected_name))

            else:
                 logger.warning(f"Invalid source language selected: {selected_name}")
        else:
             logger.debug("Source language selection cancelled.")

    def reinitialize_ocr_async(self, lang_code, lang_name):
        """Helper to run OCR initialization and show completion message."""
        logger.info(f"Starting asynchronous OCR re-initialization for {lang_code}...")
        success = initialize_paddle_ocr(lang_code) # This blocks but runs after GUI is responsive
        if success:
            logger.info(f"OCR engine updated successfully for {lang_name}.")
            # Use invokeMethod for thread safety if calling from a different thread (though Timer runs in main thread)
            QtCore.QMetaObject.invokeMethod(self, "_show_ocr_update_complete_message", Qt.QueuedConnection)
            # QMessageBox.information(self, "Update Complete", f"OCR engine updated for {lang_name}.")
        else:
            logger.error(f"OCR engine update failed for {lang_name}.")
            # Error message shown by initialize_paddle_ocr

    @QtCore.Slot()
    def _show_ocr_update_complete_message(self):
        """Slot to show the completion message box safely."""
        QMessageBox.information(self, "Update Complete", "OCR engine update finished.")


    def selectTargetLanguage(self):
        # (Keep the existing selectTargetLanguage method here)
        # Ensure QInputDialog is imported
        languages = {
            "English": "en", "Spanish": "es", "French": "fr", "German": "de",
            "Italian": "it", "Portuguese": "pt", "Russian": "ru",
            "Chinese (Simplified)": "zh", # Target for translation service (may differ from OCR)
            "Japanese": "ja", "Korean": "ko"
            # Add languages supported by your translation backend (Flask app)
        }
        current_name = next((name for name, code in languages.items() if code == self.target_language), "English")

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Select Target Language")
        dialog.setLabelText("Choose target language for Translation:")
        dialog.setComboBoxItems(list(languages.keys()))
        dialog.setTextValue(current_name)
        ok = dialog.exec()

        if ok:
            selected_name = dialog.textValue()
            if selected_name in languages:
                self.target_language = languages[selected_name]
                logger.info(f"Target language set to: {self.target_language} ({selected_name})")
                # Update capture widget state if needed (it reads from control_window usually)
                if self.capture_widget:
                    self.capture_widget.target_language = self.target_language
                # Saving handled on exit
            else:
                 logger.warning(f"Invalid target language selected: {selected_name}")
        else:
             logger.debug("Target language selection cancelled.")

    def openServer(self):
        # (Keep the existing openServer method here)
        # Ensure webbrowser, logger, QMessageBox are imported
        url = "http://127.0.0.1:5000" # Default Flask server address
        logger.info(f"Opening web browser to: {url}")
        try:
            webbrowser.open(url)
        except Exception as e:
            logger.error(f"Failed to open web browser: {e}")
            QMessageBox.warning(self, "Error", f"Could not open web browser.\nPlease manually navigate to {url}")

    def setupGlobalShortcuts(self):
        # (Keep the existing setupGlobalShortcuts method here)
        # Ensure QShortcut, QKeySequence are imported
        try:
            # F1: Capture
            QShortcut(QKeySequence("F1"), self).activated.connect(self.captureScreen)
            # F2: Toggle Click-Through
            if self.capture_widget:
                 QShortcut(QKeySequence("F2"), self).activated.connect(self.toggleCaptureWidgetClickThrough)
            else:
                 logger.error("Cannot register F2 shortcut: CaptureWidget not initialized.")
            # F3: Toggle Live Capture
            QShortcut(QKeySequence("F3"), self).activated.connect(self.toggleLiveCapture)
            # F4: Activate Snipping Tool
            QShortcut(QKeySequence("F4"), self).activated.connect(self.activateSnippingTool)

            logger.info("Global shortcuts (F1, F2, F3, F4) registered.")
        except Exception as e:
            logger.error(f"Failed to register global shortcuts: {e}", exc_info=True)
            QMessageBox.warning(self, "Shortcut Error", f"Could not register global hotkeys (F1-F4).\nThey may be in use by another application.\n\nError: {e}")

    def showAboutDialog(self):
        # (Keep the existing showAboutDialog method here)
        # Ensure QMessageBox is imported
         about_text = """
         <b>Overlay Translate</b> - Version 1.3.1 (Modular)
         <p>Seamless screen capture and translation.</p>
         <p>Features:</p>
         <ul>
             <li>Screen Region Capture & Snip Tool</li>
             <li>Live Translation Mode</li>
             <li>Offline Translation (via local server)</li>
             <li>AI Translation (OpenAI, Ollama, LM Studio)</li>
             <li>AI Chat Interface</li>
             <li>Customizable Overlay & Theme</li>
             <li>Support Folder with Logs & Metadata</li>
         </ul>
         <p>Powered by PaddleOCR, Argos Translate (example), and various AI APIs.</p>
         <br/>
         <p>(c) 2024 Your Name/Organization</p>
         """
         QMessageBox.about(self, "About Overlay Translate", about_text)

    def toggleCaptureWidgetClickThrough(self):
        """Safely call the toggle method on the capture widget."""
        if self.capture_widget:
            self.capture_widget.toggleClickThrough()
        else:
            logger.warning("Attempted to toggle click-through, but CaptureWidget is not available.")