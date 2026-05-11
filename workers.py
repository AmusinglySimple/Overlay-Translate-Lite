# workers.py — Lite version (no AI providers, no metrics)
import os
import re
import time
import datetime
import requests
import json
import cv2
import numpy as np
from langdetect import detect
from typing import Optional, Dict, Any

from utils.ocr_utils import get_paddle_ocr_instance, APP_LANG_TO_PADDLE
from PySide6.QtCore import QThread, Signal
from utils.config import (
    logger,
    FLASK_SERVER_HOST, FLASK_SERVER_PORT, FLASK_REQUEST_TIMEOUT, FLASK_RETRY_INITIAL_DELAY,
    IMAGE_PREPROCESS_RETRY_DELAY,
    IMAGE_OPTIMIZATION_ENABLED, IMAGE_MAX_DIMENSION, IMAGE_PNG_COMPRESSION, IMAGE_SCALE_FACTOR
)
from utils.retry_utils import retry_with_backoff
from utils.image_optimizer import ImageOptimizer


def sanitize_error_message(error_message: str) -> str:
    error_message = re.sub(r'(\?|&)key=[A-Za-z0-9_-]+', r'\1key=***HIDDEN***', error_message)
    error_message = re.sub(r'Bearer [A-Za-z0-9_\-\.]+', 'Bearer ***HIDDEN***', error_message)
    error_message = re.sub(r'sk-[A-Za-z0-9_-]{20,}', 'sk-***HIDDEN***', error_message)
    error_message = re.sub(r'AIza[A-Za-z0-9_-]{30,}', 'AIza***HIDDEN***', error_message)
    error_message = re.sub(r'api[_-]?key["\']?\s*[:=]\s*["\']?[A-Za-z0-9_-]{20,}', 'api_key=***HIDDEN***', error_message, flags=re.IGNORECASE)
    return error_message


# Image optimizer for reducing image size before OCR
image_optimizer = ImageOptimizer(
    max_dimension=IMAGE_MAX_DIMENSION,
    png_compression=IMAGE_PNG_COMPRESSION,
    scale_factor=IMAGE_SCALE_FACTOR,
    enabled=IMAGE_OPTIMIZATION_ENABLED
)


class TranslationWorker(QThread):
    translation_complete = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        file_name: str,
        source_language: str,
        target_language: str,
        fonts: Dict[str, Any],
        use_translate_with_ai: bool = False,
        contrast_factor: float = 1.0,
        live: bool = False,
        parent: Optional[Any] = None
    ) -> None:
        super().__init__(parent)
        self.file_name = file_name
        self.source_language = source_language
        self.target_language = target_language
        self.fonts = fonts
        self.use_translate_with_ai = False  # Always False in Lite
        self.contrast_factor = contrast_factor
        self.live = live
        self.is_running = True
        self.min_ocr_confidence = 0.80

        if not os.path.exists(file_name):
            logger.error(f"Input file does not exist: {file_name}")
            self.is_running = False

    def stop(self) -> None:
        logger.debug(f"TranslationWorker requested to stop for file: {os.path.basename(self.file_name)}")
        self.is_running = False

    @retry_with_backoff(
        max_attempts=2,
        initial_delay=IMAGE_PREPROCESS_RETRY_DELAY,
        exceptions=(FileNotFoundError, cv2.error, OSError),
        on_retry=lambda e, attempt, delay: logger.info(
            f"Retrying image preprocessing: attempt {attempt}, waiting {delay:.1f}s"
        )
    )
    def preprocess_image(self, image_path: str) -> Optional[np.ndarray]:
        try:
            start_time = time.time()

            if IMAGE_OPTIMIZATION_ENABLED:
                optimized_path, opt_stats = image_optimizer.optimize_file(
                    image_path, in_place=True
                )
                if opt_stats and (opt_stats.was_resized or opt_stats.was_compressed):
                    logger.debug(
                        f"Image optimization: "
                        f"{opt_stats.original_dimensions[0]}x{opt_stats.original_dimensions[1]} → "
                        f"{opt_stats.optimized_dimensions[0]}x{opt_stats.optimized_dimensions[1]}, "
                        f"{opt_stats.size_reduction_percent:.1f}% size reduction"
                    )
                image_path = optimized_path

            img = cv2.imread(image_path)
            if img is None:
                raise FileNotFoundError(f"cv2.imread failed to load image at {image_path}")

            if self.contrast_factor != 1.0:
                img = cv2.convertScaleAbs(img, alpha=self.contrast_factor, beta=0)

            logger.debug(f"Preprocessing finished in {time.time() - start_time:.3f} seconds")
            return img

        except Exception as e:
            logger.error(f"Image preprocessing failed: {e}", exc_info=True)
            self.error.emit(f"Image preprocessing failed: {e}")
            return None

    def correct_ocr_text(self, text: str, lang: str = '') -> str:
        universal_corrections = {
            'OpenAl': 'OpenAI', 'CpenAl': 'OpenAI',
            'ChatGpT': 'ChatGPT',
        }
        spanish_corrections = {
            'nive penAl': 'nivel OpenAI',
            'tngresa': 'ingresa', 'seccin': 'sección', 'suscripcion': 'suscripción',
            'configuraci6n': 'configuración', 'interna*': 'interna',
            'aplicaciontodo': 'aplicación todo', 'utlizar': 'utilizar',
        }
        corrected_text = text
        for wrong, correct in universal_corrections.items():
            corrected_text = corrected_text.replace(wrong, correct)
        if lang in ('es', 'spanish'):
            for wrong, correct in spanish_corrections.items():
                corrected_text = corrected_text.replace(wrong, correct)
        return corrected_text

    def translate_with_flask(self, text: str, src_lang: str, tgt_lang: str) -> Optional[str]:
        if not self.is_running:
            return None

        @retry_with_backoff(
            max_attempts=3,
            initial_delay=FLASK_RETRY_INITIAL_DELAY,
            backoff_factor=2.0,
            exceptions=(requests.exceptions.Timeout, requests.exceptions.ConnectionError),
            on_retry=lambda e, attempt, delay: logger.info(
                f"Retrying Flask translation: attempt {attempt}, waiting {delay:.1f}s"
            )
        )
        def _make_translation_request():
            if not self.is_running:
                return None

            url = f"http://{FLASK_SERVER_HOST}:{FLASK_SERVER_PORT}/api/translate"
            data = {"text": text, "source_lang": src_lang, "target_lang": tgt_lang}

            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=data,
                timeout=FLASK_REQUEST_TIMEOUT
            )
            response.raise_for_status()
            result = response.json()

            translated_text = result.get("translated_text")
            if translated_text:
                return translated_text
            else:
                error_msg = result.get("error", "Empty translation from Flask server.")
                logger.warning(f"Translation service returned empty result: {error_msg}")
                self.error.emit(f"Translation Service Error: {error_msg}")
                return None

        try:
            return _make_translation_request()
        except requests.exceptions.Timeout:
            logger.error("Translation request timed out after all retries")
            self.error.emit("Translation Service Error: Request timed out after retries.")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to translation service after all retries")
            self.error.emit("Translation Service Error: Cannot connect to local server. Is it running?")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Translation request failed: {e}")
            self.error.emit(f"Translation Service Request Error: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from translation service: {e}")
            self.error.emit("Translation Service Error: Invalid response format.")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in translation: {e}", exc_info=True)
            self.error.emit(f"Translation Error: {e}")
            return None

    def run(self) -> None:
        if not self.is_running:
            return

        start_time = time.time()
        result = {
            'file_name': self.file_name, 'original_text': '', 'translated_text': '',
            'error_message': '', 'boxes': [], 'translated_lines': [],
            'live': self.live, 'timestamp': datetime.datetime.now()
        }

        try:
            processed_image_np = self.preprocess_image(self.file_name)

            actual_source_lang = self.source_language
            if actual_source_lang == 'auto':
                try:
                    paddle_instance_auto = get_paddle_ocr_instance('ch')
                    if not paddle_instance_auto:
                        raise Exception("Could not get multilingual OCR instance.")
                    ocr_results = paddle_instance_auto.ocr(processed_image_np, cls=True)
                    prelim_text = " ".join([line[1][0] for line in ocr_results[0]]) if ocr_results and ocr_results[0] else ""
                    if len(prelim_text.strip()) > 10:
                        actual_source_lang = detect(prelim_text[:1000])
                        logger.info(f"Detected source language (app code): {actual_source_lang}")
                    else:
                        actual_source_lang = 'en'
                except Exception as lang_detect_err:
                    logger.warning(f"Language detection failed: {lang_detect_err}. Falling back to English.")
                    actual_source_lang = 'en'

            paddle_lang_code = APP_LANG_TO_PADDLE.get(actual_source_lang, 'en')
            paddle_instance_final = get_paddle_ocr_instance(paddle_lang_code)
            if not paddle_instance_final:
                raise Exception(f"Could not get OCR instance for '{paddle_lang_code}'.")

            if 'ocr_results' not in locals() or paddle_lang_code != 'ch':
                ocr_results = paddle_instance_final.ocr(processed_image_np, cls=True)

            if not self.is_running:
                return

            lines, boxes, confidences = [], [], []
            if ocr_results and ocr_results[0] is not None:
                for line_data in ocr_results[0]:
                    box_coords, (text, confidence) = line_data[0], line_data[1]
                    if confidence >= self.min_ocr_confidence and text.strip():
                        x_coords = [p[0] for p in box_coords]
                        y_coords = [p[1] for p in box_coords]
                        left, top, right, bottom = min(x_coords), min(y_coords), max(x_coords), max(y_coords)
                        lines.append(text)
                        boxes.append((left, top, right, bottom))
                        confidences.append(confidence)

            if not lines:
                result['translated_text'] = "No text detected."
            else:
                original_text = self.correct_ocr_text('\n'.join(lines), lang=actual_source_lang)
                result.update({'original_text': original_text, 'boxes': boxes})

                # Always use Flask (local Argos) translation in Lite
                translated_text = self.translate_with_flask(original_text, actual_source_lang, self.target_language)

                result['translated_text'] = translated_text if translated_text else "Translation Failed."

                if translated_text and "Translation Failed" not in translated_text:
                    translated_lines_raw = translated_text.split('\n')
                    result['translated_lines'] = (translated_lines_raw + [""] * len(boxes))[:len(boxes)]
                else:
                    result['translated_lines'] = [""] * len(boxes)

        except Exception as e:
            logger.error(f"Error in TranslationWorker run: {e}", exc_info=True)
            sanitized_error = sanitize_error_message(str(e))
            result['error_message'] = sanitized_error
            result.setdefault('translated_text', f"Error: {sanitized_error}")
            self.error.emit(sanitized_error)
        finally:
            duration = time.time() - start_time
            if self.is_running:
                logger.info(f"TranslationWorker finished in {duration:.3f}s for {os.path.basename(self.file_name)}.")
                self.translation_complete.emit(result)
