import os
import sys
import time
import datetime
import logging
import requests
import subprocess
import webbrowser
import textwrap
import tempfile
import shutil
import json
import gc
import platform

from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtWidgets import (
    QDialog, QApplication, QVBoxLayout, QLabel, QMainWindow, QPushButton,
    QInputDialog, QSlider, QMessageBox, QProgressBar, QSystemTrayIcon, QMenu,
    QWidget, QHBoxLayout, QTextEdit, QLineEdit, QFileDialog, QShortcut, QGroupBox
)
from PyQt5.QtCore import Qt, QPoint, QRect, QRectF, QTimer, QThread, pyqtSignal, QPropertyAnimation
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QImage, QLinearGradient, QKeySequence
from PyQt5.QtWidgets import QGraphicsOpacityEffect

from PIL import Image, ImageDraw, ImageFont, ImageOps
from paddleocr import PaddleOCR
from langdetect import detect
import cv2
import numpy as np

# Logging setup
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Define project root directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Configuration file for window positions and settings
CONFIG_FILE = os.path.join(PROJECT_ROOT, "window_positions.json")
SUPPORT_FOLDER = os.path.join(os.path.expanduser("~/Desktop"), "Support")

# Global instances
paddle_ocr = None
ai_api_config = {"provider": None, "api_key": None, "endpoint": None}

# Function to get system font paths based on OS
def get_system_font_path(font_name):
    system = platform.system()
    font_paths = {
        "Windows": {
            "Arial": r"C:\Windows\Fonts\arial.ttf",
            "MSYH": r"C:\Windows\Fonts\msyh.ttc",
            "Malgun": r"C:\Windows\Fonts\malgun.ttf",
        },
        "Darwin": {
            "Arial": "/Library/Fonts/Arial.ttf",
            "MSYH": "/System/Library/Fonts/STHeiti Light.ttc",
            "Malgun": "/System/Library/Fonts/AppleGothic.ttf",
        },
        "Linux": {
            "Arial": "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
            "MSYH": "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "Malgun": "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.ttf",
        }
    }
    
    default_font = "arial.ttf"
    font_map = font_paths.get(system, {})
    
    if font_name == "default":
        font_path = font_map.get("Arial", default_font)
    elif font_name == "ja" or font_name == "zh":
        font_path = font_map.get("MSYH", default_font)
    elif font_name == "ko":
        font_path = font_map.get("Malgun", default_font)
    else:
        font_path = default_font

    if not os.path.exists(font_path):
        logging.warning(f"Font file not found at {font_path}, using system default: {default_font}")
        return default_font
    return font_path

def initialize_paddle_ocr(lang='en'):
    global paddle_ocr
    try:
        if paddle_ocr:
            del paddle_ocr
            paddle_ocr = None
            gc.collect()
        paddle_ocr = PaddleOCR(use_angle_cls=True, lang=lang, use_gpu=False)
        logging.info(f"PaddleOCR initialized successfully for language: {lang}")
    except Exception as e:
        logging.error(f"Failed to initialize PaddleOCR: {e}")
        paddle_ocr = None

def load_window_positions():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load window positions: {e}")
    return {}

def save_window_positions(positions):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(positions, f, indent=4)
        logging.info("Window positions and settings saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save window positions: {e}")

def ensure_support_folder():
    if not os.path.exists(SUPPORT_FOLDER):
        os.makedirs(SUPPORT_FOLDER)
        logging.info(f"Created Support folder at {SUPPORT_FOLDER}")

# Initialize PaddleOCR on startup
initialize_paddle_ocr('en')

class TranslationWorker(QThread):
    translation_complete = pyqtSignal(dict)

    def __init__(self, file_name, source_language, target_language, fonts, improve_translation=False, contrast_factor=1.0, live=False, parent=None):
        super().__init__(parent)
        self.file_name = file_name
        self.source_language = source_language
        self.target_language = target_language
        self.fonts = fonts
        self.improve_translation = improve_translation
        self.contrast_factor = contrast_factor
        self.live = live
        self.is_running = True

    def preprocess_image(self, image):
        if image.width > 1000 or image.height > 1000:
            image = image.resize((int(image.width / 2), int(image.height / 2)))
        image = image.convert('RGB')
        img_array = np.array(image)
        img_array = cv2.convertScaleAbs(img_array, alpha=self.contrast_factor, beta=0)
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        return Image.fromarray(binary)

    def improve_translation_with_ai(self, original_text, translated_text):
        if not ai_api_config["provider"] or not ai_api_config["api_key"]:
            return translated_text
        try:
            prompt = f"Improve this translation for clarity and accuracy:\nOriginal: {original_text}\nInitial Translation: {translated_text}\nTarget Language: {self.target_language}"
            headers = {"Authorization": f"Bearer {ai_api_config['api_key']}"}
            if ai_api_config["provider"] == "OpenAI":
                data = {
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 512,
                    "temperature": 0.7
                }
                response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
            elif ai_api_config["provider"] == "xAI":
                data = {"prompt": prompt, "max_tokens": 512, "temperature": 0.7}
                response = requests.post("https://api.xai.com/v1/completions", headers=headers, json=data)  # Hypothetical endpoint
            elif ai_api_config["provider"] == "LM Studio":
                data = {"prompt": prompt, "max_tokens": 512, "temperature": 0.7}
                response = requests.post("http://localhost:1234/v1/completions", headers=headers, json=data)  # LM Studio local endpoint
            response.raise_for_status()
            result = response.json()
            improved_text = result.get("choices", [{}])[0].get("text", translated_text).strip()
            return improved_text if improved_text else translated_text
        except Exception as e:
            logging.error(f"AI API improvement failed: {e}")
            return translated_text

    def run(self):
        if not self.is_running:
            return
        result = {'original_text': '', 'translated_text': '', 'error_message': '', 'boxes': [], 'live': self.live}
        try:
            if not paddle_ocr:
                raise Exception("PaddleOCR is not initialized. Check installation and dependencies.")

            image = Image.open(self.file_name)
            image = self.preprocess_image(image)
            image_path = self.file_name

            ocr_result = paddle_ocr.ocr(image_path, cls=True)
            if not ocr_result or not ocr_result[0]:
                result['original_text'] = ""
                result['translated_text'] = "No text detected."
                result['boxes'] = []
            else:
                lines = []
                boxes = []
                for line in ocr_result[0]:
                    box = line[0]
                    text = line[1][0]
                    left = min(box[0][0], box[3][0])
                    top = min(box[0][1], box[1][1])
                    right = max(box[1][0], box[2][0])
                    bottom = max(box[2][1], box[3][1])
                    lines.append(text)
                    boxes.append((left, top, right, bottom))
                original_text = '\n'.join(lines)
                result['original_text'] = original_text
                result['boxes'] = boxes

                source_lang = self.source_language if self.source_language != 'auto' else detect(original_text)

                data = {"q": original_text, "source": source_lang, "target": self.target_language, "format": "text"}
                url = "http://127.0.0.1:5000/translate"
                try:
                    response = requests.post(url, data=data, timeout=30)
                    response.raise_for_status()
                    translated_text = response.json().get("translatedText", "Translation failed.")
                except requests.RequestException as e:
                    logging.error(f"LibreTranslate failed: {e}")
                    translated_text = "Translation service unavailable."

                if self.improve_translation:
                    improved_text = self.improve_translation_with_ai(original_text, translated_text)
                    translated_text = improved_text if improved_text else translated_text
                result['translated_text'] = translated_text

        except Exception as e:
            logging.error(f"Translation error: {e}")
            result['error_message'] = str(e)
        finally:
            if self.is_running:
                self.translation_complete.emit(result)
            self.is_running = False

    def stop(self):
        self.is_running = False
        self.quit()
        self.wait()

class LiveTranslationWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Live Translation")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setMinimumSize(300, 100)
        self.setStyleSheet("""
            QDialog {
                background-color: #fefefe;
                border: 2px solid #2980b9;
                border-radius: 10px;
            }
            QLabel {
                color: #111;
                font-size: 18px;
                font-family: Arial, sans-serif;
            }
        """)
        self.initUI()
        self.load_geometry()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        self.translation_label = QLabel("", self)
        self.translation_label.setWordWrap(True)
        self.translation_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.translation_label)
        self.setLayout(layout)

    def updateTranslation(self, text):
        self.translation_label.setText(text.replace('\n', ' ').strip())

    def load_geometry(self):
        positions = load_window_positions()
        if 'LiveTranslationWindow' in positions:
            geo = positions['LiveTranslationWindow']
            self.setGeometry(geo['x'], geo['y'], geo['width'], geo['height'])

    def closeEvent(self, event):
        positions = load_window_positions()
        positions['LiveTranslationWindow'] = {
            'x': self.x(),
            'y': self.y(),
            'width': self.width(),
            'height': self.height()
        }
        save_window_positions(positions)
        event.accept()

class IntroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌟 Welcome to Overlay Translate! 🌟")
        self.setGeometry(100, 100, 450, 450)
        self.setStyleSheet("background-color: #f0f0f0; font-family: Arial;")
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        intro_label = QLabel(
            "👋 **Welcome to Overlay Translate!**\n\n"
            "🚀 Capture and translate screen text offline with ease.\n\n"
            "✨ **Features:**\n"
            "1. 📸 Capture text effortlessly\n"
            "2. 🎥 Real-time live capture\n"
            "3. 🌐 Offline translations\n"
            "4. 🎨 High contrast theme\n"
            "5. 🌎 Multilingual support\n"
            "6. 💾 Save options\n"
            "7. ⏲ Adjustable capture timing\n"
            "8. 💬 Context-aware chat\n"
            "9. 🚨 Enhanced error feedback\n\n"
            "Get started now! 🎉"
        )
        intro_label.setWordWrap(True)
        intro_label.setAlignment(Qt.AlignCenter)
        intro_label.setStyleSheet("font-size: 14px; padding: 10px; color: #2c3e50;")
        close_button = QPushButton("Start Using", self)
        close_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3498db, stop:1 #2980b9);
                color: white; border-radius: 8px; padding: 10px; font-size: 14px;
            }
            QPushButton:hover { background: #2980b9; }
        """)
        close_button.clicked.connect(self.accept)
        layout.addWidget(intro_label)
        layout.addWidget(close_button)
        self.setLayout(layout)

class ControlWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.live_translation_popout = None
        self.chat_window = None
        self.source_language = 'auto'
        self.target_language = 'en'
        self.tray_icon = None
        self.default_font_size = 24
        self.default_font_type = "default"
        self.showIntroDialog()
        self.capture_widget = CaptureWidget(control_window=self)
        self.snipping_tool = SnippingTool(self.capture_widget)
        self.high_contrast_theme_enabled = False
        self.font_size = 20
        self.improve_translation_enabled = False
        self.initUI()
        self.setupGlobalShortcuts()
        self.load_geometry()
        ensure_support_folder()

    def showIntroDialog(self):
        intro_dialog = IntroDialog(self)
        intro_dialog.exec_()

    def initUI(self):
        self.setWindowTitle('Overlay Translate')
        self.setStyleSheet("background-color: #ecf0f1; font-family: Arial;")
        flags = Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint
        self.setWindowFlags(flags)

        self.capture_btn = self.createButton('📸 Capture / Translate (F1)', self.captureScreen, '#3498db', '#2980b9', '#2471a3')
        self.live_capture_btn = self.createButton('🎥 Live Capture', self.toggleLiveCapture, '#3498db', '#2980b9', '#2471a3')
        self.increase_font_btn = self.createButton('🔍 +', self.increaseFontSize, '#2ecc71', '#27ae60', '#229954')
        self.decrease_font_btn = self.createButton('🔍 -', self.decreaseFontSize, '#e74c3c', '#c0392b', '#a93226')
        self.toggle_btn = self.createButton('🔁 Click-Through (F2)', self.capture_widget.toggleClickThrough, '#9b59b6', '#8e44ad', '#7d3c98')
        self.snip_btn = self.createButton('✂️ Snip (F4)', self.activateSnippingTool, '#16a085', '#138d75', '#117a65')

        slider_style = """
            QSlider::groove:horizontal {
                height: 8px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #bdc3c7, stop:1 #ecf0f1);
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #3498db; width: 16px; height: 16px; border-radius: 8px; margin: -4px 0;
            }
            QSlider::sub-page:horizontal { background: #3498db; }
        """
        self.opacity_slider = QSlider(Qt.Horizontal, self)
        self.opacity_slider.setRange(1, 100)
        self.opacity_slider.setValue(10)
        self.opacity_slider.setStyleSheet(slider_style)
        self.opacity_slider.valueChanged.connect(self.adjustCaptureWidgetOpacity)

        self.threshold_slider = QSlider(Qt.Horizontal, self)
        self.threshold_slider.setRange(0, 50)
        self.threshold_slider.setValue(5)
        self.threshold_slider.setStyleSheet(slider_style)
        self.threshold_slider.valueChanged.connect(self.updateThreshold)

        self.contrast_slider = QSlider(Qt.Horizontal, self)
        self.contrast_slider.setRange(5, 20)
        self.contrast_slider.setValue(10)
        self.contrast_slider.setStyleSheet(slider_style)
        self.contrast_slider.valueChanged.connect(self.updateContrast)

        self.live_translation_label = QLabel("Live translation will appear here...", self)
        self.live_translation_label.setWordWrap(True)
        self.live_translation_label.setAlignment(Qt.AlignCenter)
        self.live_translation_label.setStyleSheet(f"background: #ffffff; border: 2px solid #3498db; border-radius: 5px; padding: 10px; font-size: {self.font_size}px; color: #2c3e50;")
        self.live_translation_label.setVisible(False)

        self.label_opacity_effect = QGraphicsOpacityEffect(self.live_translation_label)
        self.live_translation_label.setGraphicsEffect(self.label_opacity_effect)

        self.label_fade_anim = QPropertyAnimation(self.label_opacity_effect, b"opacity")
        self.label_fade_anim.setDuration(500)
        self.label_fade_anim.setStartValue(0.0)
        self.label_fade_anim.setEndValue(1.0)

        self.translation_progress_bar = QProgressBar(self)
        self.translation_progress_bar.setMaximum(100)
        self.translation_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #3498db; border-radius: 5px; text-align: center; background: #ecf0f1; color: #2c3e50;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3498db, stop:1 #2980b9);
            }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        capture_group = QGroupBox("Capture Controls")
        capture_group.setStyleSheet("QGroupBox { font-size: 16px; color: #2c3e50; }")
        capture_layout = QVBoxLayout()
        capture_layout.addWidget(self.capture_btn)
        capture_layout.addWidget(self.live_capture_btn)
        capture_layout.addWidget(self.snip_btn)
        capture_group.setLayout(capture_layout)
        main_layout.addWidget(capture_group)

        main_layout.addWidget(self.live_translation_label)

        font_group = QGroupBox("Font Size (Live Translation)")
        font_group.setStyleSheet("QGroupBox { font-size: 16px; color: #2c3e50; }")
        font_layout = QHBoxLayout()
        font_layout.addWidget(self.increase_font_btn)
        font_layout.addWidget(self.decrease_font_btn)
        font_group.setLayout(font_layout)
        main_layout.addWidget(font_group)

        settings_group = QGroupBox("Settings")
        settings_group.setStyleSheet("QGroupBox { font-size: 16px; color: #2c3e50; }")
        settings_layout = QVBoxLayout()
        settings_layout.addWidget(self.toggle_btn)
        settings_layout.addWidget(QLabel("Opacity:", self))
        settings_layout.addWidget(self.opacity_slider)
        settings_layout.addWidget(QLabel("Word-Line Threshold:", self))
        settings_layout.addWidget(self.threshold_slider)
        settings_layout.addWidget(QLabel("OCR Contrast:", self))
        settings_layout.addWidget(self.contrast_slider)
        self.improve_translation_toggle = QPushButton('🔄 Improve Translation: OFF', self)
        self.improve_translation_toggle.setCheckable(True)
        self.improve_translation_toggle.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e74c3c, stop:1 #c0392b);
                color: white; border-radius: 8px; padding: 12px; font-size: 14px;
            }
            QPushButton:checked { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2ecc71, stop:1 #27ae60); }
            QPushButton:hover { opacity: 0.9; }
        """)
        self.improve_translation_toggle.clicked.connect(self.toggleImproveTranslation)
        settings_layout.addWidget(self.improve_translation_toggle)
        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)

        main_layout.addWidget(self.translation_progress_bar)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.setMenuBar(self.createMenuBar())

        self.capture_widget.show()
        self.live_capture_timer = QTimer(self)
        self.live_capture_timer.timeout.connect(self.captureScreenForLiveTranslation)
        self.live_capture_timer.setInterval(1000)
        self.initTrayIcon()

        positions = load_window_positions()
        if 'font_settings' in positions:
            self.default_font_size = positions['font_settings'].get('size', 24)
            self.default_font_type = positions['font_settings'].get('type', 'default')
            self.capture_widget.default_font_size = self.default_font_size
            self.capture_widget.default_font_type = self.default_font_type
        if 'ai_api_config' in positions:
            global ai_api_config
            ai_api_config = positions['ai_api_config']

    def createMenuBar(self):
        menu_bar = QtWidgets.QMenuBar(self)
        file_menu = menu_bar.addMenu("File")
        file_menu.addAction("Minimize to Tray", self.minimizeToTray)
        file_menu.addAction("Exit", self.closeApplication)
        settings_menu = menu_bar.addMenu("Settings")
        settings_menu.addAction("Source Language", self.selectSourceLanguage)
        settings_menu.addAction("Target Language", self.selectTargetLanguage)
        settings_menu.addAction("Theme", self.toggleHighContrastTheme)
        settings_menu.addAction("Server", self.openServer)
        settings_menu.addAction("Toggle Improved Translation", self.toggleImproveTranslation)
        settings_menu.addAction("Set Default Font Size", self.setDefaultFontSize)
        settings_menu.addAction("Set Default Font Type", self.setDefaultFontType)
        settings_menu.addAction("Configure AI API", self.configureAIAPI)
        tools_menu = menu_bar.addMenu("Tools")
        tools_menu.addAction("Chat with AI", self.openChatWindow)
        tools_menu.addAction("Pop Out Live Translation", self.popOutLiveTranslation)
        return menu_bar

    def createButton(self, text, callback, color, hover, pressed):
        button = QPushButton(text, self)
        button.clicked.connect(callback)
        button.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {color}, stop:1 {hover});
                color: white; border-radius: 8px; padding: 12px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton:pressed {{ background: {pressed}; }}
        """)
        return button

    def updateThreshold(self, value):
        self.capture_widget.threshold = value

    def updateContrast(self, value):
        contrast_factor = value / 10.0
        self.capture_widget.contrast_factor = contrast_factor
        logging.debug(f"Contrast factor updated to: {contrast_factor}")

    def toggleImproveTranslation(self):
        self.improve_translation_enabled = not self.improve_translation_enabled
        self.improve_translation_toggle.setText(
            '🔄 Improve Translation: ON' if self.improve_translation_enabled else '🔄 Improve Translation: OFF'
        )
        if self.improve_translation_enabled and not ai_api_config["provider"]:
            QMessageBox.warning(self, "Warning", "No AI API configured. Please configure it from Settings > Configure AI API.")
        elif self.improve_translation_enabled and self.live_capture_timer.isActive():
            QMessageBox.warning(self, "Warning", "Improved translations may cause performance issues during live capture.")

    def toggleLiveCapture(self):
        if self.live_capture_timer.isActive():
            self.live_capture_timer.stop()
            if not (self.live_translation_popout and self.live_translation_popout.isVisible()):
                self.live_translation_label.setVisible(False)
            self.live_capture_btn.setText('🎥 Live Capture')
            if self.improve_translation_enabled:
                self.improve_translation_enabled = False
                self.improve_translation_toggle.setText('🔄 Improve Translation: OFF')
                QMessageBox.information(self, "Info", "Improved translations disabled during live capture.")
        else:
            if self.improve_translation_enabled:
                reply = QMessageBox.question(self, "Warning", "Improved translations may cause instability during live capture. Continue?", QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No:
                    self.improve_translation_enabled = False
                    self.improve_translation_toggle.setText('🔄 Improve Translation: OFF')
            self.live_capture_timer.start()
            if not (self.live_translation_popout and self.live_translation_popout.isVisible()):
                self.live_translation_label.setVisible(True)
            self.live_capture_btn.setText('🛑 Stop Live Capture')

    def captureScreen(self):
        try:
            rect = self.capture_widget.rect()
            screen = QApplication.primaryScreen()
            screenshot = screen.grabWindow(0, self.capture_widget.x(), self.capture_widget.y(), rect.width(), rect.height())
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            fileName = os.path.join(SUPPORT_FOLDER, f"capture_{timestamp}.png")
            screenshot.save(fileName, format='PNG', quality=95)
            self.capture_widget.current_capture_path = fileName
            self.capture_widget.translateAndDisplay(fileName)
        except Exception as e:
            logging.error(f"Capture failed: {e}")
            QMessageBox.critical(self.capture_widget, "Error", f"Capture failed: {e}")

    def captureScreenForLiveTranslation(self):
        rect = self.capture_widget.rect()
        screen = QApplication.primaryScreen()
        screenshot = screen.grabWindow(0, self.capture_widget.x(), self.capture_widget.y(), rect.width(), rect.height())
        tempFile = os.path.join(self.capture_widget.tempDir, 'live_capture.png')
        screenshot.save(tempFile, format='PNG', quality=95)
        self.startTranslationWorker(tempFile, live=True)

    def startTranslationWorker(self, fileName, live=False):
        improve_translation = self.improve_translation_enabled and not live
        contrast_factor = self.capture_widget.contrast_factor
        self.translation_worker = TranslationWorker(fileName, self.source_language, self.target_language, self.capture_widget.fonts, improve_translation, contrast_factor, live, self)
        if live:
            self.translation_worker.translation_complete.connect(self.updateLiveTranslation)
        else:
            self.translation_worker.translation_complete.connect(self.capture_widget.displayTranslatedImage)
            self.translation_worker.finished.connect(lambda: self.translation_progress_bar.setValue(100))
        self.translation_worker.start()

    def updateLiveTranslation(self, result):
        if result['error_message']:
            logging.error(result['error_message'])
            self.live_translation_label.setText(f"Error: {result['error_message']}")
        else:
            compact_text = result['translated_text'].replace('\n', ' ')
            if self.live_translation_popout and self.live_translation_popout.isVisible():
                self.live_translation_popout.updateTranslation(compact_text)
            else:
                self.live_translation_label.setText(compact_text)
                self.label_fade_anim.start()

    def initTrayIcon(self):
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.png")
        if os.path.exists(icon_path):
            self.tray_icon = QSystemTrayIcon(QtGui.QIcon(icon_path), self)
            tray_menu = QMenu()
            tray_menu.addAction("Restore", self.restoreFromTray)
            tray_menu.addAction("Exit", self.closeApplication)
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.show()
            self.tray_icon.activated.connect(self.trayIconActivated)
        else:
            logging.warning(f"Tray icon not found at {icon_path}")

    def trayIconActivated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.restoreFromTray()

    def minimizeToTray(self):
        self.hide()
        if self.tray_icon:
            self.tray_icon.showMessage(
                "Overlay Translate",
                "The app is still running in the system tray.",
                QSystemTrayIcon.Information,
                2000
            )

    def restoreFromTray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def adjustCaptureWidgetOpacity(self, value):
        opacity = value / 100.0
        self.capture_widget.setWindowOpacity(opacity)

    def setupGlobalShortcuts(self):
        QShortcut(QKeySequence("F1"), self, activated=self.captureScreen)
        QShortcut(QKeySequence("F2"), self, activated=self.capture_widget.toggleClickThrough)
        QShortcut(QKeySequence("F3"), self, activated=self.selectSourceLanguage)
        QShortcut(QKeySequence("F4"), self, activated=self.activateSnippingTool)
        QShortcut(QKeySequence("F5"), self, activated=self.toggleHighContrastTheme)
        QShortcut(QKeySequence("F6"), self, activated=self.openServer)
        QShortcut(QKeySequence("F7"), self, activated=self.closeApplication)
        QShortcut(QKeySequence("F8"), self, activated=self.toggleImproveTranslation)

    def selectSourceLanguage(self):
        source_languages = {
            "Auto Detect": "auto",
            "English": "en",
            "Chinese (Simplified)": "ch",
            "Chinese (Traditional)": "ch_tra",
            "French": "fr",
            "German": "german",
            "Japanese": "japan",
            "Korean": "korean",
            "Spanish": "es",
            "Portuguese": "pt",
            "Italian": "it",
            "Russian": "ru",
            "Arabic": "ar",
            "Hindi": "hi",
            "Uyghur": "ug",
            "Persian": "fa",
            "Urdu": "ur",
            "Serbian (Latin)": "rs_latin",
            "Serbian (Cyrillic)": "rs_cyrillic",
            "Marathi": "mr",
            "Tamil": "ta",
            "Telugu": "te",
            "Kannada": "ka",
            "Malayalam": "ml",
            "Bangla": "bn",
            "Thai": "th",
            "Vietnamese": "vi",
            "Afrikaans": "af",
            "Albanian": "sq",
            "Amharic": "am",
            "Azerbaijani": "az",
            "Basque": "eu",
            "Belarusian": "be",
            "Bulgarian": "bg",
            "Burmese": "my",
            "Catalan": "ca",
            "Cebuano": "ceb",
            "Chichewa": "ny",
            "Corsican": "co",
            "Croatian": "hr",
            "Czech": "cs",
            "Danish": "da",
            "Dutch": "nl",
            "Esperanto": "eo",
            "Estonian": "et",
            "Filipino": "tl",
            "Finnish": "fi",
            "Galician": "gl",
            "Georgian": "ka",
            "Greek": "el",
            "Gujarati": "gu",
            "Haitian Creole": "ht",
            "Hausa": "ha",
            "Hawaiian": "haw",
            "Hebrew": "he",
            "Hmong": "hmn",
            "Hungarian": "hu",
            "Icelandic": "is",
            "Igbo": "ig",
            "Indonesian": "id",
            "Irish": "ga",
            "Javanese": "jv",
            "Kazakh": "kk",
            "Khmer": "km",
            "Kurdish": "ku",
            "Kyrgyz": "ky",
            "Lao": "lo",
            "Latin": "la",
            "Latvian": "lv",
            "Lithuanian": "lt",
            "Luxembourgish": "lb",
            "Macedonian": "mk",
            "Malagasy": "mg",
            "Malay": "ms",
            "Maltese": "mt",
            "Maori": "mi",
            "Mongolian": "mn",
            "Nepali": "ne",
            "Norwegian": "no",
            "Pashto": "ps",
            "Polish": "pl",
            "Punjabi": "pa",
            "Romanian": "ro",
            "Samoan": "sm",
            "Scottish Gaelic": "gd",
            "Sesotho": "st",
            "Shona": "sn",
            "Sindhi": "sd",
            "Sinhala": "si",
            "Slovak": "sk",
            "Slovenian": "sl",
            "Somali": "so",
            "Sundanese": "su",
            "Swahili": "sw",
            "Swedish": "sv",
            "Tajik": "tg",
            "Turkish": "tr",
            "Turkmen": "tk",
            "Ukrainian": "uk",
            "Uzbek": "uz",
            "Welsh": "cy",
            "Xhosa": "xh",
            "Yiddish": "yi",
            "Yoruba": "yo",
            "Zulu": "zu",
        }
        lang, ok = QInputDialog.getItem(self, "Select Source Language", "Choose the language to detect:", sorted(source_languages.keys()), 0, False)
        if ok and lang:
            self.source_language = source_languages[lang]
            if self.source_language != 'auto':
                initialize_paddle_ocr(self.source_language)
            else:
                initialize_paddle_ocr('en')
            logging.info(f"Source language set to: {self.source_language}")

    def selectTargetLanguage(self):
        target_languages = {
            "English": "en",
            "Spanish": "es",
            "French": "fr",
            "German": "de",
            "Italian": "it",
            "Portuguese": "pt",
            "Russian": "ru",
            "Chinese (Simplified)": "zh-cn",
            "Japanese": "ja",
            "Korean": "ko",
        }
        lang, ok = QInputDialog.getItem(self, "Select Target Language", "Choose the language to translate to:", sorted(target_languages.keys()), 0, False)
        if ok and lang:
            self.target_language = target_languages[lang]
            self.capture_widget.target_language = self.target_language
            logging.info(f"Target language set to: {self.target_language}")

    def openServer(self):
        webbrowser.open('http://127.0.0.1:5000/')

    def closeApplication(self):
        reply = QMessageBox.question(self, 'Message', 
                                     "Are you sure to quit? Exiting will delete the 'Support' folder on your Desktop containing all captures.",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.finalCleanup()
            QApplication.quit()

    def finalCleanup(self):
        positions = load_window_positions()
        positions['ControlWindow'] = {
            'x': self.x(),
            'y': self.y(),
            'width': self.width(),
            'height': self.height()
        }
        if self.live_translation_popout and self.live_translation_popout.isVisible():
            positions['LiveTranslationWindow'] = {
                'x': self.live_translation_popout.x(),
                'y': self.live_translation_popout.y(),
                'width': self.live_translation_popout.width(),
                'height': self.live_translation_popout.height()
            }
        if self.chat_window and self.chat_window.isVisible():
            positions['ChatWindow'] = {
                'x': self.chat_window.x(),
                'y': self.chat_window.y(),
                'width': self.chat_window.width(),
                'height': self.chat_window.height()
            }
        positions['CaptureWidget'] = {
            'x': self.capture_widget.x(),
            'y': self.capture_widget.y(),
            'width': self.capture_widget.width(),
            'height': self.capture_widget.height()
        }
        positions['font_settings'] = {
            'size': self.default_font_size,
            'type': self.default_font_type
        }
        positions['ai_api_config'] = ai_api_config
        save_window_positions(positions)

        if hasattr(self, 'translation_worker') and self.translation_worker.isRunning():
            self.translation_worker.stop()
        if self.chat_window and self.chat_window.isVisible():
            self.chat_window.close()
        if self.live_translation_popout and self.live_translation_popout.isVisible():
            self.live_translation_popout.close()
        self.capture_widget.cleanup()
        self.capture_widget.close()
        if self.tray_icon:
            self.tray_icon.hide()
        if os.path.exists(SUPPORT_FOLDER):
            shutil.rmtree(SUPPORT_FOLDER, ignore_errors=True)
            logging.info(f"Deleted Support folder at {SUPPORT_FOLDER}")

    def load_geometry(self):
        positions = load_window_positions()
        if 'ControlWindow' in positions:
            geometry = positions['ControlWindow']
            self.setGeometry(geometry['x'], geometry['y'], geometry['width'], geometry['height'])

    def closeEvent(self, event):
        event.ignore()
        self.minimizeToTray()

    def toggleHighContrastTheme(self):
        self.high_contrast_theme_enabled = not self.high_contrast_theme_enabled
        self.setStyleSheet("background: black; color: white;" if self.high_contrast_theme_enabled else "background-color: #ecf0f1; font-family: Arial;")
        self.live_translation_label.setStyleSheet(
            f"background: {'#333' if self.high_contrast_theme_enabled else '#ffffff'}; border: 2px solid #3498db; border-radius: 5px; padding: 10px; font-size: {self.font_size}px; color: {'#fff' if self.high_contrast_theme_enabled else '#2c3e50'};"
        )

    def activateSnippingTool(self):
        self.capture_widget.hide()
        self.snipping_tool.show()

    def openChatWindow(self):
        self.chat_window = ChatWindow(self.capture_widget.original_text, self.capture_widget.translated_text, self)
        self.chat_window.show()

    def increaseFontSize(self):
        self.font_size += 2
        self.live_translation_label.setStyleSheet(f"background: #ffffff; border: 2px solid #3498db; border-radius: 5px; padding: 10px; font-size: {self.font_size}px; color: #2c3e50;")

    def decreaseFontSize(self):
        if self.font_size > 10:
            self.font_size -= 2
            self.live_translation_label.setStyleSheet(f"background: #ffffff; border: 2px solid #3498db; border-radius: 5px; padding: 10px; font-size: {self.font_size}px; color: #2c3e50;")

    def popOutLiveTranslation(self):
        if self.live_translation_popout is None or not self.live_translation_popout.isVisible():
            self.live_translation_popout = LiveTranslationWindow(self)
            self.live_translation_popout.updateTranslation(self.live_translation_label.text())
            self.live_translation_popout.show()
            self.live_translation_label.setVisible(False)
        else:
            self.live_translation_popout.close()
            self.live_translation_popout = None
            self.live_translation_label.setVisible(True)

    def configureAIAPI(self):
        global ai_api_config  # Declarar global al inicio
        providers = ["OpenAI (ChatGPT)", "xAI (Grok)", "LM Studio (Local)"]
        provider, ok = QInputDialog.getItem(self, "Select AI Provider", "Choose your AI provider:", providers, 0, False)
        if ok and provider:
            api_key, ok = QInputDialog.getText(self, "Enter API Key", f"Enter your {provider} API Key:", QLineEdit.Normal, ai_api_config["api_key"] or "")
            if ok:
                if provider == "OpenAI (ChatGPT)":
                    ai_api_config = {"provider": "OpenAI", "api_key": api_key, "endpoint": "https://api.openai.com/v1/chat/completions"}
                elif provider == "xAI (Grok)":
                    ai_api_config = {"provider": "xAI", "api_key": api_key, "endpoint": "https://api.xai.com/v1/completions"}
                elif provider == "LM Studio (Local)":
                    ai_api_config = {"provider": "LM Studio", "api_key": api_key, "endpoint": "http://localhost:1234/v1/completions"}
                logging.info(f"AI API configured: {provider}")
                QMessageBox.information(self, "Success", f"{provider} API configured successfully.")
                self.saveAPISettings()

    def saveAPISettings(self):
            positions = load_window_positions()
            positions['ai_api_config'] = ai_api_config
            save_window_positions(positions)

    def setDefaultFontSize(self):
        size, ok = QInputDialog.getInt(self, "Set Default Font Size", "Enter font size (10-100):", self.default_font_size, 10, 100)
        if ok:
            self.default_font_size = size
            self.capture_widget.default_font_size = size
            logging.info(f"Default font size set to: {size}")
            self.saveFontSettings()

    def setDefaultFontType(self):
        font_options = {
            "Arial (Default)": "default",
            "MS YaHei (Chinese/Japanese)": "zh",
            "Malgun Gothic (Korean)": "ko"
        }
        font, ok = QInputDialog.getItem(self, "Set Default Font Type", "Choose the font for translated text:", sorted(font_options.keys()), 0, False)
        if ok and font:
            self.default_font_type = font_options[font]
            self.capture_widget.default_font_type = self.default_font_type
            logging.info(f"Default font type set to: {self.default_font_type}")
            self.saveFontSettings()

    def saveFontSettings(self):
        positions = load_window_positions()
        positions['font_settings'] = {
            'size': self.default_font_size,
            'type': self.default_font_type
        }
        save_window_positions(positions)

class CaptureWidget(QWidget):
    def __init__(self, parent=None, control_window=None):
        super().__init__(parent)
        self.control_window = control_window
        self.target_language = 'en'
        self.fonts = {
            "default": get_system_font_path("default"),
            "ja": get_system_font_path("ja"),
            "zh": get_system_font_path("zh"),
            "ko": get_system_font_path("ko")
        }
        self.threshold = 5
        self.contrast_factor = 1.0
        self.tempDir = tempfile.mkdtemp(prefix="OverlayTranslate_")
        self.original_text = ""
        self.translated_text = ""
        self.current_capture_path = ""
        self.current_translation_path = ""
        self.resizing = False
        self.borderRadius = 20
        self.translation_worker = None
        self.default_font_size = 24
        self.default_font_type = "default"
        self.initUI()
        self.start_libretranslate_server()
        self.load_geometry()

    def initUI(self):
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.show()

    def start_libretranslate_server(self):
        try:
            self.libretranslate_process = subprocess.Popen(["libretranslate"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(1)
            if self.libretranslate_process.poll() is not None:
                raise Exception("LibreTranslate failed to start.")
            logging.info("LibreTranslate server started.")
        except Exception as e:
            logging.error(f"Failed to start LibreTranslate: {e}")
            QMessageBox.critical(self, "Error", f"Start LibreTranslate manually: {e}")

    def cleanup(self):
        if hasattr(self, 'libretranslate_process') and self.libretranslate_process:
            self.libretranslate_process.terminate()
        if self.translation_worker and self.translation_worker.isRunning():
            self.translation_worker.stop()
        if os.path.exists(self.tempDir):
            shutil.rmtree(self.tempDir, ignore_errors=True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setOpacity(0.1)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 10, 10)
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 10, 10)
        painter.setBrush(QBrush(QColor(0, 0, 0)))
        painter.drawRect(self.width() - self.borderRadius, self.height() - self.borderRadius, self.borderRadius, self.borderRadius)

    def captureScreen(self):
        try:
            rect = self.rect()
            screen = QApplication.primaryScreen()
            screenshot = screen.grabWindow(0, self.x(), self.y(), rect.width(), rect.height())
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            fileName = os.path.join(SUPPORT_FOLDER, f"capture_{timestamp}.png")
            screenshot.save(fileName, format='PNG', quality=95)
            self.current_capture_path = fileName
            self.translateAndDisplay(fileName)
        except Exception as e:
            logging.error(f"Capture failed: {e}")
            QMessageBox.critical(self, "Error", f"Capture failed: {e}")

    def translateAndDisplay(self, fileName, live=False):
        if not live:
            self.control_window.translation_progress_bar.setValue(10)
        self.startTranslationWorker(fileName, live)

    def startTranslationWorker(self, fileName, live):
        if self.translation_worker and self.translation_worker.isRunning():
            self.translation_worker.stop()
        improve_translation = self.control_window.improve_translation_enabled and not live
        contrast_factor = self.contrast_factor
        self.translation_worker = TranslationWorker(fileName, self.control_window.source_language, self.target_language, self.fonts, improve_translation, contrast_factor, live, self)
        if live:
            self.translation_worker.translation_complete.connect(self.control_window.updateLiveTranslation)
        else:
            self.translation_worker.translation_complete.connect(self.displayTranslatedImage)
            self.translation_worker.finished.connect(lambda: self.control_window.translation_progress_bar.setValue(100))
        self.translation_worker.start()

    def displayTranslatedImage(self, result):
        if result['error_message']:
            QMessageBox.critical(self, "Error", result['error_message'])
            return

        self.original_text = result['original_text']
        self.translated_text = result['translated_text']
        live = result['live']
        fileName = self.translation_worker.file_name
        image = Image.open(fileName).convert("RGBA")
        draw = ImageDraw.Draw(image)

        boxes = result['boxes']
        translated_lines = self.translated_text.split('\n')

        if not live:
            timestamp = os.path.basename(fileName).replace("capture_", "").replace(".png", "")
            text_file = os.path.join(SUPPORT_FOLDER, f"text_{timestamp}.txt")
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(f"Original Text:\n{self.original_text}\n\nTranslated Text:\n{self.translated_text}")

        if not boxes:
            font = ImageFont.truetype(self.fonts[self.default_font_type], self.default_font_size)
            full_text = "No text detected."
            text_bbox = font.getbbox(full_text)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            text_x = (image.width - text_width) / 2
            text_y = (image.height - text_height) / 2
            gradient = Image.new('RGBA', (text_width + 20, text_height + 20), (0, 0, 0, 0))
            gradient_draw = ImageDraw.Draw(gradient)
            gradient_draw.rectangle([(0, 0), (text_width + 20, text_height + 20)], fill=(255, 255, 255, 220))
            gradient_draw.rectangle([(5, 5), (text_width + 15, text_height + 15)], fill=(180, 200, 255, 180))
            image.paste(gradient, (int(text_x - 10), int(text_y - 10)), gradient)
            draw.text((text_x, text_y), full_text, font=font, fill=(0, 0, 255, 255))
        else:
            for i, bbox in enumerate(boxes):
                if i >= len(translated_lines):
                    break
                translated_line = translated_lines[i].strip()

                font_size = self.default_font_size
                try:
                    font = ImageFont.truetype(self.fonts[self.default_font_type], font_size)
                except Exception as e:
                    logging.error(f"Font loading failed: {e}, using default")
                    font = ImageFont.truetype("arial.ttf", font_size)

                text_x = bbox[0]
                text_y = bbox[1]
                text_bbox = font.getbbox(translated_line)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]

                gradient = Image.new('RGBA', (int(bbox[2] - bbox[0] + 20), int(bbox[3] - bbox[1] + 20)), (0, 0, 0, 0))
                gradient_draw = ImageDraw.Draw(gradient)
                gradient_draw.rectangle([(0, 0), (bbox[2] - bbox[0] + 20, bbox[3] - bbox[1] + 20)], 
                                       fill=(255, 255, 255, 220))
                gradient_draw.rectangle([(5, 5), (bbox[2] - bbox[0] + 15, bbox[3] - bbox[1] + 15)], 
                                       fill=(180, 200, 255, 180))
                image.paste(gradient, (int(bbox[0] - 10), int(bbox[1] - 10)), gradient)

                draw.text((text_x, text_y), translated_line, font=font, fill=(0, 0, 255, 255))

        translated_file_path = fileName.replace('capture_', 'translated_')
        image.save(translated_file_path, format='PNG', quality=95)
        self.current_translation_path = translated_file_path
        if not live:
            shutil.move(translated_file_path, os.path.join(SUPPORT_FOLDER, os.path.basename(translated_file_path)))
            self.current_translation_path = os.path.join(SUPPORT_FOLDER, os.path.basename(translated_file_path))
        image.show()

    def toggleClickThrough(self):
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowTransparentForInput)
        self.show()

    def mousePressEvent(self, event):
        self.oldPos = event.globalPos()
        self.resizing = self.is_on_border(event.pos())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if self.resizing:
                newWidth = max(event.x(), 100)
                newHeight = max(event.y(), 100)
                self.resize(newWidth, newHeight)
            else:
                delta = QPoint(event.globalPos() - self.oldPos)
                self.move(self.x() + delta.x(), self.y() + delta.y())
                self.oldPos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self.resizing = False

    def is_on_border(self, pos):
        return (
            pos.x() >= self.width() - self.borderRadius and
            pos.y() >= self.height() - self.borderRadius
        )

    def load_geometry(self):
        positions = load_window_positions()
        if 'CaptureWidget' in positions:
            geometry = positions['CaptureWidget']
            self.setGeometry(geometry['x'], geometry['y'], geometry['width'], geometry['height'])

    def closeEvent(self, event):
        positions = load_window_positions()
        positions['CaptureWidget'] = {
            'x': self.x(),
            'y': self.y(),
            'width': self.width(),
            'height': self.height()
        }
        save_window_positions(positions)
        if self.translation_worker and self.translation_worker.isRunning():
            self.translation_worker.stop()
        event.accept()

class SnippingTool(QWidget):
    def __init__(self, capture_widget):
        super().__init__()
        self.capture_widget = capture_widget
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setGeometry(QApplication.primaryScreen().geometry())
        self.setWindowOpacity(0.3)
        self.begin = QPoint()
        self.end = QPoint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(QColor('goldenrod'), 3))
        painter.setBrush(QColor(0, 255, 0, 128))
        painter.drawRect(QRect(self.begin, self.end))

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.end = self.begin
        self.update()

    def mouseMoveEvent(self, event):
        self.end = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        rect = QRect(self.begin, self.end).normalized()
        screen = QApplication.primaryScreen()
        screenshot = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        fileName = os.path.join(SUPPORT_FOLDER, f"snip_{timestamp}.png")
        screenshot.save(fileName, format='PNG', quality=95)
        self.capture_widget.translateAndDisplay(fileName)
        self.capture_widget.show()
        self.hide()

class ChatWindow(QDialog):
    def __init__(self, original_text, translated_text, parent=None):
        super().__init__(parent)
        self.original_text = original_text
        self.translated_text = translated_text
        self.parent = parent
        self.font_size = 14
        self.setWindowTitle("Chat with AI")
        self.initUI()
        self.load_geometry()

    def initUI(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #000000;
                border: 2px solid #00FF00;
                border-radius: 5px;
            }
        """)
        layout = QVBoxLayout()
        
        self.chat_history = QTextEdit(self)
        self.chat_history.setReadOnly(True)
        self.update_chat_history_style()
        self.chat_history.setTextColor(QtGui.QColor(0, 255, 0))

        font_size_layout = QHBoxLayout()
        self.increase_font_btn = QPushButton("+", self)
        self.decrease_font_btn = QPushButton("-", self)
        self.increase_font_btn.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                color: #00FF00;
                font-family: 'Courier New', 'Consolas', monospace;
                font-size: 14px;
                border: 1px solid #00FF00;
                border-radius: 0;
                padding: 5px 10px;
                min-width: 40px;
            }
            QPushButton:hover { background-color: #003300; }
            QPushButton:pressed { background-color: #002200; }
        """)
        self.decrease_font_btn.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                color: #00FF00;
                font-family: 'Courier New', 'Consolas', monospace;
                font-size: 14px;
                border: 1px solid #00FF00;
                border-radius: 0;
                padding: 5px 10px;
                min-width: 40px;
            }
            QPushButton:hover { background-color: #003300; }
            QPushButton:pressed { background-color: #002200; }
        """)
        self.increase_font_btn.clicked.connect(self.increaseFontSize)
        self.decrease_font_btn.clicked.connect(self.decreaseFontSize)
        font_size_layout.addWidget(self.increase_font_btn)
        font_size_layout.addWidget(self.decrease_font_btn)

        self.user_input = QLineEdit(self)
        self.update_user_input_style()

        self.send_btn = QPushButton(">", self)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #000000;
                color: #00FF00;
                font-family: 'Courier New', 'Consolas', monospace;
                font-size: 14px;
                border: 1px solid #00FF00;
                border-radius: 0;
                padding: 5px 10px;
                min-width: 40px;
            }
            QPushButton:hover { background-color: #003300; }
            QPushButton:pressed { background-color: #002200; }
        """)
        self.send_btn.clicked.connect(self.sendMessage)

        self.user_input.returnPressed.connect(self.sendMessage)

        layout.addWidget(self.chat_history)
        layout.addLayout(font_size_layout)
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.user_input)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)
        self.setLayout(layout)

    def update_chat_history_style(self):
        self.chat_history.setStyleSheet(f"""
            QTextEdit {{
                background-color: #000000;
                color: #00FF00;
                font-family: 'Courier New', 'Consolas', monospace;
                font-size: {self.font_size}px;
                border: none;
                padding: 10px;
            }}
        """)

    def update_user_input_style(self):
        self.user_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #000000;
                color: #00FF00;
                font-family: 'Courier New', 'Consolas', monospace;
                font-size: {self.font_size}px;
                border: 1px solid #00FF00;
                border-radius: 0;
                padding: 5px;
            }}
            QLineEdit:focus {{ border: 2px solid #00FF00; }}
        """)

    def sendMessage(self):
        user_message = self.user_input.text().strip()
        if user_message:
            self.chat_history.append(f"You: {user_message}")
            self.chat_history.append("")
            self.user_input.clear()
            self.send_btn.setEnabled(False)
            self.start_streaming_response(user_message)

    def start_streaming_response(self, message):
        if not ai_api_config["provider"] or not ai_api_config["api_key"]:
            self.chat_history.append("AI: Error: No AI API configured. Please configure it from Settings > Configure AI API.")
            self.send_btn.setEnabled(True)
            return
        self.worker = AIStreamingWorker(message, self.original_text, self.translated_text, self.parent.source_language, self.parent.target_language)
        self.worker.text_chunk.connect(self.update_chat_history_in_real_time)
        self.worker.finished.connect(self.on_streaming_finished)
        self.worker.start()

    def update_chat_history_in_real_time(self, chunk):
        current_text = self.chat_history.toPlainText()
        if current_text.endswith("You: ") or current_text.endswith("\n"):
            new_text = current_text + "AI: " + chunk
        else:
            new_text = current_text + chunk
        self.chat_history.setText(new_text)
        self.chat_history.moveCursor(QtGui.QTextCursor.End)

    def on_streaming_finished(self, final_text):
        if not final_text.startswith("Error:"):
            self.chat_history.append("")
        self.send_btn.setEnabled(True)

    def increaseFontSize(self):
        if self.font_size < 24:
            self.font_size += 2
            self.update_chat_history_style()
            self.update_user_input_style()

    def decreaseFontSize(self):
        if self.font_size > 8:
            self.font_size -= 2
            self.update_chat_history_style()
            self.update_user_input_style()

    def load_geometry(self):
        positions = load_window_positions()
        if 'ChatWindow' in positions:
            geometry = positions['ChatWindow']
            self.setGeometry(geometry['x'], geometry['y'], geometry['width'], geometry['height'])

    def closeEvent(self, event):
        positions = load_window_positions()
        positions['ChatWindow'] = {
            'x': self.x(),
            'y': self.y(),
            'width': self.width(),
            'height': self.height()
        }
        save_window_positions(positions)
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
        event.accept()

class AIStreamingWorker(QThread):
    text_chunk = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, message, original_text, translated_text, source_language, target_language, parent=None):
        super().__init__(parent)
        self.message = message
        self.original_text = original_text
        self.translated_text = translated_text
        self.source_language = source_language
        self.target_language = target_language
        self.is_running = True

    def run(self):
        if not self.is_running or not ai_api_config["provider"]:
            self.finished.emit("Error: No AI API configured.")
            return
        try:
            prompt = f"Context: Original: {self.original_text}\nTranslated: {self.translated_text}\n\nUser: {self.message}\nProvide a helpful and concise response in {self.target_language}."
            headers = {"Authorization": f"Bearer {ai_api_config['api_key']}"}
            if ai_api_config["provider"] == "OpenAI":
                data = {
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 150,
                    "temperature": 0.7,
                    "stream": True
                }
                response = requests.post(ai_api_config["endpoint"], headers=headers, json=data, stream=True)
            elif ai_api_config["provider"] == "xAI":
                data = {"prompt": prompt, "max_tokens": 150, "temperature": 0.7, "stream": True}
                response = requests.post(ai_api_config["endpoint"], headers=headers, json=data, stream=True)
            elif ai_api_config["provider"] == "LM Studio":
                data = {"prompt": prompt, "max_tokens": 150, "temperature": 0.7, "stream": True}
                response = requests.post(ai_api_config["endpoint"], headers=headers, json=data, stream=True)
            response.raise_for_status()
            full_response = ""
            for line in response.iter_lines():
                if not self.is_running:
                    break
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        chunk = decoded_line[6:]
                        if chunk != "[DONE]":
                            json_data = json.loads(chunk)
                            text_chunk = json_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if text_chunk:
                                full_response += text_chunk
                                self.text_chunk.emit(text_chunk)
                                time.sleep(0.1)
            self.finished.emit(full_response.strip())
        except Exception as e:
            logging.error(f"AI streaming failed: {e}")
            self.finished.emit(f"Error: {e}")
        finally:
            self.is_running = False

    def stop(self):
        self.is_running = False
        self.quit()
        self.wait()

if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        control_window = ControlWindow()
        control_window.show()
        sys.exit(app.exec_())
    except Exception as e:
        logging.error(f"Application failed to start: {e}")
        print(f"Error: {e}")
        sys.exit(1)
