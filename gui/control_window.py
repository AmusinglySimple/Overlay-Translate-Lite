# gui/control_window.py — Lite version (no AI, no chat, no complex features)

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

from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QInputDialog, QSlider, QMessageBox, QProgressBar, QSystemTrayIcon, QMenu,
    QFileDialog, QGroupBox, QCheckBox, QLineEdit, QApplication, QMenuBar, QDialog,
    QDialogButtonBox, QComboBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize, QPropertyAnimation, QPoint, QRect, QEasingCurve, QThread
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QColor, QFont, QActionGroup, QAction, QShortcut

# Internal imports (relative)
from .capture_widget import CaptureWidget
from .snipping_tool import SnippingTool
from .dialogs import IntroDialog, LiveTranslationWindow, ThemeDialog, TranslatedImageViewer
from .custom_widgets import CollapsibleBox, SectionSeparator

# Worker imports
from workers import TranslationWorker

# Utility imports
from utils.config import (
    SUPPORT_FOLDER, ensure_support_folder, MIN_OPACITY,
    PROJECT_ROOT, PREDEFINED_THEMES, DEFAULT_THEME, logger, get_current_theme, update_current_theme,
    DEFAULT_FONT_SIZE, PREVIEW_FONT_SIZE, MIN_FONT_SIZE, MAX_FONT_SIZE, FONT_SIZE_STEP,
    WORKER_STOP_TIMEOUT, CAPTURE_HIDE_DELAY, WORKER_CANCEL_TIMEOUT,
    LIVE_TRANSLATION_DEFAULT_INTERVAL, LIVE_TRANSLATION_MIN_INTERVAL, LIVE_TRANSLATION_MAX_INTERVAL,
    IMAGE_CHANGE_THRESHOLD_AGGRESSIVE, IMAGE_CHANGE_THRESHOLD_BALANCED, IMAGE_CHANGE_THRESHOLD_QUALITY,
    PERFORMANCE_MODE_AGGRESSIVE, PERFORMANCE_MODE_BALANCED, PERFORMANCE_MODE_QUALITY
)
from utils.helpers import (
    load_settings, save_settings, apply_theme, choose_font_for_text, get_system_font_path, resource_path
)
from utils.ocr_utils import APP_LANG_TO_PADDLE, get_paddle_model_directory
from utils.logging_config import shutdown_logging as shutdown_logging_system
from utils.validators import (
    validate_opacity,
    validate_font_size,
    validate_numeric_range
)
from PIL import Image


def shutdown_logging():
    """Safely closes and removes all handlers from the logger and shuts down logging system."""
    app_logger = logging.getLogger("OverlayTranslateLite")
    app_logger.info("=" * 60)
    app_logger.info("Initiating logging shutdown...")
    app_logger.info("=" * 60)
    
    if app_logger:
        handlers = app_logger.handlers[:]
        for handler in handlers:
            try:
                handler.close()
                app_logger.removeHandler(handler)
            except Exception as e:
                import sys
                print(f"Error closing log handler {handler}: {e}", file=sys.stderr)
    
    shutdown_logging_system()
    
    import sys
    if sys.stderr:
        print("Logging system has been shut down.", file=sys.stderr)


class ControlWindow(QMainWindow):
    translation_error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        logger.info("Initializing ControlWindow (Lite)...")
        self.live_translation_popout = None
        self.source_language = 'auto'
        self.target_language = 'en'
        self.tray_icon = None
        self.app_icon = None
        self.default_font_size = DEFAULT_FONT_SIZE
        self.default_font_type = "default"
        self.capture_widget = None
        self.snipping_tool = None
        self.font_size = PREVIEW_FONT_SIZE
        self.translation_worker = None
        self.is_live_capturing = False
        self.current_settings = {}

        self.live_translation_popout_was_visible = False
        self.last_viewer_settings = {}
        
        # Live translation performance settings
        self.live_performance_mode = PERFORMANCE_MODE_BALANCED
        self.live_translation_interval = LIVE_TRANSLATION_DEFAULT_INTERVAL
        self.image_comparator = None

        # Load initial configuration
        self.current_settings = load_settings()
        self.last_viewer_settings = self.current_settings.get("viewer_settings", {})
        logger.debug(f"Loaded initial last_viewer_settings: {self.last_viewer_settings}")

        self.showIntroDialog()

        try:
            self.capture_widget = CaptureWidget(control_window=self)
            self.snipping_tool = SnippingTool(self.capture_widget)
        except Exception as e:
             logger.critical(f"Failed to initialize CaptureWidget/SnippingTool: {e}", exc_info=True)
             QMessageBox.critical(self, self.tr("Startup Error"), self.tr("Failed to initialize core components:\n{}").format(e))

        self.initUI()
        self.setupGlobalShortcuts()
        self.load_state_from_settings()
        ensure_support_folder()

        self.translation_error_occurred.connect(self.displayTranslationError)
        logger.info("ControlWindow (Lite) initialization complete.")

    def showIntroDialog(self):
        intro_dialog = IntroDialog(self)
        intro_dialog.exec()

    def initUI(self):
        self.setWindowTitle(self.tr('Overlay Translate Lite'))
        flags = Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)

        # === CAPTURE CONTROLS SECTION ===
        self.capture_section = CollapsibleBox(self.tr("🎯 Capture Controls"), expanded=True)
        capture_layout = QHBoxLayout()
        self.capture_btn = self._createButton(self.tr('Capture (F1)'), self.captureScreen, 'capture.svg', self.tr("Capture selected area and translate"))
        self.live_capture_btn = self._createButton(self.tr('Live (F3)'), self.toggleLiveCapture, 'live.svg', self.tr("Toggle continuous live translation"), checkable=True)
        self.snip_btn = self._createButton(self.tr('Snip (F4)'), self.activateSnippingTool, 'snip.svg', self.tr("Select a new area with snipping tool"))
        capture_layout.addWidget(self.capture_btn)
        capture_layout.addWidget(self.live_capture_btn)
        capture_layout.addWidget(self.snip_btn)
        self.capture_section.content_layout.addLayout(capture_layout)
        main_layout.addWidget(self.capture_section)

        # === LIVE TRANSLATION PREVIEW SECTION ===
        self.live_preview_section = CollapsibleBox(self.tr("📺 Live Translation Preview"), expanded=True)
        self.live_translation_label = QLabel(self.tr("Live translation disabled."), self)
        self.live_translation_label.setWordWrap(True)
        self.live_translation_label.setAlignment(Qt.AlignCenter)
        self.live_translation_label.setObjectName("ControlWindowLiveLabel")
        self.live_translation_label.setStyleSheet(f"QLabel#ControlWindowLiveLabel {{ font-size: {self.font_size}px; }}")
        self.label_opacity_effect = QtWidgets.QGraphicsOpacityEffect(self.live_translation_label)
        self.live_translation_label.setGraphicsEffect(self.label_opacity_effect)
        self.label_fade_anim = QPropertyAnimation(self.label_opacity_effect, b"opacity", self)
        self.label_fade_anim.setDuration(400); self.label_fade_anim.setStartValue(0.0); self.label_fade_anim.setEndValue(1.0); self.label_fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.live_preview_section.content_layout.addWidget(self.live_translation_label)
        
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel(self.tr("Preview Size:"), self)); font_layout.addStretch(1)
        self.decrease_font_btn = self._createButton('-', self.decreaseFontSize, 'zoom_out.svg', self.tr("Decrease preview font size"), fixed_size=QSize(40, 40))
        self.increase_font_btn = self._createButton('+', self.increaseFontSize, 'zoom_in.svg', self.tr("Increase preview font size"), fixed_size=QSize(40, 40))
        font_layout.addWidget(self.decrease_font_btn); font_layout.addWidget(self.increase_font_btn)
        self.live_preview_section.content_layout.addLayout(font_layout)
        
        # Performance settings for live translation
        perf_layout = QVBoxLayout()
        perf_layout.setSpacing(5)
        
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel(self.tr("Performance Mode:"), self))
        self.performance_mode_combo = QComboBox(self)
        self.performance_mode_combo.addItem(self.tr("⚡ Aggressive (Skip Unchanged)"), PERFORMANCE_MODE_AGGRESSIVE)
        self.performance_mode_combo.addItem(self.tr("⚖️ Balanced (Default)"), PERFORMANCE_MODE_BALANCED)
        self.performance_mode_combo.addItem(self.tr("🎯 Quality (Always OCR)"), PERFORMANCE_MODE_QUALITY)
        self.performance_mode_combo.setCurrentIndex(1)
        self.performance_mode_combo.currentIndexChanged.connect(self.onPerformanceModeChanged)
        self.performance_mode_combo.setToolTip(self.tr("Control live translation performance vs accuracy trade-off"))
        mode_layout.addWidget(self.performance_mode_combo)
        perf_layout.addLayout(mode_layout)
        
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel(self.tr("Interval:"), self))
        self.interval_slider = QSlider(Qt.Horizontal, self)
        self.interval_slider.setRange(LIVE_TRANSLATION_MIN_INTERVAL, LIVE_TRANSLATION_MAX_INTERVAL)
        self.interval_slider.setValue(LIVE_TRANSLATION_DEFAULT_INTERVAL)
        self.interval_slider.setSingleStep(500)
        self.interval_slider.setPageStep(1000)
        self.interval_slider.valueChanged.connect(self.onIntervalChanged)
        self.interval_label = QLabel(f"{LIVE_TRANSLATION_DEFAULT_INTERVAL}ms", self)
        self.interval_label.setMinimumWidth(60)
        self.interval_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        interval_layout.addWidget(self.interval_slider)
        interval_layout.addWidget(self.interval_label)
        perf_layout.addLayout(interval_layout)
        
        self.live_preview_section.content_layout.addLayout(perf_layout)
        main_layout.addWidget(self.live_preview_section)

        # === OVERLAY SETTINGS SECTION ===
        self.overlay_section = CollapsibleBox(self.tr("⚙️ Overlay Settings"), expanded=True)
        
        initial_tooltip = self.tr("Allow mouse clicks to pass through the overlay")
        self.toggle_btn = self._createButton(self.tr('Make Click-Through (F2)'), self.toggleCaptureWidgetClickThrough, 'click.svg', initial_tooltip)
        self.overlay_section.content_layout.addWidget(self.toggle_btn)
        
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel(self.tr("Opacity:"), self))
        self.opacity_slider = QSlider(Qt.Horizontal, self)
        min_opacity_int = max(1, int(MIN_OPACITY * 100))
        self.opacity_slider.setRange(min_opacity_int, 100)
        self.opacity_slider.valueChanged.connect(self.adjustCaptureWidgetOpacity)
        opacity_layout.addWidget(self.opacity_slider)
        self.overlay_section.content_layout.addLayout(opacity_layout)
        main_layout.addWidget(self.overlay_section)

        # === PROGRESS BAR & SPINNER ===
        progress_layout = QHBoxLayout()
        
        from gui.custom_widgets import SvgSpinner
        self.translation_spinner = SvgSpinner(size=24, parent=self)
        self.translation_spinner.hide()
        progress_layout.addWidget(self.translation_spinner)
        
        self.translation_progress_bar = QProgressBar(self)
        self.translation_progress_bar.setRange(0, 100); self.translation_progress_bar.setValue(0); self.translation_progress_bar.setTextVisible(True)
        self.translation_progress_bar.setFormat("OCR/Translate: %p%"); self.translation_progress_bar.setVisible(False)
        progress_layout.addWidget(self.translation_progress_bar)
        
        main_layout.addLayout(progress_layout)

        main_layout.addStretch(1)

        self.setMenuBar(self.createMenuBar())

        # Simple status bar
        qt_status_bar = QtWidgets.QStatusBar(self)
        self.setStatusBar(qt_status_bar)
        qt_status_bar.setSizeGripEnabled(False)
        qt_status_bar.showMessage(self.tr("Ready"))
        qt_status_bar.show()

        if self.capture_widget: self.capture_widget.show()
        else: logger.error("CaptureWidget not initialized before attempting to show!")

        self.live_capture_timer = QTimer(self)
        self.live_capture_timer.timeout.connect(self.captureScreenForLiveTranslation)
        self.live_capture_timer.setInterval(3000)

        self.initTrayIcon()
        self.apply_initial_settings()
        if self.app_icon:
            self.setWindowIcon(self.app_icon)

    def createMenuBar(self):
        menu_bar = QMenuBar(self)
        file_menu = menu_bar.addMenu(self.tr("&File"))
        tray_action = QAction(self.tr("Minimize to Tray"), self); tray_action.triggered.connect(self.minimizeToTray); file_menu.addAction(tray_action)
        exit_action = QAction(self.tr("Exit"), self); exit_action.triggered.connect(self.closeApplication); exit_action.setShortcut(QKeySequence.Quit); file_menu.addAction(exit_action)

        settings_menu = menu_bar.addMenu(self.tr("&Settings"))
        lang_menu = settings_menu.addMenu(self.tr("Translation Languages"))
        src_lang_action = QAction(self.tr("Set Source Language..."), self); src_lang_action.triggered.connect(self.selectSourceLanguage); lang_menu.addAction(src_lang_action)
        tgt_lang_action = QAction(self.tr("Set Target Language..."), self); tgt_lang_action.triggered.connect(self.selectTargetLanguage); lang_menu.addAction(tgt_lang_action)
        font_menu = settings_menu.addMenu(self.tr("Translation Font"))
        font_size_action = QAction(self.tr("Set Default Font Size..."), self); font_size_action.triggered.connect(self.setDefaultFontSize); font_menu.addAction(font_size_action)
        font_type_action = QAction(self.tr("Set Default Font Type..."), self); font_type_action.triggered.connect(self.setDefaultFontType); font_menu.addAction(font_type_action)
        settings_menu.addSeparator()
        
        # Theme menu
        theme_menu = settings_menu.addMenu(self.tr("Theme"))
        self.theme_action_group = QActionGroup(self); self.theme_action_group.setExclusive(True)
        current_theme_name = get_current_theme().get("name", "Default Neon")
        
        for theme_name in sorted(PREDEFINED_THEMES.keys()):
            action = QAction(theme_name, self, checkable=True)
            action.triggered.connect(lambda checked=False, name=theme_name: self.switch_theme(name))
            if theme_name == current_theme_name: action.setChecked(True)
            theme_menu.addAction(action)
            self.theme_action_group.addAction(action)
        
        theme_menu.addSeparator()
        theme_menu.addAction(self.tr("Edit Current Theme..."), self.openThemeEditor)
        
        settings_menu.addSeparator()
        server_action = QAction(self.tr("Open Translation Server UI"), self); server_action.triggered.connect(self.openServer); settings_menu.addAction(server_action)
        settings_menu.addSeparator()

        tools_menu = menu_bar.addMenu(self.tr("&Tools"))
        live_popout_action = QAction(self.tr("Pop Out Live Translation"), self); live_popout_action.triggered.connect(self.popOutLiveTranslation); tools_menu.addAction(live_popout_action)

        help_menu = menu_bar.addMenu(self.tr("&Help"))
        about_action = QAction(self.tr("About"), self); about_action.triggered.connect(self.showAboutDialog); help_menu.addAction(about_action)
        folder_action = QAction(self.tr("Open Support Folder"), self); folder_action.triggered.connect(self.openSupportFolder); help_menu.addAction(folder_action)
        ocr_info_action = QAction(self.tr("OCR Engine Info..."), self); ocr_info_action.triggered.connect(self.show_paddleocr_info); help_menu.addAction(ocr_info_action)

        return menu_bar

    def openThemeEditor(self):
        dialog = ThemeDialog(self)
        dialog.exec()
        self.update_theme_menu_checkstate()

    def update_theme_menu_checkstate(self):
        current_theme_name = get_current_theme().get("name", "")
        for action in self.theme_action_group.actions():
            action.setChecked(action.text() == current_theme_name)

    def switch_theme(self, theme_name):
        if theme_name in PREDEFINED_THEMES and get_current_theme().get("name") != theme_name:
            new_theme = PREDEFINED_THEMES[theme_name]
            update_current_theme(new_theme)
            apply_theme()
            save_settings(self.gather_current_state())
            logger.info(f"Switched theme to '{theme_name}' and saved settings.")

    def create_separator(self):
        line = QtWidgets.QFrame(); line.setFrameShape(QtWidgets.QFrame.HLine); line.setFrameShadow(QtWidgets.QFrame.Sunken); line.setStyleSheet("margin: 5px 0;")
        return line

    def apply_initial_settings(self):
        fs = self.current_settings.get('font_settings', {})
        self.default_font_size = fs.get('size', 20); self.default_font_type = fs.get('type', 'default')
        if self.capture_widget:
            self.capture_widget.default_font_size = self.default_font_size; self.capture_widget.default_font_type = self.default_font_type
        capture_state = self.current_settings.get('CaptureWidget', {})
        loaded_opacity = capture_state.get('opacity', 0.8)
        min_slider_val = self.opacity_slider.minimum(); max_slider_val = self.opacity_slider.maximum()
        slider_value = int(max(min_slider_val / 100.0, min(max_slider_val / 100.0, loaded_opacity)) * 100)
        self.opacity_slider.setValue(slider_value)
        self.live_capture_btn.setChecked(False); self._update_live_button_style(False)
        
        # Restore collapsible section states
        section_states = self.current_settings.get('collapsible_sections', {})
        if hasattr(self, 'capture_section'):
            self.capture_section.set_expanded(section_states.get('capture', True), animate=False)
        if hasattr(self, 'live_preview_section'):
            self.live_preview_section.set_expanded(section_states.get('live_preview', True), animate=False)
        if hasattr(self, 'overlay_section'):
            self.overlay_section.set_expanded(section_states.get('overlay', True), animate=False)
        
        # Restore live translation performance settings
        perf_settings = self.current_settings.get('live_performance', {})
        saved_mode = perf_settings.get('mode', PERFORMANCE_MODE_BALANCED)
        saved_interval = perf_settings.get('interval', LIVE_TRANSLATION_DEFAULT_INTERVAL)
        
        if hasattr(self, 'performance_mode_combo'):
            for i in range(self.performance_mode_combo.count()):
                if self.performance_mode_combo.itemData(i) == saved_mode:
                    self.performance_mode_combo.setCurrentIndex(i)
                    break
        
        if hasattr(self, 'interval_slider'):
            self.interval_slider.setValue(saved_interval)
        
        self.live_performance_mode = saved_mode
        self.live_translation_interval = saved_interval

    def load_state_from_settings(self):
        if 'ControlWindow' in self.current_settings:
            try:
                geometry = self.current_settings['ControlWindow']
                if all(k in geometry for k in ('x', 'y', 'width', 'height')):
                    self.setGeometry(int(geometry['x']), int(geometry['y']), int(geometry['width']), int(geometry['height']))
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Could not restore window geometry: {e}")
                self.resize(500, 550)
        else: self.resize(500, 550)
    
    def openSupportFolder(self):
        folder_path = SUPPORT_FOLDER; logger.info(f"Opening Support Folder: {folder_path}")
        try:
            if not os.path.exists(folder_path): ensure_support_folder()
            system = platform.system()
            if system == "Windows": os.startfile(folder_path)
            elif system == "Darwin": subprocess.Popen(["open", folder_path])
            else: subprocess.Popen(["xdg-open", folder_path])
        except Exception as e: QMessageBox.warning(self, self.tr("Error"), self.tr("Could not open the Support folder.\nError: {}").format(e))

    def _createButton(self, text, callback, icon_name, tooltip="", fixed_size=None, checkable=False):
        button = QPushButton(text, self)
        if icon_name:
            icon_path = resource_path(os.path.join("assets", "icons", icon_name))
            if os.path.exists(icon_path): button.setIcon(QIcon(icon_path)); button.setIconSize(QSize(18, 18))
        button.clicked.connect(callback); button.setToolTip(tooltip); button.setCheckable(checkable)
        if fixed_size: button.setFixedSize(fixed_size)
        else: button.setMinimumHeight(35); button.setMinimumWidth(60)
        return button

    def _update_live_button_style(self, is_live):
        self.live_capture_btn.setText(self.tr('Stop (F3)') if is_live else self.tr('Live (F3)'))
        icon_name = 'stop.svg' if is_live else 'live.svg'
        icon_path = resource_path(os.path.join("assets", "icons", icon_name))
        if os.path.exists(icon_path): self.live_capture_btn.setIcon(QIcon(icon_path))
        self.live_capture_btn.setToolTip(self.tr("Stop continuous live translation") if is_live else self.tr("Toggle continuous live translation"))
        self.live_capture_btn.setProperty("liveActive", is_live)
        self.live_capture_btn.style().unpolish(self.live_capture_btn); self.live_capture_btn.style().polish(self.live_capture_btn)

    def onPerformanceModeChanged(self, index):
        mode = self.performance_mode_combo.itemData(index)
        self.live_performance_mode = mode
        logger.info(f"Performance mode changed to: {mode}")
        
        if mode == PERFORMANCE_MODE_AGGRESSIVE:
            suggested_interval = 2000
        elif mode == PERFORMANCE_MODE_QUALITY:
            suggested_interval = 4000
        else:
            suggested_interval = LIVE_TRANSLATION_DEFAULT_INTERVAL
        
        if self.interval_slider.value() == self.live_translation_interval:
            self.interval_slider.setValue(suggested_interval)
    
    def onIntervalChanged(self, value):
        self.live_translation_interval = value
        self.interval_label.setText(f"{value}ms")
        
        if self.is_live_capturing:
            self.live_capture_timer.setInterval(value)
            logger.debug(f"Live capture interval updated to {value}ms")
    
    def toggleLiveCapture(self):
        if self.is_live_capturing:
            self.live_capture_timer.stop(); self.is_live_capturing = False; self._update_live_button_style(False)
            self.live_translation_label.setText(self.tr("Live translation disabled.")); self.label_opacity_effect.setOpacity(1.0)
            if self.translation_worker and self.translation_worker.isRunning(): self.translation_worker.stop()
            if self.image_comparator:
                self.image_comparator.reset()
                self.image_comparator = None
        else:
            if not self.capture_widget or not self.capture_widget.isVisible():
                QMessageBox.warning(self, self.tr("Overlay Hidden"), self.tr("Please show the capture overlay first.")); self.live_capture_btn.setChecked(False); return
            
            from utils.image_comparison import ImageComparator
            self.image_comparator = ImageComparator()
            logger.debug(f"Starting live capture with performance mode: {self.live_performance_mode}")
            
            self.live_capture_timer.setInterval(self.live_translation_interval)
            self.live_capture_timer.start(); self.is_live_capturing = True; self._update_live_button_style(True)
            self.live_translation_label.setText(self.tr("Live capture active...")); self.label_opacity_effect.setOpacity(1.0)
            QTimer.singleShot(50, self.captureScreenForLiveTranslation)

    def hide_progress_bar(self):
        self.translation_progress_bar.hide()
        self.translation_spinner.stop()

    def captureScreen(self):
        if not self.capture_widget or not self.capture_widget.isVisible(): QMessageBox.warning(self, self.tr("Overlay Hidden"), self.tr("Please show the capture overlay.")); return
        
        self.statusBar().showMessage(self.tr("Capturing..."))
        self.translation_progress_bar.setVisible(True); self.translation_spinner.start(); self.translation_progress_bar.setValue(0); self.translation_progress_bar.setFormat("Capturing...")
        QApplication.processEvents()
        
        try:
            overlay_geometry = self.capture_widget.geometry()
            
            # Multi-monitor fix
            widget_center = overlay_geometry.center()
            screen = QApplication.screenAt(widget_center)
            if screen is None:
                screen = QApplication.primaryScreen()
            screen_geo = screen.geometry()
            
            grab_x = overlay_geometry.x() - screen_geo.x()
            grab_y = overlay_geometry.y() - screen_geo.y()
            grab_w = overlay_geometry.width()
            grab_h = overlay_geometry.height()
            
            self.capture_widget.hide(); QApplication.processEvents(); time.sleep(CAPTURE_HIDE_DELAY)
            screenshot = screen.grabWindow(0, grab_x, grab_y, grab_w, grab_h)
            self.capture_widget.show(); QApplication.processEvents()
            if screenshot.isNull(): raise Exception("Grabbed null pixmap.")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f"); ensure_support_folder()
            fileName = os.path.join(SUPPORT_FOLDER, f"capture_{timestamp}.png")
            if not screenshot.save(fileName, "PNG"): raise Exception(f"Failed to save screenshot.")
            self.capture_widget.current_capture_path = fileName
            
            self.statusBar().showMessage(self.tr("Translating..."))
            self.translation_progress_bar.setFormat("Translating... %p%"); self.translation_progress_bar.setValue(10)
            self.initiate_translation_from_file(fileName)
        except Exception as e:
            logger.error(f"Screen grab failed: {e}", exc_info=True)
            self.statusBar().showMessage(self.tr("Capture failed"))
            self.translation_progress_bar.setFormat("Capture Failed"); self.translation_progress_bar.setValue(0)
            if self.capture_widget and not self.capture_widget.isVisible(): self.capture_widget.show()
            QMessageBox.critical(self, self.tr("Capture Error"), self.tr("Screen capture failed.\nError: {}").format(e))

    def captureScreenForLiveTranslation(self):
        if not self.is_live_capturing or not self.capture_widget or not self.capture_widget.isVisible(): return
        try:
            overlay_geometry = self.capture_widget.geometry()
            
            # Multi-monitor fix
            widget_center = overlay_geometry.center()
            screen = QApplication.screenAt(widget_center)
            if screen is None:
                screen = QApplication.primaryScreen()
            screen_geo = screen.geometry()
            
            grab_x = overlay_geometry.x() - screen_geo.x()
            grab_y = overlay_geometry.y() - screen_geo.y()
            grab_w = overlay_geometry.width()
            grab_h = overlay_geometry.height()
            
            screenshot = screen.grabWindow(0, grab_x, grab_y, grab_w, grab_h)
            if screenshot.isNull(): raise Exception("Grabbed null pixmap for live.")
            temp_live_dir = os.path.join(SUPPORT_FOLDER, "temp"); os.makedirs(temp_live_dir, exist_ok=True)
            tempFile = os.path.join(temp_live_dir, 'live_capture.png')
            if not screenshot.save(tempFile, "PNG"): raise Exception("Failed to save live screenshot.")
            
            should_process = True
            if self.live_performance_mode != PERFORMANCE_MODE_QUALITY and self.image_comparator:
                import cv2
                current_image = cv2.imread(tempFile)
                if current_image is not None:
                    if self.live_performance_mode == PERFORMANCE_MODE_AGGRESSIVE:
                        threshold = IMAGE_CHANGE_THRESHOLD_AGGRESSIVE
                    else:
                        threshold = IMAGE_CHANGE_THRESHOLD_BALANCED
                    
                    has_changed, change_amount = self.image_comparator.has_changed(
                        current_image, 
                        threshold=threshold,
                        method='pixel'
                    )
                    
                    if not has_changed:
                        should_process = False
                        logger.debug(f"Content unchanged (change: {change_amount:.2%}, threshold: {threshold:.2%}), skipping OCR")
                        if self.live_translation_popout and self.live_translation_popout.isVisible():
                            self.live_translation_popout.show_skip_indicator(True)
                        else:
                            self.label_opacity_effect.setOpacity(0.7)
                    else:
                        if self.live_translation_popout and self.live_translation_popout.isVisible():
                            self.live_translation_popout.show_skip_indicator(False)
            
            if should_process:
                if not (self.translation_worker and self.translation_worker.isRunning()): 
                    self.initiate_translation_from_file(tempFile, is_live=True)
            
        except Exception as e:
            error_text = f"Live Capture Error: {str(e)[:100]}"; logger.error(f"Live capture failed: {e}", exc_info=True)
            if self.live_translation_popout and self.live_translation_popout.isVisible(): self.live_translation_popout.updateTranslation(error_text)
            else: self.live_translation_label.setText(error_text); self.label_opacity_effect.setOpacity(1.0)

    def initiate_translation_from_file(self, file_path, is_live=False, is_snip=False):
        if self.translation_worker and self.translation_worker.isRunning():
            if is_live:
                logger.debug("Skipping new live worker as previous is running.")
                return
            else:
                logger.warning("Stopping previous worker for new non-live capture.")
                self.translation_worker.stop()
                if not self.translation_worker.wait(WORKER_CANCEL_TIMEOUT): 
                    logger.error("Previous translation worker did not stop gracefully!")
        
        contrast = self.capture_widget.contrast_factor if self.capture_widget else 1.0
        if not is_live: self.capture_widget.current_capture_path = file_path
        fonts = self.capture_widget.fonts if self.capture_widget else {}
        
        self.translation_worker = TranslationWorker(
            file_name=file_path,
            source_language=self.source_language,
            target_language=self.target_language,
            fonts=fonts,
            use_translate_with_ai=False,
            contrast_factor=contrast,
            live=is_live,
            parent=self
        )
        self.translation_worker.translation_complete.connect(self.handleTranslationResult)
        self.translation_worker.error.connect(self.handleTranslationError)
        self.translation_worker.finished.connect(self.onTranslationWorkerFinished)
        
        self.translation_worker.start()

    def handleTranslationResult(self, result):
        if not isinstance(result, dict): self.handleTranslationError("Invalid result format."); return
        is_live = result.get('live', False); error_message = result.get('error_message', ''); translated_text = result.get('translated_text', '')
        if error_message:
            if not is_live: self.translation_progress_bar.setFormat("Processing Error"); self.translation_progress_bar.setValue(0); QTimer.singleShot(3000, self.hide_progress_bar)
            return
        if is_live:
            compact_text = translated_text.replace('\n', ' ').strip()
            if compact_text and "Translation Failed" not in compact_text and "Error:" not in compact_text:
                if self.live_translation_popout and self.live_translation_popout.isVisible():
                    self.live_translation_popout.updateTranslation(compact_text); self.live_translation_popout.trigger_fade_in()
                else:
                    self.live_translation_label.setText(compact_text); self.live_translation_label.setFont(choose_font_for_text(compact_text, font_size=self.font_size))
                    self.label_fade_anim.stop(); self.label_opacity_effect.setOpacity(0.0); self.label_fade_anim.start()
        else:
            if self.translation_progress_bar.isVisible():
                self.translation_progress_bar.setValue(100); self.translation_progress_bar.setFormat("Complete!"); QTimer.singleShot(2000, self.hide_progress_bar)
            try:
                original_image_path = self.capture_widget.current_capture_path
                original_text = result.get('original_text')
                
                if original_image_path and os.path.exists(original_image_path) and original_text:
                    base_name = os.path.splitext(os.path.basename(original_image_path))[0]
                    txt_filepath = os.path.join(SUPPORT_FOLDER, f"{base_name}.txt")
                    timestamp_str = result.get('timestamp', datetime.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
                    metadata = f"Timestamp: {timestamp_str}\nSource: {self.source_language}\nTarget: {self.target_language}\n\n--- Original ---\n{original_text}\n\n--- Translated ---\n{result.get('translated_text', 'N/A')}"
                    with open(txt_filepath, 'w', encoding='utf-8') as f: f.write(metadata)
            except Exception as meta_err: logger.error(f"Failed to save metadata: {meta_err}", exc_info=True)
            
            try:
                if self.capture_widget:
                    viewer_file_path = self.capture_widget.current_capture_path
                    if viewer_file_path and os.path.exists(viewer_file_path):
                        self.capture_widget.displayTranslatedImage(result, viewer_file_path, self.target_language)
                    else: QMessageBox.critical(self, self.tr("Viewer Error"), self.tr("Invalid image path for viewer."))
            except RuntimeError as re:
                logger.warning(f"RuntimeError accessing capture_widget (C++ object may be deleted): {re}")

    def handleTranslationError(self, error_message): self.translation_error_occurred.emit(error_message)

    def displayTranslationError(self, error_message):
        error_text = f"Error: {error_message[:100]}"
        if self.is_live_capturing:
            if self.live_translation_popout and self.live_translation_popout.isVisible(): self.live_translation_popout.updateTranslation(error_text)
            else: self.live_translation_label.setText(error_text); self.label_opacity_effect.setOpacity(1.0)
        else:
            if self.translation_progress_bar.isVisible(): self.translation_progress_bar.setFormat(self.tr("Error")); self.translation_progress_bar.setValue(0); QTimer.singleShot(3000, self.hide_progress_bar)
            QMessageBox.warning(self, self.tr("Translation Error"), self.tr("An error occurred:\n\n{}").format(error_message))

    def onTranslationWorkerFinished(self):
        if not self.is_live_capturing:
            self.statusBar().showMessage(self.tr("Ready"))
        if not self.is_live_capturing and self.translation_progress_bar.isVisible():
            if not (self.translation_progress_bar.value() == 100 or "Error" in self.translation_progress_bar.format()):
                QTimer.singleShot(2000, self.hide_progress_bar)
        self.translation_worker = None

    def initTrayIcon(self):
        if self.app_icon is None:
            icon_path = resource_path(os.path.join("assets", "icon.png"))
            if os.path.exists(icon_path):
                self.app_icon = QIcon(icon_path)
            else:
                logger.error(f"Tray icon not found at {icon_path}. Tray functionality disabled.")
                return
        if not self.app_icon: return
        
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_icon.setToolTip(self.tr("Overlay Translate Lite"))        
        tray_menu = QMenu(self)
        restore = QAction(self.tr("Show Controls"), self); restore.triggered.connect(self.restoreFromTray); tray_menu.addAction(restore)
        capture = QAction(self.tr("Capture (F1)"), self); capture.triggered.connect(self.captureScreen); tray_menu.addAction(capture)
        snip = QAction("Snip (F4)", self); snip.triggered.connect(self.activateSnippingTool); tray_menu.addAction(snip)
        tray_menu.addSeparator()
        exit_action = QAction("Exit", self); exit_action.triggered.connect(self.closeApplication); tray_menu.addAction(exit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.trayIconActivated)
        self.tray_icon.show()
        logger.info("System tray icon initialized.")
    
    def trayIconActivated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick: self.restoreFromTray()

    def minimizeToTray(self):
        self.live_translation_popout_was_visible = bool(self.live_translation_popout and self.live_translation_popout.isVisible())
        
        self.hide()
        if self.capture_widget: self.capture_widget.hide()
        if self.live_translation_popout: self.live_translation_popout.hide()
        
        if self.tray_icon: 
            self.tray_icon.showMessage("Overlay Translate Lite", "Minimized to tray.", QSystemTrayIcon.MessageIcon.Information, 3000)

    def restoreFromTray(self):
        self.showNormal()
        self.show()
        
        if self.capture_widget: 
            self.capture_widget.show()
        
        if hasattr(self, 'live_translation_popout_was_visible') and self.live_translation_popout_was_visible and self.live_translation_popout:
            self.live_translation_popout.show()
        
        self.raise_()
        self.activateWindow()
        logger.info("Main window restored")

    def closeEvent(self, event):
        if hasattr(self, '_is_closing_application') and self._is_closing_application:
            event.accept()
            return
        event.ignore()
        self.minimizeToTray()

    def update_last_viewer_settings(self, settings_dict): self.last_viewer_settings = settings_dict if isinstance(settings_dict, dict) else self.last_viewer_settings

    def gather_current_state(self):
        state = {'ControlWindow': {'x': self.x(), 'y': self.y(), 'width': self.width(), 'height': self.height()}}
        if self.capture_widget: state['CaptureWidget'] = self.capture_widget.get_state()
        if self.live_translation_popout: state['LiveTranslationWindow'] = self.live_translation_popout.save_geometry()
        active_viewer = next((w for w in QApplication.topLevelWidgets() if isinstance(w, TranslatedImageViewer) and w.isVisible()), None)
        if active_viewer: state['TranslatedImageViewer'] = active_viewer.get_geometry_settings()
        state['viewer_settings'] = self.last_viewer_settings
        state['font_settings'] = {'size': self.default_font_size, 'type': self.default_font_type}
        state['settings'] = {}
        
        state['collapsible_sections'] = {
            'capture': self.capture_section.is_expanded() if hasattr(self, 'capture_section') else True,
            'live_preview': self.live_preview_section.is_expanded() if hasattr(self, 'live_preview_section') else True,
            'overlay': self.overlay_section.is_expanded() if hasattr(self, 'overlay_section') else True,
        }
        
        state['live_performance'] = {
            'mode': self.live_performance_mode,
            'interval': self.live_translation_interval
        }
        
        return state

    def closeApplication(self):
        logger.info("Application closure requested by user")
        self._is_closing_application = True
        
        if self.is_live_capturing: self.live_capture_timer.stop()
        
        # Properly cleanup translation worker
        if self.translation_worker:
            try:
                self.translation_worker.translation_complete.disconnect()
                self.translation_worker.error.disconnect()
                self.translation_worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            if self.translation_worker.isRunning():
                self.translation_worker.stop()
                if not self.translation_worker.wait(WORKER_STOP_TIMEOUT * 2):
                    logger.warning("Translation worker did not stop gracefully, terminating...")
                    self.translation_worker.terminate()
                    self.translation_worker.wait(1000)
            self.translation_worker.deleteLater()
            self.translation_worker = None
        
        if self.live_translation_popout and self.live_translation_popout.isVisible(): self.live_translation_popout.close()

        final_state = self.gather_current_state()
        if self.capture_widget: self.capture_widget.cleanup(); self.capture_widget.close()
        if self.tray_icon: self.tray_icon.hide()
        
        logger.info("Saving final application state...")
        save_settings(final_state)

        shutdown_logging()
        
        if os.path.exists(SUPPORT_FOLDER):
            import sys
            if sys.stderr:
                print(f"Prompting user for Support folder cleanup: {SUPPORT_FOLDER}", file=sys.stderr)
            msgBox = QMessageBox(self); msgBox.setWindowModality(Qt.WindowModal)
            msgBox.setWindowTitle("Clean Up Support Folder?"); msgBox.setText(f"Clean up Support folder?\n\n<i>{SUPPORT_FOLDER}</i>\n\n<b>Warning:</b> Deleting cannot be undone.")
            msgBox.setTextFormat(Qt.RichText); msgBox.setIcon(QMessageBox.Icon.Question)
            zipDeleteButton = msgBox.addButton("Zip & Delete", QMessageBox.ButtonRole.ActionRole)
            deleteButton = msgBox.addButton("Delete Folder", QMessageBox.ButtonRole.DestructiveRole)
            keepButton = msgBox.addButton("Just Close", QMessageBox.ButtonRole.AcceptRole)
            msgBox.setDefaultButton(keepButton); msgBox.exec(); clickedBtn = msgBox.clickedButton()

            if clickedBtn == zipDeleteButton:
                zip_success = False; zip_filename = ""
                try:
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
                    zip_filename = os.path.join(desktop_path, f"OverlayTranslate_Support_{timestamp}.zip")
                    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, _, files in os.walk(SUPPORT_FOLDER):
                            for file in files:
                                file_path = os.path.join(root, file)
                                zipf.write(file_path, os.path.relpath(file_path, SUPPORT_FOLDER))
                    zip_success = True
                    QMessageBox.information(self, self.tr("Zip Created"), self.tr("Support folder archived to:\n{}").format(zip_filename))
                except Exception as e:
                    QMessageBox.critical(self, self.tr("Zip Error"), self.tr("Could not create zip archive.\nError: {}\n\nFolder NOT deleted.").format(e))
                if zip_success:
                    try: shutil.rmtree(SUPPORT_FOLDER)
                    except Exception as e: QMessageBox.warning(self, self.tr("Cleanup Error"), self.tr("Could not delete original Support folder after zipping:\n{}").format(e))
            elif clickedBtn == deleteButton:
                try: shutil.rmtree(SUPPORT_FOLDER); QMessageBox.information(self, self.tr("Folder Deleted"), self.tr("Support folder deleted."))
                except Exception as e: QMessageBox.warning(self, self.tr("Cleanup Error"), self.tr("Could not delete Support folder:\n{}").format(e))

        import sys
        if sys.stderr:
            print("Exiting application via QApplication.quit().", file=sys.stderr)
        QApplication.quit()

    def activateSnippingTool(self):
        if self.snipping_tool:
            if self.capture_widget: self.capture_widget.hide()
            self.snipping_tool.show()
    
    def increaseFontSize(self):
        new_size = min(self.font_size + FONT_SIZE_STEP, MAX_FONT_SIZE)
        valid, error = validate_font_size(new_size)
        if valid:
            self.font_size = new_size
            self.live_translation_label.setStyleSheet(f"QLabel#ControlWindowLiveLabel {{ font-size: {self.font_size}px; }}")
            if self.live_translation_popout and self.live_translation_popout.isVisible():
                self.live_translation_popout.set_font_size(self.font_size)
        else:
            logger.warning(f"Invalid font size: {error}")
    
    def decreaseFontSize(self):
        new_size = max(self.font_size - FONT_SIZE_STEP, MIN_FONT_SIZE)
        valid, error = validate_font_size(new_size)
        if valid:
            self.font_size = new_size
            self.live_translation_label.setStyleSheet(f"QLabel#ControlWindowLiveLabel {{ font-size: {self.font_size}px; }}")
            if self.live_translation_popout and self.live_translation_popout.isVisible():
                self.live_translation_popout.set_font_size(self.font_size)
        else:
            logger.warning(f"Invalid font size: {error}")

    def popOutLiveTranslation(self):
        if self.live_translation_popout is None or not self.live_translation_popout.isVisible():
            self.live_translation_popout = LiveTranslationWindow(self)
            self.live_translation_popout.set_font_size(self.font_size)
            current_text = self.live_translation_label.text()
            if "disabled" in current_text or "active" in current_text or "popped out" in current_text: self.live_translation_popout.updateTranslation(self.tr("Waiting..."))
            else: self.live_translation_popout.updateTranslation(current_text)
            self.live_translation_popout.show(); self.live_translation_label.setText(self.tr("Live view popped out."))
        else: self.live_translation_popout.close(); self.live_translation_popout = None; self.live_translation_label.setText(self.tr("Live translation disabled."))
        self.label_opacity_effect.setOpacity(1.0)
    
    def setDefaultFontSize(self):
        size, ok = QInputDialog.getInt(self, self.tr("Font Size"), self.tr("Default font size:"), self.default_font_size, 8, 72)
        if ok: self.default_font_size = size; self.capture_widget.default_font_size = size
    
    def setDefaultFontType(self):
        font_options = {
            self.tr("Roboto (Default Latin)"): "default", self.tr("Arial (Fallback)"): "Arial",
            self.tr("Microsoft YaHei (Chinese)"): "zh", self.tr("MS Gothic (Japanese)"): "ja",
            self.tr("Malgun Gothic (Korean)"): "ko" }
        current_key = next((key for key, value in font_options.items() if value == self.default_font_type), self.tr("Roboto (Default Latin)"))
        dialog = QInputDialog(self); dialog.setWindowTitle(self.tr("Set Default Font Category"))
        dialog.setLabelText(self.tr("Choose default font category for viewer:")); dialog.setComboBoxItems(list(font_options.keys()))
        dialog.setTextValue(current_key)
        if dialog.exec():
            font_display_name = dialog.textValue()
            if font_display_name in font_options:
                self.default_font_type = font_options[font_display_name]
                if self.capture_widget: self.capture_widget.default_font_type = self.default_font_type

    def adjustCaptureWidgetOpacity(self, value):
        if self.capture_widget:
            opacity = max(MIN_OPACITY, value / 100.0)
            valid, error = validate_opacity(opacity)
            if not valid:
                logger.warning(f"Invalid opacity value: {error}. Clamping to valid range.")
                opacity = max(MIN_OPACITY, min(1.0, opacity))
            self.capture_widget.setWindowOpacity(opacity); self.capture_widget.updateClickThroughState()
    
    def selectSourceLanguage(self):
        languages = {"Auto Detect": "auto", "English": "en", "Chinese (Simp)": "ch", "Japanese": "ja", "Korean": "ko", "French": "fr", "Spanish": "es", "Russian": "ru", "German": "de"}
        current = next((k for k, v in languages.items() if v == self.source_language), "Auto Detect")
        choice, ok = QInputDialog.getItem(self, "Select OCR Language", "Source Language:", languages.keys(), list(languages.keys()).index(current), False)
        if ok and choice: self.source_language = languages[choice]; logger.info(f"Source language set to: {choice} ({self.source_language})")
    
    def selectTargetLanguage(self):
        languages = {"English": "en", "Spanish": "es", "French": "fr", "German": "de", "Italian": "it", "Portuguese": "pt", "Russian": "ru", "Chinese (Simplified)": "zh", "Japanese": "ja", "Korean": "ko"}
        current = next((k for k, v in languages.items() if v == self.target_language), "English")
        choice, ok = QInputDialog.getItem(self, "Select Target Language", "Target Language:", languages.keys(), list(languages.keys()).index(current), False)
        if ok and choice: self.target_language = languages[choice]; self.capture_widget.target_language = self.target_language; logger.info(f"Target language set to: {choice} ({self.target_language})")
    
    def openServer(self): webbrowser.open("http://127.0.0.1:5000")
    
    def setupGlobalShortcuts(self):
        QShortcut(QKeySequence("F1"), self).activated.connect(self.captureScreen)
        if self.capture_widget: QShortcut(QKeySequence("F2"), self).activated.connect(self.toggleCaptureWidgetClickThrough)
        QShortcut(QKeySequence("F3"), self).activated.connect(self.toggleLiveCapture)
        QShortcut(QKeySequence("F4"), self).activated.connect(self.activateSnippingTool)
    
    def showAboutDialog(self):
        from __version__ import __version__
        QMessageBox.about(self, "About Overlay Translate Lite", f"<b>Overlay Translate Lite</b> - Version {__version__}\n<p>Powered by PaddleOCR and Argos Translate.</p>")
    
    def show_paddleocr_info(self):
        try:
            model_dir = get_paddle_model_directory()
            info_text = (
                f"<b>PaddleOCR Configuration:</b>\n\n"
                f"<b>Model Storage Directory:</b>\n{model_dir}\n\n"
                f"<small>PaddleOCR automatically downloads models to this directory on first use for a specific language. Ensure you have an internet connection for new languages.</small>"
            )
            QMessageBox.information(self, "PaddleOCR Information", info_text)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not retrieve PaddleOCR information.\nError: {e}")
    
    def toggleCaptureWidgetClickThrough(self):
        if self.capture_widget: self.capture_widget.toggleClickThrough()
