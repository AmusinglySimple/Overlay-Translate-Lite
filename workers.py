import os
import re
import time
import datetime
import logging
import requests
import json
import cv2
import numpy as np
import keyring # Moved here
from PIL import Image, ImageDraw, ImageFont, ImageOps
from langdetect import detect

# --- MODIFIED: Import pytesseract and language map ---
import pytesseract
from utils.ocr_utils import APP_LANG_TO_TESSERACT, get_tesseract_langs
# --- END MODIFIED ---

from PySide6.QtCore import QThread, Signal, QEventLoop, Qt
from PySide6.QtWidgets import QMessageBox

from utils.config import SUPPORT_FOLDER, ai_api_config, logger, ensure_support_folder
# --- MODIFIED: Removed get_ocr_instance ---
# from utils.ocr_utils import get_ocr_instance # Import the getter
# --- END MODIFIED ---


# Conditional import for SSEClient
try:
    from sseclient import SSEClient
except ImportError:
    SSEClient = None
    logger.warning("sseclient-py not found. AI Chat streaming for some providers might not work.")
    logger.warning("Install it using: pip install sseclient-py")


# --- TranslationWorker Thread ---
class TranslationWorker(QThread):
    translation_complete = Signal(dict)
    error = Signal(str)

    def __init__(self, file_name, source_language, target_language, fonts, use_translate_with_ai=False, contrast_factor=1.0, live=False, parent=None):
        super().__init__(parent)
        self.file_name = file_name
        self.source_language = source_language # App language code (e.g., 'en', 'es', 'ch')
        self.target_language = target_language
        self.fonts = fonts
        self.use_translate_with_ai = use_translate_with_ai
        self.contrast_factor = contrast_factor
        self.live = live
        self.is_running = True
        self.min_ocr_confidence = 50 # Configurable confidence threshold

        if not os.path.exists(file_name):
            logger.error(f"Input file does not exist: {file_name}")
            self.is_running = False

    def stop(self):
        logger.debug(f"TranslationWorker requested to stop for file: {os.path.basename(self.file_name)}")
        self.is_running = False

    def preprocess_image(self, image):
        try:
            start_time = time.time()
            logger.debug(f"Preprocessing image: {image.size}, mode: {image.mode}")
            if image.mode != 'RGB':
                image = image.convert('RGB')
            if self.contrast_factor != 1.0:
                 img_array = np.array(image)
                 img_array = cv2.convertScaleAbs(img_array, alpha=self.contrast_factor, beta=0)
                 image = Image.fromarray(img_array)
            # --- MODIFIED: Tesseract often prefers grayscale, not binary ---
            # gray_image = image.convert('L')
            # img_array = np.array(gray_image)
            # Tesseract's internal Otsu thresholding is often good enough.
            # Applying adaptive thresholding here can sometimes hurt Tesseract.
            # Let's try passing the enhanced RGB or simple Grayscale directly.
            # If results are poor, consider adding thresholding back.
            gray_image = image.convert('L') # Convert to grayscale
            # --- END MODIFIED ---
            logger.debug(f"Preprocessing finished in {time.time() - start_time:.3f} seconds")
            # --- MODIFIED: Return grayscale image ---
            return gray_image
            # --- END MODIFIED ---
        except Exception as e:
            logger.error(f"Image preprocessing failed: {e}", exc_info=True)
            self.error.emit(f"Image preprocessing failed: {e}")
            raise

    def correct_ocr_text(self, text):
        # (Keep the existing correct_ocr_text method here)
        corrections = {
            'OpenAl': 'OpenAI', 'CpenAl': 'OpenAI', 'nive penAl': 'nivel OpenAI',
            'tngresa': 'ingresa', 'seccin': 'sección', 'suscripcion': 'suscripción',
            'ChatGpT': 'ChatGPT', 'configuraci6n': 'configuración', 'interna*': 'interna',
            'aplicaciontodo': 'aplicación todo', 'utlizar': 'utilizar', 'Ollama ': 'Ollama',
            # Add Tesseract-specific common errors if observed
        }
        corrected_text = text
        for wrong, correct in corrections.items():
            corrected_text = corrected_text.replace(wrong, correct)
        if corrected_text != text:
            logger.debug(f"OCR Correction applied: '{text}' -> '{corrected_text}'")
        return corrected_text

    def translate_with_ai(self, original_text, num_lines):
        # (This method remains unchanged - it calls AITranslationWorker)
        if not self.is_running: return None
        if not ai_api_config.get("provider"):
            logger.warning("No AI API provider configured; skipping AI translation.")
            return None

        logger.debug(f"Starting AI translation via AITranslationWorker for {num_lines} lines.")
        try:
            loop = QEventLoop()
            # Pass required args to AITranslationWorker
            ai_worker = AITranslationWorker(
                text=original_text, # Pass the text explicitly
                source_language=self.source_language, # Pass source language
                target_language=self.target_language, # Pass target language
                num_lines=num_lines
            )
            translated_text = None
            error_message = None

            def on_translation_complete(text):
                nonlocal translated_text
                translated_text = text
                logger.debug(f"Received AI translation: '{text[:100]}...'")
                if loop.isRunning(): loop.quit()

            def on_error(error):
                nonlocal error_message
                error_message = error
                logger.error(f"AI translation error: {error}")
                if loop.isRunning(): loop.quit()

            def on_finished():
                if loop.isRunning(): loop.quit()

            ai_worker.translation_complete.connect(on_translation_complete)
            ai_worker.error.connect(on_error)
            ai_worker.finished.connect(on_finished)
            ai_worker.start()
            loop.exec()

            if not self.is_running:
                 logger.warning("TranslationWorker stopped during AI translation.")
                 ai_worker.stop()
                 return None

            if error_message:
                logger.error(f"AI translation failed: {error_message}")
                self.error.emit(f"AI Translation Error: {error_message}")
                return None
            if translated_text is None:
                logger.error("No translation received from AI worker (timed out or other issue).")
                self.error.emit("AI Translation Error: No response received.")
                return None

            logger.debug(f"AI translation successful, returning: '{translated_text[:100]}...'")
            return translated_text

        except Exception as e:
            logger.error(f"Exception during AI translation initiation or waiting: {e}", exc_info=True)
            self.error.emit(f"AI Translation Exception: {e}")
            return None


    def translate_with_flask(self, text, src_lang, tgt_lang):
        # (This method remains unchanged - it calls the Flask backend)
        if not self.is_running: return None
        url = "http://127.0.0.1:5000/api/translate"
        data = {"text": text, "source_lang": src_lang, "target_lang": tgt_lang}
        logger.debug(f"Sending translation request to Flask: {data}")
        try:
            response = requests.post(url, headers={"Content-Type": "application/json"}, json=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            translated_text = result.get("translated_text")
            if translated_text:
                 logger.debug(f"Flask translation successful: '{translated_text[:100]}...'")
                 return translated_text
            else:
                 error_msg = result.get("error", "Empty translation from Flask server.")
                 logger.error(f"Flask server translation failed: {error_msg}")
                 self.error.emit(f"Translation Service Error: {error_msg}")
                 return None
        except requests.exceptions.ConnectionError:
            logger.error(f"Flask server connection failed at {url}.")
            self.error.emit("Translation Service Unavailable (Connection Error)")
            return None
        except requests.exceptions.Timeout:
            logger.error(f"Flask server request timed out ({url}).")
            self.error.emit("Translation Service Timed Out")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Flask server request failed: {e}", exc_info=True)
            self.error.emit(f"Translation Service Request Error: {e}")
            return None
        except json.JSONDecodeError:
             logger.error(f"Failed to decode JSON response from Flask server: {response.text[:200]}")
             self.error.emit("Translation Service Error: Invalid response format.")
             return None

    # --- MODIFIED: run method with Tesseract ---
    def run(self):
        if not self.is_running:
            logger.warning(f"TranslationWorker.run cancelled before start for {os.path.basename(self.file_name)}.")
            return

        start_time = time.time()
        result = {'file_name': self.file_name, 'original_text': '', 'translated_text': '', 'error_message': '', 'boxes': [], 'translated_lines': [], 'live': self.live, 'timestamp': datetime.datetime.now()}
        temp_image_for_tesseract = None # Use the preprocessed image directly

        try:
            try:
                image = Image.open(self.file_name)
                image.load()
                logger.debug(f"Image loaded: {self.file_name}, size: {image.size}, mode: {image.mode}")
            except FileNotFoundError:
                raise Exception(f"Image file not found: {self.file_name}")
            except Exception as e:
                raise Exception(f"Failed to load image '{os.path.basename(self.file_name)}': {e}")

            try:
                # Preprocess image (returns grayscale PIL image)
                temp_image_for_tesseract = self.preprocess_image(image)
            except Exception as e:
                raise Exception("Image preprocessing failed.") # Error already logged

            # --- Determine Tesseract Language ---
            tesseract_lang_code = 'eng' # Default
            actual_source_lang = self.source_language # App code ('en', 'es', 'auto'...)

            if actual_source_lang == 'auto':
                # Need original text first for detection, perform preliminary OCR
                try:
                    logger.debug("Performing preliminary OCR for language detection...")
                    prelim_text = pytesseract.image_to_string(temp_image_for_tesseract, lang='eng') # Detect using English base
                    if len(prelim_text.strip()) > 10: # Need enough text
                        detected_app_lang = detect(prelim_text[:1000])
                        actual_source_lang = detected_app_lang # Update app lang code
                        logger.info(f"Detected source language (app code): {actual_source_lang}")
                        # Map detected app code to tesseract code
                        tesseract_lang_code = APP_LANG_TO_TESSERACT.get(actual_source_lang, 'eng')
                    else:
                        logger.info("Text too short for auto-detection, using English ('eng').")
                        actual_source_lang = 'en' # Update app lang code
                        tesseract_lang_code = 'eng'
                except Exception as lang_detect_err:
                    logger.warning(f"Language detection failed: {lang_detect_err}. Falling back to English ('eng').")
                    actual_source_lang = 'en' # Update app lang code
                    tesseract_lang_code = 'eng'
                    self.error.emit("Language detection failed, using English.")
            else:
                # Map the specified app language code to Tesseract code
                tesseract_lang_code = APP_LANG_TO_TESSERACT.get(actual_source_lang, 'eng')
                if tesseract_lang_code == 'eng' and actual_source_lang != 'en':
                    logger.warning(f"No Tesseract mapping for '{actual_source_lang}', defaulting to 'eng'.")


            # --- Check if Tesseract language pack is available ---
            installed_langs = get_tesseract_langs()
            required_langs = tesseract_lang_code.split('+')
            missing_langs = [lang for lang in required_langs if lang not in installed_langs]
            if missing_langs:
                logger.error(f"Missing Tesseract language pack(s): {missing_langs} (Required: {tesseract_lang_code}). Installed: {installed_langs}")
                raise Exception(f"Missing Tesseract language pack(s): {', '.join(missing_langs)}. Please install them.")


            logger.debug(f"Starting Tesseract OCR with lang='{tesseract_lang_code}' and psm=6")
            ocr_start_time = time.time()
            try:
                # Use image_to_data to get bounding boxes and text
                ocr_data = pytesseract.image_to_data(
                    temp_image_for_tesseract,
                    lang=tesseract_lang_code,
                    config='--psm 6', # Assume a single uniform block of text
                    output_type=pytesseract.Output.DICT
                )
                logger.debug(f"Tesseract finished in {time.time() - ocr_start_time:.3f} seconds.")
            except pytesseract.TesseractNotFoundError:
                 logger.error("Tesseract executable not found or not configured correctly.")
                 raise Exception("Tesseract not found. Please ensure it's installed and configured.")
            except pytesseract.TesseractError as ocr_err:
                 logger.error(f"Tesseract processing error: {ocr_err}", exc_info=True)
                 raise Exception(f"Tesseract OCR failed: {ocr_err}")
            except Exception as e:
                 logger.error(f"Unexpected error during Tesseract processing: {e}", exc_info=True)
                 raise Exception(f"Unexpected OCR error: {e}")


            if not self.is_running:
                logger.warning("TranslationWorker stopped during OCR.")
                return

            # --- Parse Tesseract Results ---
            lines = []
            boxes = []
            confidences = []
            words_by_line = {} # Group words by line number

            n_boxes = len(ocr_data['level'])
            for i in range(n_boxes):
                text = ocr_data['text'][i].strip()
                conf = int(ocr_data['conf'][i])

                # Filter out low-confidence words or empty strings
                if conf >= self.min_ocr_confidence and text:
                    line_num = ocr_data['line_num'][i]
                    # block_num = ocr_data['block_num'][i] # Could use block/par for more complex grouping
                    # par_num = ocr_data['par_num'][i]
                    # word_key = (block_num, par_num, line_num)
                    word_key = line_num # Simple grouping by line number

                    if word_key not in words_by_line:
                        words_by_line[word_key] = []

                    words_by_line[word_key].append({
                        'text': ocr_data['text'][i], # Keep original spacing for joining
                        'conf': conf,
                        'left': ocr_data['left'][i],
                        'top': ocr_data['top'][i],
                        'width': ocr_data['width'][i],
                        'height': ocr_data['height'][i]
                    })

            if not words_by_line:
                logger.warning("Tesseract detected no text with sufficient confidence.")
                result['translated_text'] = "No text detected."
            else:
                # Reconstruct lines and calculate bounding boxes
                total_confidence = 0
                total_words = 0
                sorted_line_keys = sorted(words_by_line.keys())

                for line_key in sorted_line_keys:
                    line_words = words_by_line[line_key]
                    if not line_words: continue

                    line_text = " ".join([w['text'] for w in line_words])
                    line_conf = sum(w['conf'] for w in line_words) / len(line_words)

                    # Calculate bounding box for the entire line
                    min_left = min(w['left'] for w in line_words)
                    min_top = min(w['top'] for w in line_words)
                    max_right = max(w['left'] + w['width'] for w in line_words)
                    max_bottom = max(w['top'] + w['height'] for w in line_words)

                    lines.append(line_text)
                    boxes.append((min_left, min_top, max_right, max_bottom))
                    confidences.append(line_conf)
                    total_confidence += sum(w['conf'] for w in line_words)
                    total_words += len(line_words)

                if not lines:
                    logger.warning("No valid lines reconstructed after confidence filtering.")
                    result['translated_text'] = "No text detected (low confidence)."
                else:
                    original_text = '\n'.join(lines)
                    original_text = self.correct_ocr_text(original_text) # Apply corrections
                    result['original_text'] = original_text
                    result['boxes'] = boxes
                    avg_confidence = total_confidence / total_words if total_words else 0
                    logger.info(f"Tesseract OCR successful: Reconstructed {len(lines)} lines. Avg Word Confidence: {avg_confidence:.2f}")
                    logger.debug(f"Original Text:\n{original_text}")

                    # --- Translation (remains mostly the same) ---
                    translated_text = None
                    if self.use_translate_with_ai and not self.live:
                        logger.info("Attempting translation with AI...")
                        translated_text = self.translate_with_ai(original_text, len(lines))
                        if translated_text:
                            logger.info("AI translation successful.")
                        else:
                            logger.warning("AI translation failed or returned empty. Falling back to Flask server.")

                    if translated_text is None:
                        logger.info("Attempting translation with Flask server...")
                        # Use the *detected* or specified actual_source_lang (app code) for Flask
                        translated_text = self.translate_with_flask(original_text, actual_source_lang, self.target_language)
                        if translated_text:
                            logger.info("Flask translation successful.")
                        else:
                             logger.error("Flask translation also failed.")
                             translated_text = "Translation failed (Service Unavailable)."

                    result['translated_text'] = translated_text if translated_text else "Translation Failed."
                    logger.debug(f"Final translated_text for result: '{result['translated_text'][:100]}...'")

                    # --- Line Alignment (remains the same) ---
                    if translated_text and translated_text != "Translation failed (Service Unavailable)." and translated_text != "No text detected.":
                        translated_lines_raw = translated_text.split('\n')
                        logger.debug(f"Raw translated lines: {len(translated_lines_raw)}")
                        num_boxes = len(boxes)
                        num_translated_raw = len(translated_lines_raw)

                        if num_translated_raw == num_boxes:
                            result['translated_lines'] = translated_lines_raw
                            logger.debug("Translated line count matches box count.")
                        else:
                            logger.warning(f"Mismatch: {num_translated_raw} translated lines for {num_boxes} boxes. Attempting redistribution.")
                            if num_translated_raw < num_boxes:
                                logger.debug(f"Padding translated lines with {num_boxes - num_translated_raw} empty strings.")
                                result['translated_lines'] = translated_lines_raw + [""] * (num_boxes - num_translated_raw)
                            else:
                                logger.debug(f"Truncating translated lines from {num_translated_raw} to {num_boxes}.")
                                result['translated_lines'] = translated_lines_raw[:num_boxes]
                    else:
                        result['translated_lines'] = [""] * len(boxes)

        except Exception as e:
            logger.error(f"Error in TranslationWorker run: {e}", exc_info=True)
            result['error_message'] = str(e)
            if not result.get('translated_text'):
                result['translated_text'] = f"Error: {e}"
            self.error.emit(result['error_message'])

        finally:
            # No temporary file saved for Tesseract, just used the PIL image in memory
            pass

            if self.is_running:
                total_time = time.time() - start_time
                logger.info(f"TranslationWorker finished in {total_time:.3f} seconds for {os.path.basename(self.file_name)}.")
                logger.debug(f"Emitting result: translated_lines count = {len(result.get('translated_lines', []))}")
                self.translation_complete.emit(result)
            else:
                logger.warning(f"TranslationWorker finished but was stopped, not emitting result for {os.path.basename(self.file_name)}.")


# --- AITranslationWorker Thread ---
# (This class remains unchanged as it doesn't directly interact with OCR)
class AITranslationWorker(QThread):
    translation_complete = Signal(str)
    error = Signal(str)

    def __init__(self, text, source_language, target_language, num_lines, parent=None):
        super().__init__(parent)
        self.text = text
        self.source_language = source_language # App lang code
        self.target_language = target_language # App lang code
        self.num_lines = num_lines
        self.is_running = True

    def stop(self):
        logger.debug("AITranslationWorker requested to stop.")
        self.is_running = False

    def run(self):
        if not self.is_running:
            logger.warning("AITranslationWorker cancelled before start.")
            return

        if not ai_api_config.get("provider"):
            self.error.emit("No AI API provider configured.")
            logger.error("AI translation run attempted without configured provider.")
            return

        start_time = time.time()
        logger.info(f"Starting AI translation ({ai_api_config['provider']}) for {self.num_lines} lines...")

        try:
            # Use simple lang codes for prompt, AI should understand common ones
            target_lang_name = self.target_language
            source_lang_name = self.source_language if self.source_language != 'auto' else 'auto-detected'

            lines = self.text.split('\n')
            lines_to_process = lines[:self.num_lines]
            numbered_text = '\n'.join(f"{i+1}. {line}" for i, line in enumerate(lines_to_process))

            prompt = (
                f"Translate the following numbered text from {source_lang_name} to {target_lang_name}. "
                f"Provide a translation for each numbered line. Maintain the original line breaks and meaning. "
                f"The output MUST contain exactly {self.num_lines} numbered lines, corresponding to the input lines. "
                f"If an input line is empty or untranslatable, provide an empty translation for that number (e.g., '3. '). "
                f"Do not add any introductory text, summaries, or explanations. Only provide the numbered translated lines.\n\n"
                f"Input Text:\n{numbered_text}\n\n"
                f"Translated Text ({target_lang_name}):"
            )
            logger.debug(f"AI Translation Prompt:\n---PROMPT START---\n{prompt}\n---PROMPT END---")

            headers = {"Content-Type": "application/json"}
            api_key = None
            provider = ai_api_config["provider"]
            endpoint = ai_api_config["endpoint"]

            if provider in ["OpenAI", "LM Studio"]:
                 try:
                     api_key = keyring.get_password("OverlayTranslate", provider)
                     if api_key:
                         headers["Authorization"] = f"Bearer {api_key}"
                     else:
                         if provider == "OpenAI":
                            raise ValueError(f"API key for {provider} not found in keyring.")
                         else:
                            logger.warning(f"API key for {provider} not found, proceeding without Authorization header.")
                 except Exception as key_err:
                     raise ValueError(f"Failed to retrieve API key for {provider}: {key_err}")

            response = None
            max_tokens = max(150 * self.num_lines, 200)

            # --- Model selection logic (keep as is) ---
            # (OpenAI, Ollama, LM Studio request blocks remain the same)
            # ...
            if provider == "OpenAI":
                data = { "model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens, "temperature": 0.3, "n": 1, "stop": None }
                logger.debug(f"Sending request to OpenAI: {endpoint}, data: {data}")
                response = requests.post(endpoint, headers=headers, json=data, timeout=60)
            elif provider == "Ollama":
                # Use a reasonable default model or make it configurable
                model_name = "llama3" # Example default
                if endpoint.endswith('/api/chat'):
                     data = { "model": model_name, "messages": [{"role": "user", "content": prompt}],
                              "stream": False, "options": { "temperature": 0.3, "num_predict": max_tokens } }
                     logger.debug(f"Sending request to Ollama (chat): {endpoint}, data: {data}")
                     response = requests.post(endpoint, headers=headers, json=data, timeout=60)
                elif endpoint.endswith('/api/generate'):
                     data = { "model": model_name, "prompt": prompt, "stream": False,
                              "options": { "temperature": 0.3, "num_predict": max_tokens } }
                     logger.debug(f"Sending request to Ollama (generate): {endpoint}, data: {data}")
                     response = requests.post(endpoint, headers=headers, json=data, timeout=60)
                else:
                    raise ValueError("Ollama endpoint must end with /api/chat or /api/generate")
            elif provider == "LM Studio":
                data = { "model": "loaded-model", # LM Studio uses placeholder
                         "messages": [{"role": "user", "content": prompt}],
                         "max_tokens": max_tokens, "temperature": 0.3, "stream": False }
                logger.debug(f"Sending request to LM Studio: {endpoint}, data: {data}")
                response = requests.post(endpoint, headers=headers, json=data, timeout=60)
            else:
                raise ValueError(f"Unsupported AI provider: {provider}")
            # --- End model selection ---


            if not self.is_running: return

            response.raise_for_status()
            result = response.json()
            logger.debug(f"AI Response JSON: {result}")

            raw_translated_text = ""
            # --- Response parsing (keep as is) ---
            # (Parsing logic for OpenAI, Ollama, LM Studio remains the same)
            # ...
            if provider == "OpenAI" or provider == "LM Studio":
                if "choices" in result and len(result["choices"]) > 0 and "message" in result["choices"][0] and "content" in result["choices"][0]["message"]:
                    raw_translated_text = result["choices"][0]["message"]["content"]
                else:
                    logger.error(f"Unexpected response structure from {provider}: {result}")
                    raise ValueError(f"Invalid response format from {provider}.")
            elif provider == "Ollama":
                if endpoint.endswith('/api/chat'):
                    if "message" in result and "content" in result["message"]:
                        raw_translated_text = result["message"]["content"]
                    else:
                         logger.error(f"Unexpected response structure from Ollama Chat: {result}")
                         raise ValueError("Invalid response format from Ollama Chat.")
                elif endpoint.endswith('/api/generate'):
                     if "response" in result:
                        raw_translated_text = result["response"]
                     else:
                         logger.error(f"Unexpected response structure from Ollama Generate: {result}")
                         raise ValueError("Invalid response format from Ollama Generate.")
            # --- End response parsing ---

            if not raw_translated_text:
                logger.warning("AI response content is empty.")
                raise ValueError("AI returned an empty response.")

            logger.debug(f"Raw AI translated text:\n---RAW START---\n{raw_translated_text}\n---RAW END---")

            # --- Numbered line parsing (keep as is) ---
            # (Regex and fallback logic remains the same)
            # ...
            translated_lines = [""] * self.num_lines
            lines_found = 0
            line_pattern = re.compile(r"^\s*(\d+)[\.\)]\s*(.*)")

            for line in raw_translated_text.split('\n'):
                line = line.strip()
                if not line: continue
                match = line_pattern.match(line)
                if match:
                    try:
                        line_num_str = match.group(1)
                        content = match.group(2).strip()
                        line_index = int(line_num_str) - 1
                        if 0 <= line_index < self.num_lines:
                            translated_lines[line_index] = content
                            lines_found += 1
                        else:
                            logger.warning(f"Parsed line number {line_index + 1} is out of expected range (1-{self.num_lines}). Ignoring: '{line}'")
                    except ValueError:
                        logger.warning(f"Could not convert parsed line number '{line_num_str}' to int. Ignoring: '{line}'")
                    except Exception as parse_err:
                         logger.error(f"Error processing matched line '{line}': {parse_err}")
                else:
                    logger.warning(f"AI response line did not match expected number format: '{line}'")

            logger.debug(f"Parsed translated lines (found {lines_found}): {translated_lines}")

            if lines_found == 0 and self.num_lines > 0:
                 logger.warning("Regex failed to parse lines, attempting simple newline split as fallback.")
                 raw_lines_split = raw_translated_text.strip().split('\n')
                 if len(raw_lines_split) == self.num_lines:
                     logger.info("Fallback split matches line count. Using.")
                     translated_lines = [l.strip() for l in raw_lines_split]
                 else:
                     logger.error("Fallback split also failed. AI response did not follow required format.")
                     # Don't raise error, just return the joined raw text perhaps? Or empty?
                     # Let's return the best guess (joined lines)
                     final_text = '\n'.join(raw_lines_split) # Use fallback result
                     logger.warning(f"Returning fallback joined text as final: {final_text[:100]}...")
                     # This might cause line mismatch later, but better than nothing?
                     # Alternative: raise ValueError("AI response did not follow the required numbered format.")

            # If regex worked or fallback split matched count:
            if lines_found > 0 or (lines_found == 0 and len(raw_lines_split) == self.num_lines):
                 final_text = '\n'.join(translated_lines)
            # --- End numbered line parsing ---


            logger.info(f"AI translation processing finished in {time.time() - start_time:.3f} seconds.")
            logger.debug(f"Final processed AI text:\n---FINAL START---\n{final_text}\n---FINAL END---")

            if self.is_running:
                self.translation_complete.emit(final_text)

        except requests.exceptions.RequestException as e:
            error_msg = f"API Request Error: {e}"
            logger.error(f"AI translation request failed ({provider}): {e}", exc_info=True)
            if self.is_running: self.error.emit(error_msg)
        except ValueError as e:
            error_msg = f"AI Processing Error: {e}"
            logger.error(f"AI processing error ({provider}): {e}", exc_info=True)
            if self.is_running: self.error.emit(error_msg)
        except RuntimeError as e:
             error_msg = f"Runtime Error: {e}"
             logger.error(f"AI streaming runtime error ({provider}): {e}", exc_info=True)
             if self.is_running: self.error.emit(error_msg)
        except Exception as e:
            error_msg = f"Unexpected Error: {e}"
            logger.error(f"Unexpected error in AI translation ({provider}): {e}", exc_info=True)
            if self.is_running: self.error.emit(error_msg)
        finally:
            self.is_running = False



# --- AIStreamingWorker Thread ---
# (This class remains unchanged as it doesn't directly interact with OCR)
class AIStreamingWorker(QThread):
    # ... (Keep the entire class code as it was) ...
    # Make sure imports for keyring, re, requests, json, time are present at the top of workers.py
    # Make sure sseclient import is handled (done at top of file)
    # Update logging to use 'logger' from config
    # Ensure ai_api_config is imported from config
    text_chunk = Signal(str)
    finished_stream = Signal(str)
    error_stream = Signal(str)

    def __init__(self, message, target_language, parent=None):
        super().__init__(parent)
        self.message = message
        self.target_language = target_language
        self.is_running = True

    def stop(self):
        logger.debug("AIStreamingWorker requested to stop.")
        self.is_running = False

    def run(self):
        if not self.is_running:
            logger.warning("AIStreamingWorker cancelled before start.")
            return

        provider = ai_api_config.get("provider")
        endpoint = ai_api_config.get("endpoint")
        if not provider or not endpoint:
            self.error_stream.emit("No AI API configured.")
            logger.error("AI streaming run attempted without configured provider.")
            return

        start_time = time.time()
        logger.info(f"Starting AI stream request ({provider}). Target Endpoint: {endpoint}")
        full_response_text = ""
        client = None # Initialize client here for finally block

        try:
            # Use simple lang codes for prompt
            target_lang_name = self.target_language

            prompt = ( f"User: {self.message}\n"
                       f"Assistant (concise response in {target_lang_name}):" )
            logger.debug(f"AI Chat Prompt:\n---PROMPT START---\n{prompt}\n---PROMPT END---")

            headers = {"Content-Type": "application/json"}
            api_key = None

            if provider in ["OpenAI", "LM Studio"]:
                try:
                    api_key = keyring.get_password("OverlayTranslate", provider)
                    if api_key: headers["Authorization"] = f"Bearer {api_key}"
                    elif provider == "OpenAI": raise ValueError(f"API key for {provider} not found.")
                    else: logger.warning(f"API key for {provider} not found/provided, proceeding without.")
                except Exception as key_err:
                    raise ValueError(f"Failed to retrieve API key for {provider}: {key_err}")

            response = None
            max_tokens = 1024 # Max tokens for chat response
            can_stream = True
            model_name = "gpt-4o-mini" # Default for OpenAI

            if provider == "OpenAI":
                headers["Accept"] = "text/event-stream"
                data = { "model": model_name, "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens, "temperature": 0.6, "stream": True }
                logger.debug(f"Sending stream request to OpenAI: {endpoint}")
                response = requests.post(endpoint, headers=headers, json=data, stream=True, timeout=60)
            elif provider == "Ollama":
                model_name = "llama3" # Default for Ollama
                if endpoint.endswith('/api/chat'):
                    headers["Accept"] = "application/x-ndjson"
                    data = { "model": model_name, "messages": [{"role": "user", "content": prompt}],
                            "stream": True, "options": { "temperature": 0.6, "num_predict": max_tokens } }
                    logger.debug(f"Sending stream request to Ollama (chat): {endpoint}")
                    response = requests.post(endpoint, headers=headers, json=data, stream=True, timeout=60)
                elif endpoint.endswith('/api/generate'):
                    can_stream = False # /generate endpoint typically doesn't stream
                    data = { "model": model_name, "prompt": prompt, "stream": False,
                            "options": { "temperature": 0.6, "num_predict": max_tokens } }
                    logger.debug(f"Sending non-stream request to Ollama (generate): {endpoint}")
                    response = requests.post(endpoint, headers=headers, json=data, timeout=60)
                else:
                    raise ValueError("Ollama endpoint must end with /api/chat (streaming) or /api/generate (non-streaming)")
            elif provider == "LM Studio":
                headers["Accept"] = "text/event-stream"
                model_name = "loaded-model" # Placeholder for LM Studio
                data = { "model": model_name, "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens, "temperature": 0.6, "stream": True }
                logger.debug(f"Sending stream request to LM Studio: {endpoint}")
                response = requests.post(endpoint, headers=headers, json=data, stream=True, timeout=60)
            else:
                raise ValueError(f"Unsupported AI provider for streaming: {provider}")

            response.raise_for_status()
            logger.debug(f"AI Response Status Code: {response.status_code}")

            # --- Streaming / Non-streaming handling (Keep as is) ---
            # (Logic for SSEClient, NDJSON, and non-streaming remains the same)
            # ...
            if can_stream:
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/event-stream" in content_type:
                    if not SSEClient: raise RuntimeError("SSEClient library required but not found.")
                    try:
                        client = SSEClient(response)
                        for event in client.events():
                            if not self.is_running: break
                            if event.event == 'message' and event.data:
                                if event.data.strip() == '[DONE]': break
                                try:
                                    json_data = json.loads(event.data)
                                    delta = {}
                                    # Handle slight variations in response structure
                                    if provider == "OpenAI" or provider == "LM Studio":
                                        delta = json_data.get("choices", [{}])[0].get("delta", {})
                                    # Add other provider structures if needed here
                                    text_chunk = delta.get("content", "")
                                    if text_chunk:
                                        full_response_text += text_chunk
                                        if self.is_running: self.text_chunk.emit(text_chunk)
                                except (json.JSONDecodeError, IndexError, KeyError, TypeError) as e:
                                    logger.error(f"Error parsing SSE chunk: {e}, data: {event.data[:100]}")
                            elif event.event == 'error':
                                raise RuntimeError(f"AI stream error event: {event.data}")
                    except Exception as e:
                        logger.error(f"Error processing SSE stream: {e}", exc_info=True)
                        raise # Re-raise to be caught by outer handler
                    finally:
                         if client: client.close()

                elif "application/x-ndjson" in content_type: # Ollama streaming
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
                                    logger.error(f"Error parsing NDJSON chunk: {e}, line: {decoded_line[:100]}")
                    except Exception as e:
                        logger.error(f"Error processing NDJSON stream: {e}", exc_info=True)
                        raise # Re-raise
                else:
                    logger.warning(f"Unexpected streaming Content-Type '{content_type}'. Reading full response.")
                    full_response_text = response.text
                    if self.is_running: self.text_chunk.emit(full_response_text)
            else: # Handle non-streaming response (e.g., Ollama /generate)
                result = response.json()
                logger.debug(f"Received Non-Streaming JSON: {result}")
                if provider == "Ollama" and endpoint.endswith('/api/generate'):
                    full_response_text = result.get("response", "")
                else:
                    # Generic fallback for other non-streaming cases
                    logger.warning(f"Received non-streaming response for unhandled provider/endpoint: {provider}/{endpoint}")
                    # Try common response structures
                    if "choices" in result and len(result["choices"]) > 0:
                        full_response_text = result["choices"][0].get("message", {}).get("content", "") \
                                          or result["choices"][0].get("text", "")
                    elif "message" in result:
                        full_response_text = result["message"].get("content", "")
                    elif "response" in result:
                        full_response_text = result["response"]
                    else:
                        full_response_text = str(result) # Raw dump if unknown

                if not full_response_text: logger.warning("Non-streaming AI response content is empty.")
                if self.is_running: self.text_chunk.emit(full_response_text.strip())
            # --- End Streaming / Non-streaming ---


            if not self.is_running:
                logger.warning("AI Processing stopped before completion.")
                return

            logger.info(f"AI processing finished in {time.time() - start_time:.3f} seconds.")
            self.finished_stream.emit(full_response_text.strip())

        except requests.exceptions.RequestException as e:
            error_msg = f"API Request Error: {e}"
            logger.error(f"AI streaming request failed ({provider}): {e}", exc_info=True)
            if self.is_running: self.error_stream.emit(error_msg)
        except ValueError as e:
            error_msg = f"Configuration/Value Error: {e}"
            logger.error(f"AI streaming config error ({provider}): {e}", exc_info=True)
            if self.is_running: self.error_stream.emit(error_msg)
        except RuntimeError as e:
            error_msg = f"Runtime Error: {e}"
            logger.error(f"AI streaming runtime error ({provider}): {e}", exc_info=True)
            if self.is_running: self.error_stream.emit(error_msg)
        except Exception as e:
            error_msg = f"Unexpected Error: {e}"
            logger.error(f"Unexpected error in AI processing ({provider}): {e}", exc_info=True)
            if self.is_running: self.error_stream.emit(error_msg)
        finally:
            self.is_running = False
            if 'response' in locals() and response:
                try: response.close()
                except Exception as resp_close_err: logger.warning(f"Error closing AI response connection: {resp_close_err}")
            if client: # Ensure SSEClient is closed if error happened mid-stream
                try: client.close()
                except: pass
            logger.debug("AIStreamingWorker finished run method.")
