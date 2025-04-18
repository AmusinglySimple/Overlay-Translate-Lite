import os
import sys
import time
import datetime
import logging
import logging.handlers
import requests
import subprocess
import webbrowser
import textwrap
import tempfile
import shutil
import json
import gc
import platform
import keyring
import math

from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import (
    QDialog, QApplication, QVBoxLayout, QLabel, QMainWindow, QPushButton,
    QInputDialog, QSlider, QMessageBox, QProgressBar, QSystemTrayIcon, QMenu,
    QWidget, QHBoxLayout, QTextEdit, QLineEdit, QFileDialog, QGroupBox, QCheckBox,
    QColorDialog, QComboBox
)
from PySide6.QtCore import Qt, QPoint, QRect, QTimer, QThread, Signal, QPropertyAnimation, QEasingCurve, QPointF, QEventLoop
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QBrush, QImage, QLinearGradient,
    QKeySequence, QShortcut, QFont, QIcon, QFontDatabase, QPolygonF
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QGraphicsDropShadowEffect

from PIL import Image, ImageDraw, ImageFont, ImageOps
from paddleocr import PaddleOCR
from langdetect import detect
import cv2
import numpy as np

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# File handler
file_handler = logging.handlers.RotatingFileHandler('overlay_translate.log', maxBytes=1048576, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Global stylesheet
GLOBAL_STYLESHEET = """
    QDialog, QMainWindow {
        background-color: rgba(20, 20, 20, 200);
        color: #e0e0e0;
        font-family: 'Roboto', Arial, sans-serif;
        border-radius: 15px;
    }
    QLabel {
        color: #00ffcc;
        font-size: 14px;
    }
    QPushButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4a90e2, stop:1 #00ffcc);
        color: #ffffff;
        border-radius: 10px;
        padding: 12px;
        font-size: 14px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5aa1f2, stop:1 #00ffdd);
    }
    QPushButton:pressed {
        background: #357abd;
        padding-top: 14px;
        padding-bottom: 10px;
    }
    QCheckBox {
        color: #e0e0e0;
        font-size: 14px;
    }
    QLineEdit {
        background: rgba(30, 30, 30, 150);
        color: #e0e0e0;
        border: 1px solid rgba(255, 255, 255, 20);
        border-radius: 6px;
        padding: 8px;
    }
    QLineEdit:focus {
        border: 1px solid #00ffcc;
    }
    QGroupBox {
        color: #00ffcc;
        font-size: 16px;
        font-weight: 600;
        border: 1px solid rgba(255, 255, 255, 20);
        border-radius: 10px;
        margin-top: 12px;
        background: rgba(30, 30, 30, 150);
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 6px 12px;
        color: #00ffcc;
    }
    QTextEdit {
        background: rgba(30, 30, 30, 150);
        color: #00ffcc;
        font-family: 'Roboto Mono', 'Courier New', monospace;
        font-size: 14px;
        border: 1px solid rgba(255, 255, 255, 20);
        border-radius: 10px;
        padding: 12px;
    }
"""

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(PROJECT_ROOT, "window_positions.json")
SUPPORT_FOLDER = os.path.join(os.path.expanduser("~/Desktop"), "Support")

paddle_ocr = None
ai_api_config = {"provider": "Ollama", "endpoint": "http://localhost:11434/api/chat"}

def get_system_font_path(font_name):
    system = platform.system()
    font_paths = {
        "Windows": {
            "Arial": r"C:\Windows\Fonts\arial.ttf",
            "MSYH": r"C:\Windows\Fonts\msyh.ttc",
            "Malgun": r"C:\Windows\Fonts\malgun.ttf",
            "Roboto": r"C:\Windows\Fonts\Roboto-Regular.ttf",
        },
        "Darwin": {
            "Arial": "/Library/Fonts/Arial.ttf",
            "MSYH": "/System/Library/Fonts/STHeiti Light.ttc",
            "Malgun": "/System/Library/Fonts/AppleGothic.ttf",
            "Roboto": "/Library/Fonts/Roboto-Regular.ttf",
        },
        "Linux": {
            "Arial": "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
            "MSYH": "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "Malgun": "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.ttf",
            "Roboto": "/usr/share/fonts/truetype/roboto/Roboto-Regular.ttf",
        }
    }
    
    default_font = "arial.ttf"
    font_map = font_paths.get(system, {})
    
    if font_name == "default":
        font_path = font_map.get("Roboto", font_map.get("Arial", default_font))
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

def choose_font_for_text(text, default_font="Roboto", font_size=24):
    # Detect Unicode ranges for script-specific fonts
    if any('\u4e00' <= c <= '\u9fff' for c in text):  # Chinese characters
        return QFont("Noto Sans CJK SC", font_size)
    elif any('\u3040' <= c <= '\u309F' for c in text):  # Japanese Hiragana
        return QFont("Noto Sans CJK JP", font_size)
    elif any('\u30A0' <= c <= '\u30FF' for c in text):  # Japanese Katakana
        return QFont("Noto Sans CJK JP", font_size)
    elif any('\uAC00' <= c <= '\uD7AF' for c in text):  # Korean Hangul
        return QFont("Noto Sans CJK KR", font_size)
    else:
        return QFont(default_font, font_size)


def initialize_paddle_ocr(lang='en'):
    global paddle_ocr
    try:
        if paddle_ocr:
            del paddle_ocr
            paddle_ocr = None
            gc.collect()
        paddle_ocr = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            use_gpu=False,
            det=True,
            rec=True,
            e2e=False,
            show_log=False
        )
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

initialize_paddle_ocr('es')

class TranslationWorker(QThread):
    translation_complete = Signal(dict)

    def __init__(self, file_name, source_language, target_language, fonts, use_translate_with_ai=False, contrast_factor=1.0, live=False, parent=None):
        super().__init__(parent)
        self.file_name = file_name
        self.source_language = source_language
        self.target_language = target_language
        self.fonts = fonts
        self.use_translate_with_ai = use_translate_with_ai
        self.contrast_factor = contrast_factor
        self.live = live
        self.is_running = True

    def preprocess_image(self, image):
        try:
            if image.width > 1000 or image.height > 1000:
                image = image.resize((int(image.width / 2), int(image.height / 2)))
            image = image.convert('RGB')
            img_array = np.array(image)
            img_array = cv2.convertScaleAbs(img_array, alpha=self.contrast_factor, beta=0)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            return Image.fromarray(binary)
        except Exception as e:
            logging.error(f"Image preprocessing failed: {e}")
            raise

    def correct_ocr_text(self, text):
        corrections = {
            'OpenAl': 'OpenAI',
            'tngresa': 'ingresa',
            'seccin': 'sección',
            'suscripcion': 'suscripción',
            'CpenAl': 'OpenAI',
            'ChatGpT': 'ChatGPT',
            'configuraci6n': 'configuración',
            'interna*': 'interna',
            'aplicaciontodo': 'aplicación; todo',
            'utlizar': 'utilizar',
            'nive penAl': 'nivel de OpenAI',
            'CpenAl. .': 'OpenAI.'
        }
        for wrong, correct in corrections.items():
            text = text.replace(wrong, correct)
        return text

    def translate_with_ai(self, original_text, num_lines):
        if not ai_api_config["provider"]:
            logging.warning("No AI API provider configured; returning original text.")
            return original_text
        try:
            worker = AITranslationWorker(original_text, self.source_language, self.target_language, num_lines)
            translated_text = None
            error_message = None

            def on_translation_complete(text):
                nonlocal translated_text
                translated_text = text
                logging.debug(f"Received AI translation: '{text}'")

            def on_error(error):
                nonlocal error_message
                error_message = error
                logging.error(f"AI translation error: {error}")

            worker.translation_complete.connect(on_translation_complete)
            worker.error.connect(on_error)

            loop = QEventLoop()
            worker.finished.connect(loop.quit)
            worker.start()

            loop.exec_()

            if error_message:
                logging.error(f"AI translation failed: {error_message}")
                return original_text
            if translated_text is None:
                logging.error("No translation received from AI worker")
                return original_text
            logging.debug(f"Returning AI translated text: '{translated_text}'")
            return translated_text
        except Exception as e:
            logging.error(f"AI translation exception: {e}")
            return original_text

    def run(self):
        if not self.is_running:
            return
        result = {'original_text': '', 'translated_text': '', 'error_message': '', 'boxes': [], 'live': self.live}
        try:
            if not paddle_ocr:
                raise Exception("PaddleOCR is not initialized. Check installation and dependencies.")

            try:
                image = Image.open(self.file_name)
            except Exception as e:
                raise Exception(f"Failed to load image: {e}")

            try:
                image = self.preprocess_image(image)
            except Exception as e:
                raise Exception(f"Image preprocessing failed: {e}")

            temp_file = self.file_name + "_preprocessed.png"
            try:
                image.save(temp_file, format='PNG', quality=95)
            except Exception as e:
                raise Exception(f"Failed to save preprocessed image: {e}")

            try:
                ocr_result = paddle_ocr.ocr(temp_file, cls=True)
            except Exception as e:
                logging.error(f"PaddleOCR processing failed: {e}")
                result['original_text'] = ""
                result['translated_text'] = "OCR failed."
                result['boxes'] = []
                result['error_message'] = f"PaddleOCR processing failed: {e}"
            finally:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception as e:
                        logging.warning(f"Failed to remove temporary file {temp_file}: {e}")

            if not result['error_message']:
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
                    original_text = self.correct_ocr_text(original_text)
                    result['original_text'] = original_text
                    result['boxes'] = boxes

                    source_lang = self.source_language if self.source_language != 'auto' else detect(original_text)

                    translated_text = None

                    if self.use_translate_with_ai and not self.live:
                        translated_text = self.translate_with_ai(original_text, len(lines))
                        logging.debug(f"AI translated_text: '{translated_text}'")
                        if not translated_text or translated_text in ["No text detected.", original_text]:
                            logging.warning("AI translation failed or returned no text; falling back to LibreTranslate.")
                            translated_text = None

                    if translated_text is None:
                        data = {"q": original_text, "source": source_lang, "target": self.target_language, "format": "text"}
                        url = "http://127.0.0.1:5000/translate"
                        try:
                            response = requests.post(url, data=data, timeout=30)
                            response.raise_for_status()
                            translated_text = response.json().get("translatedText", "Translation failed.")
                        except requests.RequestException as e:
                            logging.error(f"LibreTranslate failed: {e}")
                            translated_text = "Translation service unavailable."

                    result['translated_text'] = translated_text if translated_text else "Translation failed."
                    logging.debug(f"Assigned translated_text to result: '{result['translated_text']}'")

                    translated_lines = translated_text.split('\n') if translated_text else []
                    logging.debug(f"Raw translated_text: '{translated_text}'")
                    logging.debug(f"Initial translated_lines: {translated_lines}")

                    if len(translated_lines) != len(boxes):
                        logging.warning(f"Mismatch: {len(translated_lines)} translated lines for {len(boxes)} boxes.")
                        if len(translated_lines) < len(boxes):
                            logging.debug(f"Padding translated_lines with {len(boxes) - len(translated_lines)} empty strings.")
                            translated_lines.extend([""] * (len(boxes) - len(translated_lines)))
                        elif len(translated_lines) > len(boxes):
                            logging.debug(f"Truncating translated_lines from {len(translated_lines)} to {len(boxes)}: discarded {translated_lines[len(boxes):]}")
                            translated_lines = translated_lines[:len(boxes)]

                    logging.debug(f"Final translated_lines: {translated_lines}")
                    result['translated_lines'] = translated_lines

        except Exception as e:
            logging.error(f"Translation error: {e}")
            result['error_message'] = str(e)
            result['translated_text'] = "Translation failed due to an error."
            result['translated_lines'] = []
        finally:
            if self.is_running:
                logging.debug(f"Emitting result: translated_text='{result['translated_text']}', translated_lines={result['translated_lines']}")
                self.translation_complete.emit(result)
            self.is_running = False

    def stop(self):
        self.is_running = False
        self.quit()
        self.wait()

class AITranslationWorker(QThread):
    translation_complete = Signal(str)
    error = Signal(str)

    def __init__(self, text, source_language, target_language, num_lines, parent=None):
        super().__init__(parent)
        self.text = text
        self.source_language = source_language
        self.target_language = target_language
        self.num_lines = num_lines
        self.is_running = True

    def run(self):
        if not self.is_running or not ai_api_config["provider"]:
            self.error.emit("No AI API configured.")
            return
        try:
            lang_map = {
                "en": "English",
                "es": "Spanish",
                "fr": "French",
                "de": "German",
                "it": "Italian",
                "pt": "Portuguese",
                "ru": "Russian",
                "zh-cn": "Chinese (Simplified)",
                "ja": "Japanese",
                "ko": "Korean"
            }
            target_lang_name = lang_map.get(self.target_language, "English")
            
            lines = self.text.split('\n')
            numbered_text = '\n'.join(f"{i+1}. {line}" for i, line in enumerate(lines))
            prompt = (
                f"Translate the following text to {target_lang_name}, preserving the exact number of lines ({self.num_lines}). "
                f"Each line should be a direct translation of the corresponding input line, maintaining the original meaning without paraphrasing. "
                f"Return the translation in the format '1. translated text', '2. translated text', etc., one per line. "
                f"If a line is empty, return an empty translation for that line. Ensure exactly {self.num_lines} lines are returned:\n"
                f"{numbered_text}"
            )
            logging.debug(f"Translation prompt: {prompt}")

            headers = {"Content-Type": "application/json"}
            api_key = keyring.get_password("OverlayTranslate", ai_api_config["provider"])
            if ai_api_config["provider"] in ["OpenAI", "LM Studio"] and api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            if ai_api_config["provider"] == "OpenAI":
                data = {
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max(5000 * self.num_lines, 100),
                    "temperature": 0.3
                }
                endpoint = ai_api_config["endpoint"]
                response = requests.post(endpoint, headers=headers, json=data)
            elif ai_api_config["provider"] == "Ollama":
                data = {
                    "model": "llama3.2",
                    "prompt": prompt,
                    "stream": False
                }
                endpoint = ai_api_config["endpoint"].replace('/api/chat', '/api/generate')
                response = requests.post(endpoint, headers=headers, json=data)
            elif ai_api_config["provider"] == "LM Studio":
                data = {
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max(5000 * self.num_lines, 100),
                    "temperature": 0.3
                }
                endpoint = "http://localhost:1234/v1/chat/completions"
                response = requests.post(endpoint, headers=headers, json=data)

            response.raise_for_status()
            result = response.json()
            
            if ai_api_config["provider"] == "OpenAI":
                translated_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            elif ai_api_config["provider"] == "Ollama":
                translated_text = result.get("response", "")
            elif ai_api_config["provider"] == "LM Studio":
                translated_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not translated_text:
                self.error.emit("Empty response from AI.")
                return

            logging.debug(f"Raw AI translated_text: '{translated_text}'")

            translated_lines = []
            for line in translated_text.split('\n'):
                line = line.strip()
                if not line or line.lower().startswith(("here is the", "translation:", "translated text:", "note:")):
                    logging.debug(f"Skipping line: '{line}'")
                    continue
                if line and line[0].isdigit() and '.' in line[:3]:
                    try:
                        cleaned_line = line[line.index('.') + 1:].strip()
                        cleaned_line = cleaned_line.replace(" Al ", " AI ").replace(" Al.", " AI.")
                        translated_lines.append(cleaned_line)
                        logging.debug(f"Cleaned numbered line: '{line}' -> '{cleaned_line}'")
                    except ValueError:
                        logging.warning(f"Failed to clean line: '{line}'")
                        translated_lines.append(line)
                else:
                    translated_lines.append(line)

            logging.debug(f"Cleaned translated_lines: {translated_lines}")

            if len(translated_lines) < self.num_lines:
                logging.warning(f"AI returned {len(translated_lines)} lines, expected {self.num_lines}. Padding with empty strings.")
                translated_lines.extend([""] * (self.num_lines - len(translated_lines)))
            elif len(translated_lines) > self.num_lines:
                logging.warning(f"AI returned {len(translated_lines)} lines, expected {self.num_lines}. Truncating.")
                translated_lines = translated_lines[:self.num_lines]

            original_lines = self.text.split('\n')
            for i in range(min(self.num_lines, len(translated_lines))):
                if not translated_lines[i].strip() and i < len(original_lines):
                    logging.debug(f"Line {i+1} is empty; using original: '{original_lines[i]}'")
                    translated_lines[i] = original_lines[i]

            logging.debug(f"Final translated_lines: {translated_lines}")

            final_text = '\n'.join(translated_lines).strip()
            logging.debug(f"Final translated text: '{final_text}'")

            if not final_text and not any(translated_lines):
                self.error.emit("No valid translation text after cleaning.")
                return

            self.translation_complete.emit(final_text)
            logging.info(f"AI translation completed: {final_text}")

        except Exception as e:
            logging.error(f"AI translation failed: {e}")
            self.error.emit(str(e))
        finally:
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
        self.initUI()
        self.load_geometry()

    def initUI(self):
        self.setStyleSheet(GLOBAL_STYLESHEET)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        self.translation_label = QLabel("", self)
        self.translation_label.setWordWrap(True)
        self.translation_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.translation_label)
        self.setLayout(layout)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)

    def updateTranslation(self, text):
        flat_text = text.replace('\n', ' ').strip()
        self.translation_label.setText(flat_text)
        self.translation_label.setFont(choose_font_for_text(flat_text, font_size=20))


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
        self.setWindowTitle("🌌 Overlay Translate")
        self.setGeometry(100, 100, 450, 450)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(GLOBAL_STYLESHEET)
        self.initUI()
        self.raise_()
        self.activateWindow()

    def initUI(self):
        self.setStyleSheet("""
            QDialog {
                background-color: rgba(20, 20, 20, 200);
                border-radius: 15px;
                color: #ffffff;
                font-family: 'Roboto', Arial, sans-serif;
            }
        """)
        layout = QVBoxLayout()
        layout.setContentsMargins(25, 25, 25, 25)
        intro_label = QLabel(
            "<h2 style='color: #00ffcc;'>🌌 Welcome to Overlay Translate</h2><br>"
            "<p style='line-height: 1.6; color: #e0e0e0;'>⚡️ Experience seamless screen text capture and translation with a futuristic edge.</p><br>"
            "<h3 style='color: #4a90e2;'>🔮 Features:</h3>"
            "<ul style='line-height: 1.8; color: #b0b0b0;'>"
            "<li>📷 Instant text capture</li>"
            "<li>🎥 Real-time translation streams</li>"
            "<li>🌍 Offline multilingual support</li>"
            "<li>🖥️ Sleek, modern interface</li>"
            "<li>💬 AI-powered chat</li>"
            "<li>💾 Save captures effortlessly</li>"
            "<li>⚙️ Customizable settings</li>"
            "</ul><br>"
            "<p style='text-align: center; color: #00ffcc;'>Dive into the future of translation! 🚀</p>"
        )
        intro_label.setWordWrap(True)
        intro_label.setAlignment(Qt.AlignCenter)
        intro_label.setStyleSheet("font-size: 14px;")

        close_button = QPushButton("Launch")
        icon_path = os.path.join(PROJECT_ROOT, "assets/icons/launch.svg")
        if os.path.exists(icon_path):
            close_button.setIcon(QIcon(icon_path))
        close_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4a90e2, stop:1 #00ffcc);
                color: #ffffff;
                border-radius: 10px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5aa1f2, stop:1 #00ffdd);
            }
            QPushButton:pressed {
                background: #357abd;
                padding-top: 14px;
                padding-bottom: 10px;
            }
        """)
        close_button.clicked.connect(self.accept)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 255, 204, 100))
        shadow.setOffset(0, 0)
        close_button.setGraphicsEffect(shadow)

        layout.addWidget(intro_label)
        layout.addWidget(close_button)
        self.setLayout(layout)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(800)
        self.animation.setStartValue(0)
        self.animation.setEndValue(1)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.animation.start()

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
        self.is_in_design_mode = False

        self.handle_size = 10
        self.drag_handle_rect = QRect(0, 0, self.handle_size, self.handle_size)
        self.resize_handle_rect = QRect(0, 0, self.handle_size, self.handle_size)

    def set_design_mode(self, enabled):
        self.is_in_design_mode = enabled
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.is_in_design_mode:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            pen = QPen(QColor(0, 255, 204), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

            painter.setBrush(QColor(0, 255, 204, 180))
            painter.setPen(Qt.NoPen)
            self.drag_handle_rect = QRect(0, 0, self.handle_size, self.handle_size)
            painter.drawRect(self.drag_handle_rect)

            self.resize_handle_rect = QRect(self.width() - self.handle_size, self.height() - self.handle_size, self.handle_size, self.handle_size)
            painter.drawRect(self.resize_handle_rect)

    def mousePressEvent(self, event):
        if not self.is_in_design_mode:
            self.widget.mousePressEvent(event)
            return

        self.drag_start_pos = event.globalPosition().toPoint()
        self.resize_start_pos = event.globalPosition().toPoint()
        self.original_pos = self.pos()
        self.original_size = self.size()

        if self.drag_handle_rect.contains(event.position().toPoint()):
            self.dragging = True
            self.setCursor(Qt.SizeAllCursor)
        elif self.resize_handle_rect.contains(event.position().toPoint()):
            self.resizing = True
            self.setCursor(Qt.SizeFDiagCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if not self.is_in_design_mode:
            self.widget.mouseMoveEvent(event)
            return

        if self.dragging:
            delta = event.globalPosition().toPoint() - self.drag_start_pos
            new_pos = self.original_pos + delta

            siblings = [w for w in self.parent().findChildren(DraggableResizableWidget) if w != self]
            min_spacing = 5
            for sibling in siblings:
                sibling_rect = sibling.geometry()
                if sibling_rect.adjusted(-min_spacing, -min_spacing, min_spacing, min_spacing).contains(new_pos):
                    if new_pos.x() < sibling_rect.x():
                        new_pos.setX(sibling_rect.x() - self.width() - min_spacing)
                    else:
                        new_pos.setX(sibling_rect.right() + min_spacing)
                    if new_pos.y() < sibling_rect.y():
                        new_pos.setY(sibling_rect.y() - self.height() - min_spacing)
                    else:
                        new_pos.setY(sibling_rect.bottom() + min_spacing)

            parent_rect = self.parent().rect()
            new_pos.setX(max(0, min(new_pos.x(), parent_rect.width() - self.width())))
            new_pos.setY(max(0, min(new_pos.y(), parent_rect.height() - self.height())))
            self.move(new_pos)

        elif self.resizing:
            delta = event.globalPosition().toPoint() - self.resize_start_pos
            new_width = max(self.minimumWidth(), self.original_size.width() + delta.x())
            new_height = max(self.minimumHeight(), self.original_size.height() + delta.y())
            self.resize(new_width, new_height)

        event.accept()

    def mouseReleaseEvent(self, event):
        if not self.is_in_design_mode:
            self.widget.mouseReleaseEvent(event)
            return

        if self.dragging:
            self.dragging = False
            self.unsetCursor()
        elif self.resizing:
            self.resizing = False
            self.unsetCursor()
        else:
            self.widget.mousePressEvent(event)
        event.accept()

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
        self.translate_with_ai_enabled = False
        self.showIntroDialog()
        self.capture_widget = CaptureWidget(control_window=self)
        self.snipping_tool = SnippingTool(self.capture_widget)
        self.font_size = 20
        self.initUI()
        self.setupGlobalShortcuts()
        self.load_geometry()
        ensure_support_folder()
        self.startBackgroundAnimation()

    def showIntroDialog(self):
        intro_dialog = IntroDialog(self)
        intro_dialog.exec()

    def initUI(self):
        self.setWindowTitle('Overlay Translate')
        flags = Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1e1e1e, stop:1 #2a2a2a);
                color: #e0e0e0;
                font-family: 'Roboto', Arial, sans-serif;
            }
            QGroupBox {
                color: #00ffcc;
                font-size: 16px;
                font-weight: 600;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 10px;
                margin-top: 12px;
                background: rgba(30, 30, 30, 150);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 6px 12px;
                color: #00ffcc;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
            }
        """)

        self.capture_btn = self.createButton('Capture / Translate (F1)', self.captureScreen, '#4a90e2', '#5aa1f2', '#357abd', 'capture.svg')
        self.live_capture_btn = self.createButton('Live Capture', self.toggleLiveCapture, '#4a90e2', '#5aa1f2', '#357abd', 'live.svg')
        self.increase_font_btn = self.createButton('+', self.increaseFontSize, '#2ecc71', '#3edf81', '#27ae60', 'zoom_in.svg')
        self.decrease_font_btn = self.createButton('-', self.decreaseFontSize, '#e74c3c', '#f75c4c', '#c0392b', 'zoom_out.svg')
        self.toggle_btn = self.createButton('Click-Through (F2)', self.capture_widget.toggleClickThrough, '#9b59b6', '#ab69c6', '#8e44ad', 'click.svg')
        self.snip_btn = self.createButton('Snip (F4)', self.activateSnippingTool, '#16a085', '#26b095', '#138d75', 'snip.svg')

        self.increase_font_btn.setFixedSize(40, 40)
        self.decrease_font_btn.setFixedSize(40, 40)

        slider_style = """
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(255, 255, 255, 20);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, stop:0 #ffffff, stop:1 #4a90e2);
                width: 16px;
                height: 16px;
                border-radius: 8px;
                margin: -5px 0;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4a90e2, stop:1 #00ffcc);
                border-radius: 3px;
            }
        """
        self.opacity_slider = QSlider(Qt.Horizontal, self)
        self.opacity_slider.setRange(1, 100)
        self.opacity_slider.setValue(10)
        self.opacity_slider.setStyleSheet(slider_style)
        self.opacity_slider.valueChanged.connect(self.adjustCaptureWidgetOpacity)

        self.live_translation_label = QLabel("Live translation will appear here...", self)
        self.live_translation_label.setWordWrap(True)
        self.live_translation_label.setAlignment(Qt.AlignCenter)
        self.live_translation_label.setStyleSheet("""
            background: rgba(30, 30, 30, 150);
            border: 1px solid rgba(255, 255, 255, 20);
            border-radius: 10px;
            padding: 15px;
            font-size: 18px;
            color: #00ffcc;
        """)
        self.live_translation_label.setVisible(False)

        self.label_opacity_effect = QGraphicsOpacityEffect(self.live_translation_label)
        self.live_translation_label.setGraphicsEffect(self.label_opacity_effect)

        self.label_fade_anim = QPropertyAnimation(self.label_opacity_effect, b"opacity")
        self.label_fade_anim.setDuration(400)
        self.label_fade_anim.setStartValue(0.0)
        self.label_fade_anim.setEndValue(1.0)
        self.label_fade_anim.setEasingCurve(QEasingCurve.InOutQuad)

        self.translation_progress_bar = QProgressBar(self)
        self.translation_progress_bar.setMaximum(100)
        self.translation_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                background: rgba(30, 30, 30, 150);
                color: #e0e0e0;
                text-align: center;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4a90e2, stop:1 #00ffcc);
                border-radius: 5px;
            }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        capture_group = QGroupBox("Capture Controls")
        capture_layout = QVBoxLayout()
        capture_layout.addWidget(self.capture_btn)
        capture_layout.addWidget(self.live_capture_btn)
        capture_layout.addWidget(self.snip_btn)
        capture_group.setLayout(capture_layout)
        main_layout.addWidget(capture_group)

        main_layout.addWidget(self.live_translation_label)

        font_group = QGroupBox("Font Size (Live Translation)")
        font_group.setStyleSheet("""
            QGroupBox {
                color: #00ffcc;
                font-size: 16px;
                font-weight: 600;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 8px;
                margin-top: 6px;
                margin-bottom: 0px;
                background: rgba(30, 30, 30, 150);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 6px;
                color: #00ffcc;
            }
        """)
        font_group.setMaximumHeight(70)
        font_layout = QHBoxLayout()
        font_layout.setContentsMargins(4, 2, 4, 2)
        font_layout.setSpacing(4)
        font_layout.addWidget(self.increase_font_btn)
        font_layout.addWidget(self.decrease_font_btn)
        font_group.setLayout(font_layout)
        main_layout.addWidget(font_group)

        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()
        settings_layout.addWidget(self.toggle_btn)
        settings_layout.addWidget(QLabel("Opacity:", self))
        settings_layout.addWidget(self.opacity_slider)
        self.translate_with_ai_toggle = QPushButton('Translate with AI: OFF', self)
        self.translate_with_ai_toggle.setCheckable(True)
        self.translate_with_ai_toggle.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e74c3c, stop:1 #c0392b);
                color: #ffffff;
                border-radius: 10px;
                padding: 12px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover:!checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f75c4c, stop:1 #d1483b);
                padding: 11px;
            }
            QPushButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2ecc71, stop:1 #27ae60);
            }
            QPushButton:hover:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3edf81, stop:1 #38bf71);
                padding: 11px;
            }
            QPushButton:pressed {
                background: #c0392b;
                padding-top: 14px;
                padding-bottom: 10px;
            }
        """)
        self.translate_with_ai_toggle.clicked.connect(self.toggleTranslateWithAI)
        settings_layout.addWidget(self.translate_with_ai_toggle)
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
            ai_api_config.update({k: v for k, v in positions['ai_api_config'].items() if k != "api_key"})

    def startBackgroundAnimation(self):
        self.bg_anim = QPropertyAnimation(self, b"windowOpacity")
        self.bg_anim.setDuration(10000)
        self.bg_anim.setStartValue(1.0)
        self.bg_anim.setEndValue(1.0)
        self.bg_anim.setLoopCount(-1)
        self.bg_anim.start()

    def createMenuBar(self):
        menu_bar = QtWidgets.QMenuBar(self)
        menu_bar.setStyleSheet("""
            QMenuBar {
                background: rgba(20, 20, 20, 150);
                color: #00ffcc;
                font-size: 14px;
                font-family: 'Roboto', Arial, sans-serif;
            }
            QMenuBar::item {
                padding: 6px 12px;
            }
            QMenuBar::item:selected {
                background: rgba(74, 144, 226, 100);
            }
            QMenu {
                background: rgba(20, 20, 20, 200);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 8px;
            }
            QMenu::item {
                padding: 6px 25px;
            }
            QMenu::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4a90e2, stop:1 #00ffcc);
                color: #ffffff;
            }
        """)
        file_menu = menu_bar.addMenu("File")
        file_menu.addAction("Minimize to Tray", self.minimizeToTray)
        file_menu.addAction("Exit", self.closeApplication)
        settings_menu = menu_bar.addMenu("Settings")
        settings_menu.addAction("Source Language", self.selectSourceLanguage)
        settings_menu.addAction("Target Language", self.selectTargetLanguage)
        settings_menu.addAction("Server", self.openServer)
        settings_menu.addAction("Toggle Translate with AI", self.toggleTranslateWithAI)
        settings_menu.addAction("Set Default Font Size", self.setDefaultFontSize)
        settings_menu.addAction("Set Default Font Type", self.setDefaultFontType)
        settings_menu.addAction("Configure AI API", self.configureAIAPI)
        tools_menu = menu_bar.addMenu("Tools")
        tools_menu.addAction("Chat with AI", self.openChatWindow)
        tools_menu.addAction("Pop Out Live Translation", self.popOutLiveTranslation)
        return menu_bar

    def createButton(self, text, callback, color, hover, pressed, icon_name):
        button = QPushButton(text, self)
        icon_path = os.path.join(PROJECT_ROOT, f"assets/icons/{icon_name}")
        if os.path.exists(icon_path):
            button.setIcon(QIcon(icon_path))
            button.setText('')
        else:
            logging.warning(f"Icon not found at {icon_path}, using text label: {text}")
        button.clicked.connect(callback)
        button.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {color}, stop:1 {pressed});
                color: #ffffff;
                border-radius: 10px;
                padding: 12px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {hover}, stop:1 {color});
            }}
            QPushButton:pressed {{
                background: {pressed};
                padding-top: 14px;
                padding-bottom: 10px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(255, 255, 255, 100))
        shadow.setOffset(0, 0)
        button.setGraphicsEffect(shadow)
        return button

    def toggleTranslateWithAI(self):
        if self.live_capture_timer.isActive():
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Warning")
            msg_box.setText("Translate with AI cannot be enabled during live capture due to performance issues.")
            msg_box.setStyleSheet(GLOBAL_STYLESHEET)
            msg_box.exec()
            self.translate_with_ai_enabled = False
            self.translate_with_ai_toggle.setChecked(False)
            self.translate_with_ai_toggle.setText('Translate with AI: OFF')
            self.translate_with_ai_toggle.setStyleSheet(self.translate_with_ai_toggle.styleSheet())
            logging.info("Translate with AI disabled due to active live capture")
            return

        if not ai_api_config["provider"]:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Warning")
            msg_box.setText("Please set an AI API provider first in Settings > Configure AI API")
            msg_box.setStyleSheet(GLOBAL_STYLESHEET)
            msg_box.exec()
            self.translate_with_ai_enabled = False
            self.translate_with_ai_toggle.setChecked(False)
            self.translate_with_ai_toggle.setText('Translate with AI: OFF')
            self.translate_with_ai_toggle.setStyleSheet(self.translate_with_ai_toggle.styleSheet())
            return
            
        self.translate_with_ai_enabled = not self.translate_with_ai_enabled
        self.translate_with_ai_toggle.setChecked(self.translate_with_ai_enabled)
        self.translate_with_ai_toggle.setText(
            'Translate with AI: ON' if self.translate_with_ai_enabled else 'Translate with AI: OFF'
        )
        self.translate_with_ai_toggle.setStyleSheet(self.translate_with_ai_toggle.styleSheet())

    def toggleLiveCapture(self):
        if self.live_capture_timer.isActive():
            self.live_capture_timer.stop()
            if not (self.live_translation_popout and self.live_translation_popout.isVisible()):
                self.live_translation_label.setVisible(False)
            self.live_capture_btn.setText('Live Capture')
            icon_path = os.path.join(PROJECT_ROOT, "assets/icons/live.svg")
            if os.path.exists(icon_path):
                self.live_capture_btn.setIcon(QIcon(icon_path))
                self.live_capture_btn.setText('')
            if self.translate_with_ai_enabled:
                self.translate_with_ai_enabled = False
                self.translate_with_ai_toggle.setText('Translate with AI: OFF')
                QMessageBox.information(self, "Info", "Translate with AI disabled during live capture.")
        else:
            if self.translate_with_ai_enabled:
                reply = QMessageBox.question(self, "Warning", "Translate with AI may cause instability during live capture. Continue?", QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No:
                    self.translate_with_ai_enabled = False
                    self.translate_with_ai_toggle.setText('Translate with AI: OFF')
            self.live_capture_timer.start()
            if not (self.live_translation_popout and self.live_translation_popout.isVisible()):
                self.live_translation_label.setVisible(True)
            self.live_capture_btn.setText('Stop Live Capture')
            icon_path = os.path.join(PROJECT_ROOT, "assets/icons/stop.svg")
            if os.path.exists(icon_path):
                self.live_capture_btn.setIcon(QIcon(icon_path))
                self.live_capture_btn.setText('')

    def captureScreen(self):
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                rect = self.capture_widget.rect()
                screen = QApplication.primaryScreen()
                screenshot = screen.grabWindow(0, self.capture_widget.x(), self.capture_widget.y(), rect.width(), rect.height())
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                fileName = os.path.join(SUPPORT_FOLDER, f"capture_{timestamp}.png")
                
                if not screenshot.save(fileName, format='PNG', quality=95):
                    raise Exception("Failed to save screenshot.")
                
                if not os.path.exists(fileName) or os.path.getsize(fileName) == 0:
                    raise Exception("Screenshot file is empty or does not exist.")
                
                with Image.open(fileName) as img:
                    img.verify()
                
                self.capture_widget.current_capture_path = fileName
                self.capture_widget.translateAndDisplay(fileName)
                return
            except Exception as e:
                logging.error(f"Capture attempt {attempt + 1}/{max_attempts} failed: {e}")
                if attempt == max_attempts - 1:
                    QMessageBox.critical(self.capture_widget, "Error", f"Capture failed after {max_attempts} attempts: {e}")
                    return
                time.sleep(0.5)

    def captureScreenForLiveTranslation(self):
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                rect = self.capture_widget.rect()
                screen = QApplication.primaryScreen()
                screenshot = screen.grabWindow(0, self.capture_widget.x(), self.capture_widget.y(), rect.width(), rect.height())
                tempFile = os.path.join(self.capture_widget.tempDir, 'live_capture.png')
                
                if not screenshot.save(tempFile, format='PNG', quality=95):
                    raise Exception("Failed to save screenshot for live translation.")
                
                if not os.path.exists(tempFile) or os.path.getsize(tempFile) == 0:
                    raise Exception("Live screenshot file is empty or does not exist.")
                
                with Image.open(tempFile) as img:
                    img.verify()
                
                self.startTranslationWorker(tempFile, live=True)
                return
            except Exception as e:
                logging.error(f"Live capture attempt {attempt + 1}/{max_attempts} failed: {e}")
                if attempt == max_attempts - 1:
                    self.live_translation_label.setText(f"Error: {e}")
                    return
                time.sleep(0.5)

    def startTranslationWorker(self, fileName, live=False):
        use_translate_with_ai = self.translate_with_ai_enabled and not live
        contrast_factor = self.capture_widget.contrast_factor
        self.translation_worker = TranslationWorker(fileName, self.source_language, self.target_language, self.capture_widget.fonts, use_translate_with_ai, contrast_factor, live, self)
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
            self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self)
            tray_menu = QMenu()
            tray_menu.addAction("Restore", self.restoreFromTray)
            tray_menu.addAction("Exit", self.closeApplication)
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.setToolTip("Overlay Translate")
            self.tray_icon.show()
            self.tray_icon.activated.connect(self.trayIconActivated)
            logging.debug(f"Tray icon initialized with path: {icon_path}")
            self.tray_icon.showMessage(
                "Overlay Translate",
                "Tray icon initialized successfully.",
                QSystemTrayIcon.Information,
                5000
            )
        else:
            logging.error(f"Tray icon not found at {icon_path}")
            self.tray_icon = None

    def trayIconActivated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.restoreFromTray()

    def minimizeToTray(self):
        self.hide()
        if self.tray_icon:
            logging.debug("Attempting to show tray notification")
            self.tray_icon.show()
            self.tray_icon.showMessage(
                "Overlay Translate",
                "Application minimized to system tray. Click the icon to restore.",
                QSystemTrayIcon.Information,
                10000
            )
            logging.debug("Tray notification triggered")
            QTimer.singleShot(500, lambda: self.showFallbackMessage())
        else:
            logging.error("Tray icon not initialized, cannot show notification")
            self.showFallbackMessage()

    def showFallbackMessage(self):
        if not self.isVisible():
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Overlay Translate")
            msg_box.setText("Application minimized to system tray. Click the tray icon to restore.")
            msg_box.setStyleSheet(GLOBAL_STYLESHEET)
            msg_box.exec()
            logging.debug("Fallback tray message shown")

    def restoreFromTray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def adjustCaptureWidgetOpacity(self, value):
        opacity = value / 100.0
        self.capture_widget.setWindowOpacity(opacity)

    def setupGlobalShortcuts(self):
        self.shortcut_capture = QShortcut(QKeySequence("F1"), QApplication.instance(), self.captureScreen)
        self.shortcut_toggle = QShortcut(QKeySequence("F2"), QApplication.instance(), self.capture_widget.toggleClickThrough)
        self.shortcut_source_lang = QShortcut(QKeySequence("F3"), QApplication.instance(), self.selectSourceLanguage)
        self.shortcut_snip = QShortcut(QKeySequence("F4"), QApplication.instance(), self.activateSnippingTool)
        self.shortcut_server = QShortcut(QKeySequence("F6"), QApplication.instance(), self.openServer)
        self.shortcut_exit = QShortcut(QKeySequence("F7"), QApplication.instance(), self.closeApplication)
        self.shortcut_improve = QShortcut(QKeySequence("F8"), QApplication.instance(), self.toggleTranslateWithAI)

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
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Select Source Language")
        dialog.setLabelText("Choose the language to detect:")
        dialog.setComboBoxItems(sorted(source_languages.keys()))
        dialog.setStyleSheet(GLOBAL_STYLESHEET + """
            QComboBox {
                background: rgba(30, 30, 30, 150);
                color: #00ffcc;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                padding: 5px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
            }
            QComboBox QAbstractItemView {
                background: rgba(30, 30, 30, 200);
                color: #00ffcc;
                selection-background-color: #4a90e2;
                selection-color: #ffffff;
            }
        """)
        ok = dialog.exec()
        lang = dialog.textValue()
        logging.debug(f"Source language dialog returned: lang={lang}, ok={ok}")
        if ok and lang:
            self.source_language = source_languages[lang]
            if self.source_language != 'auto':
                initialize_paddle_ocr(self.source_language)
            else:
                initialize_paddle_ocr('en')
            self.capture_widget.source_language = self.source_language
            logging.info(f"Source language set to: {self.source_language}")
        else:
            logging.warning("Source language selection cancelled or invalid")

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
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Select Target Language")
        dialog.setLabelText("Choose the language to translate to:")
        dialog.setComboBoxItems(sorted(target_languages.keys()))
        dialog.setStyleSheet(GLOBAL_STYLESHEET + """
            QComboBox {
                background: rgba(30, 30, 30, 150);
                color: #00ffcc;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                padding: 5px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
            }
            QComboBox QAbstractItemView {
                background: rgba(30, 30, 30, 200);
                color: #00ffcc;
                selection-background-color: #4a90e2;
                selection-color: #ffffff;
            }
        """)
        ok = dialog.exec()
        lang = dialog.textValue()
        logging.debug(f"Target language dialog returned: lang={lang}, ok={ok}")
        if ok and lang:
            self.target_language = target_languages[lang]
            self.capture_widget.target_language = self.target_language
            logging.info(f"Target language set to: {self.target_language}")
        else:
            logging.warning("Target language selection cancelled or invalid")

    def openServer(self):
        webbrowser.open('http://127.0.0.1:5000/')

    def closeApplication(self):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirm Exit")
        msg_box.setText("Are you sure you want to exit Overlay Translate? Support folder on your desktop will be deleted.")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: rgba(30, 30, 30, 200);
                color: #00ffcc;
                font-family: 'Roboto', Arial, sans-serif;
                font-size: 14px;
            }
            QMessageBox QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4a90e2, stop:1 #00ffcc);
                color: #ffffff;
                border-radius: 5px;
                padding: 8px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5aa1f2, stop:1 #00ffdd);
            }
            QMessageBox QPushButton:pressed {
                background: #357abd;
            }
        """)
        reply = msg_box.exec()
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
        positions['ai_api_config'] = {k: v for k, v in ai_api_config.items() if k != "api_key"}
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
        
        # Delete the Support folder
        if os.path.exists(SUPPORT_FOLDER):
            try:
                shutil.rmtree(SUPPORT_FOLDER, ignore_errors=True)
                logging.info(f"Support folder deleted at {SUPPORT_FOLDER}")
            except Exception as e:
                logging.error(f"Failed to delete Support folder: {e}")

    def load_geometry(self):
        positions = load_window_positions()
        if 'ControlWindow' in positions:
            geometry = positions['ControlWindow']
            self.setGeometry(geometry['x'], geometry['y'], geometry['width'], geometry['height'])

    def closeEvent(self, event):
        event.ignore()
        self.minimizeToTray()

    def activateSnippingTool(self):
        self.capture_widget.hide()
        self.snipping_tool.show()

    def openChatWindow(self):
        logging.debug("Opening ChatWindow")
        try:
            self.chat_window = ChatWindow(parent=self)
            self.chat_window.show()
            logging.debug("ChatWindow shown")
        except Exception as e:
            logging.error(f"Failed to open ChatWindow: {e}")

    def increaseFontSize(self):
        self.font_size += 2
        self.live_translation_label.setStyleSheet(f"""
            background: rgba(30, 30, 30, 150);
            border: 1px solid rgba(255, 255, 255, 20);
            border-radius: 10px;
            padding: 15px;
            font-size: {self.font_size}px;
            color: #00ffcc;
        """)

    def decreaseFontSize(self):
        if self.font_size > 10:
            self.font_size -= 2
            self.live_translation_label.setStyleSheet(f"""
                background: rgba(30, 30, 30, 150);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 10px;
                padding: 15px;
                font-size: {self.font_size}px;
                color: #00ffcc;
            """)

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
        dialog = QDialog(self)
        dialog.setWindowTitle("Configure AI API")
        dialog.setModal(True)
        dialog.setStyleSheet(GLOBAL_STYLESHEET)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)

        api_group = QGroupBox("AI API Settings")
        api_layout = QVBoxLayout()

        openai_layout = QHBoxLayout()
        self.openai_checkbox = QCheckBox("OpenAI (ChatGPT)")
        self.openai_checkbox.setChecked(ai_api_config["provider"] == "OpenAI")
        self.openai_key_input = QLineEdit(keyring.get_password("OverlayTranslate", "OpenAI") or "")
        self.openai_key_input.setEchoMode(QLineEdit.Password)
        openai_layout.addWidget(self.openai_checkbox)
        openai_layout.addWidget(self.openai_key_input)

        ollama_layout = QHBoxLayout()
        self.ollama_checkbox = QCheckBox("Ollama")
        self.ollama_checkbox.setChecked(ai_api_config["provider"] == "Ollama")
        self.ollama_endpoint_input = QLineEdit(ai_api_config["endpoint"] if ai_api_config["provider"] == "Ollama" else "http://localhost:11434")
        ollama_layout.addWidget(self.ollama_checkbox)
        ollama_layout.addWidget(self.ollama_endpoint_input)

        lmstudio_layout = QHBoxLayout()
        self.lmstudio_checkbox = QCheckBox("LM Studio (Local)")
        self.lmstudio_checkbox.setChecked(ai_api_config["provider"] == "LM Studio")
        self.lmstudio_key_input = QLineEdit(keyring.get_password("OverlayTranslate", "LM Studio") or "")
        self.lmstudio_key_input.setEchoMode(QLineEdit.Password)
        lmstudio_layout.addWidget(self.lmstudio_checkbox)
        lmstudio_layout.addWidget(self.lmstudio_key_input)

        self.openai_checkbox.stateChanged.connect(lambda: self.ensure_single_active(self.openai_checkbox))
        self.ollama_checkbox.stateChanged.connect(lambda: self.ensure_single_active(self.ollama_checkbox))
        self.lmstudio_checkbox.stateChanged.connect(lambda: self.ensure_single_active(self.lmstudio_checkbox))

        api_layout.addLayout(openai_layout)
        api_layout.addLayout(ollama_layout)
        api_layout.addLayout(lmstudio_layout)
        api_group.setLayout(api_layout)
        layout.addWidget(api_group)
        button_box = QHBoxLayout()
        save_btn = QPushButton()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(lambda: self.save_api_settings(dialog))
        cancel_btn.clicked.connect(dialog.reject)
        button_box.addWidget(save_btn)
        button_box.addWidget(cancel_btn)
        layout.addLayout(button_box)

        dialog.setLayout(layout)
        dialog.exec()

    def ensure_single_active(self, checked_checkbox):
        checkboxes = [self.openai_checkbox, self.ollama_checkbox, self.lmstudio_checkbox]
        for checkbox in checkboxes:
            if checkbox != checked_checkbox and checked_checkbox.isChecked():
                checkbox.setChecked(False)

    def save_api_settings(self, dialog):
        if self.openai_checkbox.isChecked():
            api_key = self.openai_key_input.text().strip()
            if not api_key:
                QMessageBox.warning(self, "Error", "Please enter an API key for OpenAI")
                return
            ai_api_config.update({"provider": "OpenAI", "endpoint": "https://api.openai.com/v1/chat/completions"})
            keyring.set_password("OverlayTranslate", "OpenAI", api_key)
            provider_name = "OpenAI (ChatGPT)"
        elif self.ollama_checkbox.isChecked():
            endpoint = self.ollama_endpoint_input.text().strip()
            if not endpoint:
                QMessageBox.warning(self, "Error", "Please enter an endpoint for Ollama")
                return
            ai_api_config.update({"provider": "Ollama", "endpoint": f"{endpoint.rstrip('/')}/api/chat"})
            keyring.set_password("OverlayTranslate", "Ollama", "")
            provider_name = "Ollama"
        elif self.lmstudio_checkbox.isChecked():
            api_key = self.lmstudio_key_input.text().strip()
            if not api_key:
                QMessageBox.warning(self, "Error", "Please enter an API key for LM Studio")
                return
            ai_api_config.update({"provider": "LM Studio", "endpoint": "http://localhost:1234/v1/chat/completions"})
            keyring.set_password("OverlayTranslate", "LM Studio", api_key)
            provider_name = "LM Studio (Local)"
        else:
            ai_api_config.update({"provider": None, "endpoint": None})
            for provider in ["OpenAI", "Ollama", "LM Studio"]:
                keyring.set_password("OverlayTranslate", provider, "")
            provider_name = "None"

        logging.info(f"AI API configured: {provider_name}")
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Success")
        msg_box.setText(f"{provider_name} API configured successfully.")
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: rgba(30, 30, 30, 200);
                color: #00ffcc;
                font-family: 'Roboto', Arial, sans-serif;
                font-size: 14px;
            }
            QMessageBox QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4a90e2, stop:1 #00ffcc);
                color: #ffffff;
                border-radius: 5px;
                padding: 8px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5aa1f2, stop:1 #00ffdd);
            }
            QMessageBox QPushButton:pressed {
                background: #357abd;
            }
        """)
        msg_box.exec()
        self.saveAPISettings()
        
        if not ai_api_config["provider"] and self.translate_with_ai_enabled:
            self.translate_with_ai_enabled = False
            self.translate_with_ai_toggle.setChecked(False)
            self.translate_with_ai_toggle.setText('Translate with AI: OFF')
        
        dialog.accept()

    def saveAPISettings(self):
        positions = load_window_positions()
        positions['ai_api_config'] = {k: v for k, v in ai_api_config.items() if k != "api_key"}
        save_window_positions(positions)

    def setDefaultFontSize(self):
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Set Default Font Size")
        dialog.setLabelText("Enter font size (10-100):")
        dialog.setIntValue(self.default_font_size)
        dialog.setIntMinimum(10)
        dialog.setIntMaximum(100)
        dialog.setStyleSheet(GLOBAL_STYLESHEET)
        ok = dialog.exec()
        size = dialog.intValue()
        logging.debug(f"Font size dialog returned: size={size}, ok={ok}")
        if ok:
            self.default_font_size = size
            self.capture_widget.default_font_size = size
            logging.info(f"Default font size set to: {size}")
            self.saveFontSettings()
        else:
            logging.warning("Font size selection cancelled")

    def setDefaultFontType(self):
        font_options = {
            "Roboto (Default)": "default",
            "MS YaHei (Chinese/Japanese)": "zh",
            "Malgun Gothic (Korean)": "ko"
        }
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Set Default Font Type")
        dialog.setLabelText("Choose the font for translated text:")
        dialog.setComboBoxItems(sorted(font_options.keys()))
        dialog.setStyleSheet(GLOBAL_STYLESHEET + """
            QComboBox {
                background: rgba(30, 30, 30, 150);
                color: #00ffcc;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                padding: 5px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
            }
            QComboBox QAbstractItemView {
                background: rgba(30, 30, 30, 200);
                color: #00ffcc;
                selection-background-color: #4a90e2;
                selection-color: #ffffff;
            }
        """)
        ok = dialog.exec()
        font = dialog.textValue()
        logging.debug(f"Font type dialog returned: font={font}, ok={ok}")
        if ok and font:
            self.default_font_type = font_options[font]
            self.capture_widget.default_font_type = self.default_font_type
            logging.info(f"Default font type set to: {self.default_font_type}")
            self.saveFontSettings()
        else:
            logging.warning("Font type selection cancelled")

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
        self.setFocusPolicy(Qt.StrongFocus)
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
        painter.setOpacity(0.3)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(0, 255, 204, 80)))
        painter.setPen(QPen(QColor(0, 255, 204), 2))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 15, 15)
        painter.setBrush(QBrush(QColor(0, 255, 204)))
        painter.drawRect(self.width() - self.borderRadius, self.height() - self.borderRadius, self.borderRadius, self.borderRadius)

    def captureScreen(self):
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                rect = self.rect()
                screen = QApplication.primaryScreen()
                screenshot = screen.grabWindow(0, self.x(), self.y(), rect.width(), rect.height())
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                fileName = os.path.join(SUPPORT_FOLDER, f"capture_{timestamp}.png")
                
                if not screenshot.save(fileName, format='PNG', quality=95):
                    raise Exception("Failed to save screenshot.")
                
                if not os.path.exists(fileName) or os.path.getsize(fileName) == 0:
                    raise Exception("Screenshot file is empty or does not exist.")
                
                with Image.open(fileName) as img:
                    img.verify()
                
                self.current_capture_path = fileName
                self.translateAndDisplay(fileName)
                return
            except Exception as e:
                logging.error(f"Capture attempt {attempt + 1}/{max_attempts} failed: {e}")
                if attempt == max_attempts - 1:
                    QMessageBox.critical(self, "Error", f"Capture failed after {max_attempts} attempts: {e}")
                    return
                time.sleep(0.5)

    def translateAndDisplay(self, fileName, live=False):
        if not live:
            self.control_window.translation_progress_bar.setValue(10)
        self.startTranslationWorker(fileName, live)

    def startTranslationWorker(self, fileName, live):
        if self.translation_worker and self.translation_worker.isRunning():
            self.translation_worker.stop()
        use_translate_with_ai = self.control_window.translate_with_ai_enabled and not live
        contrast_factor = self.contrast_factor
        self.translation_worker = TranslationWorker(fileName, self.control_window.source_language, self.target_language, self.fonts, use_translate_with_ai, contrast_factor, live, self)
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

        logging.debug(f"Received translated_text: '{self.translated_text}'")
        logging.debug(f"Received translated_lines: {result['translated_lines']}")

        if not live:
            timestamp = os.path.basename(fileName).replace("capture_", "").replace(".png", "")
            text_file = os.path.join(SUPPORT_FOLDER, f"text_{timestamp}.txt")
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(f"Original Text:\n{self.original_text}\n\nTranslated Text:\n{self.translated_text}")

        if not live:
            viewer = TranslatedImageViewer(
                fileName,
                result['boxes'],
                result['translated_lines'],
                self.fonts[self.default_font_type],
                self.default_font_size,
                self
            )
            viewer.exec()
        else:
            image = Image.open(fileName).convert("RGBA")
            draw = ImageDraw.Draw(image)
            boxes = result['boxes']
            translated_lines = result['translated_lines']

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
                    translated_line = translated_lines[i].strip()
                    font = ImageFont.truetype(self.fonts[self.default_font_type], self.default_font_size)
                    text_x = bbox[0]
                    text_y = bbox[1]
                    text_bbox = font.getbbox(translated_line)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                    gradient = Image.new('RGBA', (int(bbox[2] - bbox[0] + 20), int(bbox[3] - bbox[1] + 20)), (0, 0, 0, 0))
                    gradient_draw = ImageDraw.Draw(gradient)
                    gradient_draw.rectangle([(0, 0), (bbox[2] - bbox[0] + 20, bbox[3] - bbox[1] + 20)], fill=(255, 255, 255, 220))
                    gradient_draw.rectangle([(5, 5), (bbox[2] - bbox[0] + 15, bbox[3] - bbox[1] + 15)], fill=(180, 200, 255, 180))
                    image.paste(gradient, (int(bbox[0] - 10), int(bbox[1] - 10)), gradient)
                    draw.text((text_x, text_y), translated_line, font=font, fill=(0, 0, 255, 255))

            translated_file_path = fileName.replace('capture_', 'translated_')
            image.save(translated_file_path, format='PNG', quality=95)
            self.current_translation_path = translated_file_path
            shutil.move(translated_file_path, os.path.join(SUPPORT_FOLDER, os.path.basename(translated_file_path)))
            self.current_translation_path = os.path.join(SUPPORT_FOLDER, os.path.basename(translated_file_path))

    def toggleClickThrough(self):
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowTransparentForInput)
        self.show()

    def mousePressEvent(self, event):
        self.oldPos = event.globalPosition().toPoint()
        self.resizing = self.is_on_border(event.pos())
        event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if self.resizing:
                newWidth = max(event.x(), 100)
                newHeight = max(event.y(), 100)
                self.resize(newWidth, newHeight)
            else:
                delta = event.globalPosition().toPoint() - self.oldPos
                self.move(self.x() + delta.x(), self.y() + delta.y())
                self.oldPos = event.globalPosition().toPoint()
            event.accept()

    def mouseReleaseEvent(self, event):
        self.resizing = False
        event.accept()

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
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.selection_rect = QRect()
        self.dragging = False
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.updateGlow)
        self.glow_phase = 0
        # Do not start animation or show widget until explicitly activated
        self.setVisible(False)

    def resetOverlay(self):
        # Cover all screens (multi-monitor)
        desktop = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(desktop)
        self.selection_rect = QRect()
        self.dragging = False
        self.glow_phase = 0
        # Start animation only when shown
        self.animation_timer.start(30)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Dim the background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
        # Draw selection rectangle if dragging
        if not self.selection_rect.isNull():
            # Animated glow effect
            glow_color = QColor(0, 255, 204, 180 + int(50 * abs(math.sin(self.glow_phase))))
            pen = QPen(glow_color, 4)
            painter.setPen(pen)
            painter.setBrush(QColor(0, 255, 204, 60))
            painter.drawRoundedRect(self.selection_rect, 12, 12)
            # Draw dashed border for extra style
            dash_pen = QPen(QColor(255, 255, 255, 180), 2, Qt.DashLine)
            painter.setPen(dash_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(self.selection_rect, 12, 12)

    def updateGlow(self):
        self.glow_phase += 0.15
        if self.glow_phase > 2 * math.pi:
            self.glow_phase = 0
        if not self.selection_rect.isNull():
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = event.pos()
            self.selection_rect = QRect(self.origin, self.origin)
            self.dragging = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.selection_rect = QRect(self.origin, event.pos()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            if self.selection_rect.width() > 10 and self.selection_rect.height() > 10:
                self.takeSnip()
            self.selection_rect = QRect()
            self.hide()

    def takeSnip(self):
        # Grab the selected area from the screen
        screen = QApplication.primaryScreen()
        geo = self.geometry()
        rect = self.selection_rect.translated(geo.x(), geo.y())
        screenshot = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        fileName = os.path.join(SUPPORT_FOLDER, f"snip_{timestamp}.png")
        screenshot.save(fileName, format='PNG', quality=95)
        self.capture_widget.translateAndDisplay(fileName)
        self.capture_widget.show()

    def showEvent(self, event):
        self.resetOverlay()
        super().showEvent(event)
                        
class ChatWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        logging.debug("ChatWindow.__init__ started")
        self.parent = parent
        self.font_size = 14
        self.setWindowTitle("AI Terminal")
        self.setMinimumSize(400, 300)
        try:
            self.initUI()
            logging.debug("ChatWindow.__init__ completed")
        except Exception as e:
            logging.error(f"ChatWindow.__init__ failed: {e}")
            raise

    def initUI(self):
        logging.debug("Initializing ChatWindow UI")
        self.setStyleSheet(GLOBAL_STYLESHEET)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)

        self.chat_history = QTextEdit(self)
        self.chat_history.setReadOnly(True)
        self.update_chat_history_style()
        logging.debug("Chat history widget created")

        font_size_layout = QHBoxLayout()
        self.increase_font_btn = QPushButton("+")
        self.decrease_font_btn = QPushButton("-")
        icon_path_increase = os.path.join(PROJECT_ROOT, "assets/icons/zoom_in.svg")
        icon_path_decrease = os.path.join(PROJECT_ROOT, "assets/icons/zoom_out.svg")
        if os.path.exists(icon_path_increase):
            self.increase_font_btn.setIcon(QIcon(icon_path_increase))
            self.increase_font_btn.setText('')
        if os.path.exists(icon_path_decrease):
            self.decrease_font_btn.setIcon(QIcon(icon_path_decrease))
            self.decrease_font_btn.setText('')
        self.increase_font_btn.clicked.connect(self.increaseFontSize)
        self.decrease_font_btn.clicked.connect(self.decreaseFontSize)
        font_size_layout.addWidget(self.increase_font_btn)
        font_size_layout.addWidget(self.decrease_font_btn)
        logging.debug("Font size buttons added")

        self.user_input = QLineEdit(self)
        self.update_user_input_style()
        logging.debug("User input field created")

        self.send_btn = QPushButton(">")
        icon_path_send = os.path.join(PROJECT_ROOT, "assets/icons/send.svg")
        if os.path.exists(icon_path_send):
            self.send_btn.setIcon(QIcon(icon_path_send))
            self.send_btn.setText('')
        self.send_btn.clicked.connect(self.sendMessage)
        logging.debug("Send button created")

        self.user_input.returnPressed.connect(self.sendMessage)

        layout.addWidget(self.chat_history)
        layout.addLayout(font_size_layout)
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.user_input)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)
        self.setLayout(layout)
        logging.debug("ChatWindow layout set")

    def update_chat_history_style(self):
        logging.debug(f"Updating chat history style with font size: {self.font_size}")
        self.chat_history.setStyleSheet(f"""
            QTextEdit {{
                font-size: {self.font_size}px;
            }}
        """)

    def update_user_input_style(self):
        logging.debug(f"Updating user input style with font size: {self.font_size}")
        self.user_input.setStyleSheet(f"""
            QLineEdit {{
                font-size: {self.font_size}px;
            }}
        """)

    def sendMessage(self):
        user_message = self.user_input.text().strip()
        logging.debug(f"User input received: '{user_message}'")
        if user_message:
            self.chat_history.append(f"<span style='color: #e0e0e0;'>[You]></span> {user_message}")
            self.chat_history.append("<span style='color: #00ffcc;'>[AI]></span> ")
            self.chat_history.moveCursor(QtGui.QTextCursor.End)
            self.user_input.clear()
            self.send_btn.setEnabled(False)
            self.start_streaming_response(user_message)

    def start_streaming_response(self, message):
        if not ai_api_config["provider"]:
            self.chat_history.insertPlainText("Error: No AI API configured. Configure in Settings > Configure AI API.")
            self.chat_history.append("")
            self.send_btn.setEnabled(True)
            return
        logging.info(f"Starting streaming response for provider: {ai_api_config['provider']}")
        self.worker = AIStreamingWorker(message, self.parent.target_language)
        self.worker.text_chunk.connect(self.update_chat_history_in_real_time)
        self.worker.finished.connect(self.on_streaming_finished)
        self.worker.start()

    def update_chat_history_in_real_time(self, chunk):
        if len(chunk) > 200:
            logging.warning(f"Received excessively long chunk: '{chunk[:50]}...'")
            return
        self.chat_history.insertPlainText(chunk)
        self.chat_history.moveCursor(QtGui.QTextCursor.End)

    def on_streaming_finished(self, final_text):
        if final_text.startswith("Error:"):
            self.chat_history.insertPlainText(f" {final_text}")
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
    text_chunk = Signal(str)
    finished = Signal(str)

    def __init__(self, message, target_language, parent=None):
        super().__init__(parent)
        self.message = message
        self.target_language = target_language
        self.is_running = True
        self.buffer = ""
        self.min_chunk_size = 50
        self.sentence_delimiters = ['.', '!', '?', '\n']
        self.last_full_response = ""

    def run(self):
        if not self.is_running or not ai_api_config["provider"]:
            self.finished.emit("Error: No AI API configured.")
            return
        try:
            prompt = (
                f"You are a helpful assistant. Provide a concise, friendly response to the following user message in {self.target_language}. "
                f"Keep it short and relevant to the user's input: '{self.message}'"
            )
            logging.debug(f"Constructed prompt: '{prompt}'")
            headers = {"Content-Type": "application/json"}
            api_key = keyring.get_password("OverlayTranslate", ai_api_config["provider"])
            if ai_api_config["provider"] in ["OpenAI", "LM Studio"] and api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            if ai_api_config["provider"] == "OpenAI":
                data = {
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 5000,
                    "temperature": 0.5,
                    "stream": True
                }
                endpoint = ai_api_config["endpoint"]
                logging.debug(f"OpenAI request data: {json.dumps(data)}")
                response = requests.post(endpoint, headers=headers, json=data, stream=True)
            elif ai_api_config["provider"] == "Ollama":
                data = {
                    "model": "llama3.2",
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True
                }
                endpoint = ai_api_config["endpoint"]
                logging.debug(f"Ollama request data: {json.dumps(data)}")
                response = requests.post(endpoint, headers=headers, json=data, stream=True)
            elif ai_api_config["provider"] == "LM Studio":
                data = {
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 5000,
                    "temperature": 0.5,
                    "stream": True
                }
                endpoint = "http://localhost:1234/v1/chat/completions"
                logging.debug(f"LM Studio request data: {json.dumps(data)}")
                response = requests.post(endpoint, headers=headers, json=data, stream=True)

            logging.info(f"Sending request to {ai_api_config['provider']} endpoint")
            response.raise_for_status()
            full_response = ""
            for line in response.iter_lines():
                if not self.is_running:
                    break
                if line:
                    decoded_line = line.decode('utf-8').strip()
                    logging.debug(f"Received line: {decoded_line}")
                    if decoded_line and decoded_line != "[DONE]":
                        try:
                            if ai_api_config["provider"] == "OpenAI" and decoded_line.startswith("data: "):
                                chunk = decoded_line[6:]
                                if chunk != "[DONE]":
                                    json_data = json.loads(chunk)
                                    logging.debug(f"Parsed JSON: {json_data}")
                                    text_chunk = json_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if text_chunk and isinstance(text_chunk, str):
                                        logging.debug(f"Valid text chunk: '{text_chunk}'")
                                        self.buffer += text_chunk
                                        full_response += text_chunk
                            elif ai_api_config["provider"] == "Ollama":
                                json_data = json.loads(decoded_line)
                                logging.debug(f"Parsed JSON: {json_data}")
                                if json_data.get("done", False):
                                    continue
                                text_chunk = json_data.get("message", {}).get("content", "")
                                if text_chunk and isinstance(text_chunk, str):
                                    logging.debug(f"Valid text chunk: '{text_chunk}'")
                                    self.buffer += text_chunk
                                    full_response += text_chunk
                            elif ai_api_config["provider"] == "LM Studio" and decoded_line.startswith("data: "):
                                chunk = decoded_line[6:]
                                if chunk != "[DONE]":
                                    json_data = json.loads(chunk)
                                    logging.debug(f"Parsed JSON: {json_data}")
                                    text_chunk = json_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if text_chunk and isinstance(text_chunk, str):
                                        logging.debug(f"Valid text chunk: '{text_chunk}'")
                                        self.buffer += text_chunk
                                        full_response += text_chunk
                            if self.buffer and (any(self.buffer.endswith(delim) for delim in self.sentence_delimiters) or len(self.buffer) >= self.min_chunk_size):
                                logging.debug(f"Emitting buffer: '{self.buffer}'")
                                self.text_chunk.emit(self.buffer)
                                self.buffer = ""
                                time.sleep(0.3)
                        except json.JSONDecodeError as e:
                            logging.error(f"Failed to parse JSON chunk: {e}, chunk: {decoded_line}")
                        except Exception as e:
                            logging.error(f"Error processing chunk: {e}, chunk: {decoded_line}")
            if self.buffer:
                logging.debug(f"Emitting final buffer: '{self.buffer}'")
                self.text_chunk.emit(self.buffer)
            logging.info(f"Streaming complete. Full response: {full_response}")
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

class ColorBarPicker(QWidget):
    colorChanged = Signal(QColor)

    def __init__(self, initial_color=QColor(255, 255, 255), parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 60)
        self.color = initial_color
        self.hue = 0
        self.saturation = 1.0
        self.value = 1.0
        self.setMouseTracking(True)
        self.initUI()
        self.updateColorFromQColor(initial_color)

    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.hue_bar = QWidget(self)
        self.hue_bar.setFixedHeight(20)
        self.hue_bar.mousePressEvent = self.hueBarMousePress
        self.hue_bar.mouseMoveEvent = self.hueBarMouseMove
        layout.addWidget(self.hue_bar)

        self.saturation_slider = QSlider(Qt.Horizontal, self)
        self.saturation_slider.setRange(0, 100)
        self.saturation_slider.setValue(int(self.saturation * 100))
        self.saturation_slider.valueChanged.connect(self.updateSaturation)
        layout.addWidget(self.saturation_slider)

        self.setLayout(layout)

    def updateColorFromQColor(self, color):
        h, s, v, _ = color.getHsvF()
        self.hue = h
        self.saturation = s
        self.value = v
        self.color = color
        self.saturation_slider.setValue(int(self.saturation * 100))
        self.update()

    def paintEvent(self, event):
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.Antialiasing)

            hue_rect = QRect(0, 0, self.hue_bar.width(), self.hue_bar.height())
            gradient = QLinearGradient(hue_rect.topLeft(), hue_rect.topRight())
            for i in range(7):
                gradient.setColorAt(i / 6.0, QColor.fromHsvF(i / 6.0, 1.0, 1.0))
            painter.fillRect(hue_rect, gradient)

            hue_pos = self.hue * self.hue_bar.width()
            painter.setPen(QPen(Qt.white, 2))
            painter.drawLine(hue_pos, 0, hue_pos, self.hue_bar.height())

    def hueBarMousePress(self, event):
        self.updateHueFromMouse(event.pos())

    def hueBarMouseMove(self, event):
        if event.buttons() & Qt.LeftButton:
            self.updateHueFromMouse(event.pos())

    def updateHueFromMouse(self, pos):
        x = max(0, min(pos.x(), self.hue_bar.width()))
        self.hue = x / self.hue_bar.width()
        self.updateColor()
        self.update()

    def updateSaturation(self, value):
        self.saturation = value / 100.0
        self.updateColor()
        self.update()

    def updateColor(self):
        self.color = QColor.fromHsvF(self.hue, self.saturation, self.value)
        self.colorChanged.emit(self.color)

    def getColor(self):
        return self.color

    def setColor(self, color):
        self.updateColorFromQColor(color)
        self.colorChanged.emit(self.color)

class TranslatedImageViewer(QDialog):
    def __init__(self, image_path, boxes, translated_lines, font_path, default_font_size, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.boxes = boxes
        self.translated_lines = translated_lines or []
        self.font_path = font_path
        self.font_size = default_font_size
        self.original_lines = translated_lines[:]  # Copy for fallback

        # Load viewer settings with defaults
        positions = load_window_positions()
        viewer_settings = positions.get('viewer_settings', {})
        self.font_color = QColor(*viewer_settings.get('font_color', (0, 0, 255, 255)))
        self.bg_color_outer = QColor(*viewer_settings.get('bg_color_outer', (255, 255, 255, 220)))
        self.bg_color_inner = QColor(*viewer_settings.get('bg_color_inner', (180, 200, 255, 180)))
        self.font_path = viewer_settings.get('font_path', font_path)
        self.font_size = viewer_settings.get('font_size', default_font_size)

        try:
            self.original_image = Image.open(image_path).convert("RGBA")
        except Exception as e:
            logging.error(f"Failed to load image {image_path}: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load image: {e}")
            return

        self.rendered_image = self.original_image.copy()
        self.setWindowTitle("Translated Image Viewer")
        self.setStyleSheet(GLOBAL_STYLESHEET)
        self.initUI()
        self.adjustDialogSize()
        self.updateImageDisplay()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        layout.addWidget(self.image_label)

        controls_group = QGroupBox("Adjust Display")
        controls_layout = QVBoxLayout()

        font_layout = QHBoxLayout()
        font_label = QLabel("Font:")
        self.font_combo = QComboBox()
        font_db = QFontDatabase()
        self.font_family_to_path = {}
        for font_family in font_db.families():
            self.font_combo.addItem(font_family)
            font_lower = font_family.lower()
            if "roboto" in font_lower:
                font_path = get_system_font_path("default")
            elif "ms yah" in font_lower or "heiti" in font_lower:
                font_path = get_system_font_path("zh")
            elif "malgun" in font_lower or "gothic" in font_lower:
                font_path = get_system_font_path("ko")
            else:
                system = platform.system()
                font_paths = {
                    "Windows": f"C:\\Windows\\Fonts\\{font_family.lower().replace(' ', '')}.ttf",
                    "Darwin": f"/Library/Fonts/{font_family}.ttf",
                    "Linux": f"/usr/share/fonts/truetype/{font_family.lower().replace(' ', '')}.ttf"
                }
                font_path = font_paths.get(system, "arial.ttf")
                if not os.path.exists(font_path):
                    font_path = "arial.ttf"
            self.font_family_to_path[font_family] = font_path

        selected_family = None
        for family, path in self.font_family_to_path.items():
            if path == self.font_path:
                selected_family = family
                break
        if selected_family:
            self.font_combo.setCurrentText(selected_family)
        else:
            self.font_combo.setCurrentText("Arial")
            self.font_path = "arial.ttf"

        self.font_combo.currentTextChanged.connect(self.updateFont)
        font_layout.addWidget(font_label)
        font_layout.addWidget(self.font_combo)
        controls_layout.addLayout(font_layout)

        font_size_layout = QHBoxLayout()
        font_size_label = QLabel("Font Size:")
        self.font_size_slider = QSlider(Qt.Horizontal)
        self.font_size_slider.setRange(10, 100)
        self.font_size_slider.setValue(self.font_size)
        self.font_size_slider.valueChanged.connect(self.updateFontSize)
        font_size_layout.addWidget(font_size_label)
        font_size_layout.addWidget(self.font_size_slider)
        controls_layout.addLayout(font_size_layout)

        font_color_layout = QHBoxLayout()
        font_color_label = QLabel("Font Color:")
        self.font_color_picker = ColorBarPicker(self.font_color)
        self.font_color_picker.colorChanged.connect(self.updateFontColor)
        font_color_layout.addWidget(font_color_label)
        font_color_layout.addWidget(self.font_color_picker)
        controls_layout.addLayout(font_color_layout)

        bg_color_layout = QHBoxLayout()
        bg_color_label = QLabel("Background Color:")
        self.bg_color_picker = ColorBarPicker(self.bg_color_outer)
        self.bg_color_picker.colorChanged.connect(self.updateBgColor)
        bg_color_layout.addWidget(bg_color_label)
        bg_color_layout.addWidget(self.bg_color_picker)
        controls_layout.addLayout(bg_color_layout)

        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)

        button_layout = QHBoxLayout()
        self.save_close_btn = QPushButton("Save & Close")
        self.save_close_btn.clicked.connect(self.saveAndClose)
        button_layout.addStretch()
        button_layout.addWidget(self.save_close_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def adjustDialogSize(self):
        image_width = self.original_image.width
        image_height = self.original_image.height
        controls_height = 200
        self.setMinimumSize(image_width, image_height + controls_height)
        self.resize(image_width, image_height + controls_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateImageDisplay()

    def updateFont(self):
        font_name = self.font_combo.currentText()
        try:
            self.font_path = self.font_family_to_path.get(font_name, "arial.ttf")
            if not os.path.exists(self.font_path):
                logging.warning(f"Font path {self.font_path} does not exist, falling back to Arial")
                self.font_path = "arial.ttf"
            logging.debug(f"Font updated to: {font_name}, path: {self.font_path}")
            self.updateImageDisplay()
        except Exception as e:
            logging.warning(f"Failed to update font {font_name}: {e}, falling back to Arial")
            self.font_path = "arial.ttf"
            self.updateImageDisplay()

    def updateFontSize(self):
        self.font_size = self.font_size_slider.value()
        logging.debug(f"Font size updated to: {self.font_size}")
        self.updateImageDisplay()

    def updateFontColor(self, color):
        self.font_color = color
        logging.debug(f"Font color updated to: {self.font_color.getRgb()}")
        self.updateImageDisplay()

    def updateBgColor(self, color):
        self.bg_color_outer = color
        r, g, b, a = color.red(), color.green(), color.blue(), color.alpha()
        self.bg_color_inner = QColor(max(r - 20, 0), max(g - 20, 0), max(b - 20, 0), min(a + 40, 255))
        logging.debug(f"Background colors updated - outer: {self.bg_color_outer.getRgb()}, inner: {self.bg_color_inner.getRgb()}")
        self.updateImageDisplay()

    def updateImageDisplay(self):
        image = self.original_image.copy()
        draw = ImageDraw.Draw(image)

        # Convert QColor to RGBA tuples for PIL
        font_color_tuple = (self.font_color.red(), self.font_color.green(), self.font_color.blue(), self.font_color.alpha())
        bg_color_outer_tuple = (self.bg_color_outer.red(), self.bg_color_outer.green(), self.bg_color_outer.blue(), self.bg_color_outer.alpha())
        bg_color_inner_tuple = (self.bg_color_inner.red(), self.bg_color_inner.green(), self.bg_color_inner.blue(), self.bg_color_inner.alpha())

        try:
            font = ImageFont.truetype(self.font_path, self.font_size)
        except Exception as e:
            logging.warning(f"Failed to load font {self.font_path}: {e}, falling back to Arial")
            font = ImageFont.truetype("arial.ttf", self.font_size)

        if not self.boxes:
            full_text = "No text detected."
            text_bbox = font.getbbox(full_text)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            text_x = (image.width - text_width) / 2
            text_y = (image.height - text_height) / 2
            gradient = Image.new('RGBA', (text_width + 20, text_height + 20), (0, 0, 0, 0))
            gradient_draw = ImageDraw.Draw(gradient)
            gradient_draw.rectangle([(0, 0), (text_width + 20, text_height + 20)], fill=bg_color_outer_tuple)
            gradient_draw.rectangle([(5, 5), (text_width + 15, text_height + 15)], fill=bg_color_inner_tuple)
            image.paste(gradient, (int(text_x - 10), int(text_y - 10)), gradient)
            draw.text((text_x, text_y), full_text, font=font, fill=font_color_tuple)
            logging.debug("Rendered 'No text detected' message")
        else:
            for i, bbox in enumerate(self.boxes):
                translated_line = self.translated_lines[i].strip() if i < len(self.translated_lines) else ""
                if not translated_line and i < len(self.original_lines):
                    translated_line = self.original_lines[i].strip()
                    logging.debug(f"Using original line {i+1}: '{translated_line}' as fallback")

                text_x = bbox[0]
                text_y = bbox[1]
                text_bbox = font.getbbox(translated_line)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]

                gradient = Image.new('RGBA', (int(bbox[2] - bbox[0] + 20), int(bbox[3] - bbox[1] + 20)), (0, 0, 0, 0))
                gradient_draw = ImageDraw.Draw(gradient)
                gradient_draw.rectangle([(0, 0), (bbox[2] - bbox[0] + 20, bbox[3] - bbox[1] + 20)], fill=bg_color_outer_tuple)
                gradient_draw.rectangle([(5, 5), (bbox[2] - bbox[0] + 15, bbox[3] - bbox[1] + 15)], fill=bg_color_inner_tuple)
                image.paste(gradient, (int(bbox[0] - 10), int(bbox[1] - 10)), gradient)

                draw.text((text_x, text_y), translated_line, font=font, fill=font_color_tuple)
                logging.debug(f"Rendered line {i+1}: '{translated_line}' at ({text_x}, {text_y})")

        self.rendered_image = image

        # Convert PIL Image to QPixmap
        image_data = image.convert("RGB").tobytes("raw", "RGB")
        qimage = QImage(image_data, image.width, image.height, image.width * 3, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimage)
        scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)
        logging.debug("Image display updated")

    def saveAndClose(self):
        positions = load_window_positions()
        positions['viewer_settings'] = {
            'font_color': (self.font_color.red(), self.font_color.green(), self.font_color.blue(), self.font_color.alpha()),
            'bg_color_outer': (self.bg_color_outer.red(), self.bg_color_outer.green(), self.bg_color_outer.blue(), self.bg_color_outer.alpha()),
            'bg_color_inner': (self.bg_color_inner.red(), self.bg_color_inner.green(), self.bg_color_inner.blue(), self.bg_color_inner.alpha()),
            'font_path': self.font_path,
            'font_size': self.font_size
        }
        save_window_positions(positions)
        logging.info("Viewer settings saved")

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        save_path = os.path.join(SUPPORT_FOLDER, f"translated_{timestamp}.png")
        try:
            self.rendered_image.save(save_path, format='PNG', quality=95)
            logging.info(f"Saved translated image to: {save_path}")
            QMessageBox.information(self, "Saved", f"Image saved to:\n{save_path}")
        except Exception as e:
            logging.error(f"Failed to save image to {save_path}: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save image: {e}")
        self.accept()

if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        app.setFont(QFont("Roboto", 10))
        control_window = ControlWindow()
        control_window.show()
        sys.exit(app.exec())
    except Exception as e:
        logging.error(f"Application failed to start: {e}")
        print(f"Error: {e}")
        sys.exit(1)
