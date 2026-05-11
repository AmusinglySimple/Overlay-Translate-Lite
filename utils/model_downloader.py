# utils/model_downloader.py
"""
PaddleOCR Model Downloader with Progress Reporting

Downloads PaddleOCR model files (.pdiparams, .pdmodel) with:
- Qt signal-based progress reporting for GUI integration
- Configurable download timeout and chunk size
- Integrity verification (file existence + size check)
- Partial file cleanup on failure
- Configurable model storage directory

Usage:
    downloader = ModelDownloader(model_dir="~/.paddleocr")
    downloader.progress.connect(update_progress_bar)
    downloader.ensure_models_ready(["en", "ch"])
"""

import os
import tarfile
import logging
import time
import requests
from typing import Optional, List, Dict, Tuple

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("OverlayTranslate")

# --- Constants ---
DOWNLOAD_TIMEOUT = 120  # seconds per request
DOWNLOAD_CHUNK_SIZE = 8192  # 8 KB chunks for streaming
DOWNLOAD_RETRIES = 3
DOWNLOAD_RETRY_DELAY = 2.0  # seconds between retries

# Minimum valid file sizes for integrity check (bytes)
MIN_MODEL_FILE_SIZE = 1024  # 1 KB — any valid model file should be at least this

# Files that must exist in a valid model directory
REQUIRED_MODEL_FILES = ["inference.pdiparams", "inference.pdmodel"]


def get_default_model_dir() -> str:
    """Returns the default PaddleOCR model directory (~/.paddleocr/)."""
    return os.path.join(os.path.expanduser("~"), ".paddleocr")


def get_model_urls(lang_code: str) -> Dict[str, Tuple[str, str]]:
    """
    Get model URLs and target directories for a given language.

    Args:
        lang_code: PaddleOCR language code (e.g., 'en', 'ch', 'korean')

    Returns:
        Dict mapping model type ('det', 'rec', 'cls') to (target_dir, url) tuples.
    """
    try:
        import paddleocr.paddleocr as pocr

        # Determine detection language (most use 'ch' detector)
        det_lang = lang_code
        if lang_code in ('en', 'french', 'german', 'it', 'es', 'pt', 'ru',
                         'latin', 'arabic', 'cyrillic', 'devanagari',
                         'korean', 'japan', 'chinese_cht', 'ta', 'te', 'ka'):
            det_lang = 'ch'

        ocr_version = 'PP-OCRv4'

        det_cfg = pocr.get_model_config('OCR', ocr_version, 'det', det_lang)
        rec_cfg = pocr.get_model_config('OCR', ocr_version, 'rec', lang_code)
        cls_cfg = pocr.get_model_config('OCR', ocr_version, 'cls', 'ch')

        base_dir = pocr.BASE_DIR

        det_url = det_cfg['url']
        rec_url = rec_cfg['url']
        cls_url = cls_cfg['url']

        # Compute target directories the same way PaddleOCR does
        det_dir = os.path.join(base_dir, 'whl', 'det', det_lang, det_url.split('/')[-1][:-4])
        rec_dir = os.path.join(base_dir, 'whl', 'rec', lang_code, rec_url.split('/')[-1][:-4])
        cls_dir = os.path.join(base_dir, 'whl', 'cls', cls_url.split('/')[-1][:-4])

        return {
            'det': (det_dir, det_url),
            'rec': (rec_dir, rec_url),
            'cls': (cls_dir, cls_url),
        }
    except Exception as e:
        logger.error(f"Failed to resolve model URLs for lang '{lang_code}': {e}", exc_info=True)
        return {}


def is_model_ready(model_dir: str) -> bool:
    """
    Check if a model directory has all required files and they are valid.

    Args:
        model_dir: Path to the model directory

    Returns:
        True if all required model files exist and are valid
    """
    if not os.path.isdir(model_dir):
        return False

    for filename in REQUIRED_MODEL_FILES:
        filepath = os.path.join(model_dir, filename)
        if not os.path.isfile(filepath):
            return False
        if os.path.getsize(filepath) < MIN_MODEL_FILE_SIZE:
            logger.warning(f"Model file {filepath} is too small ({os.path.getsize(filepath)} bytes), likely corrupt")
            return False

    return True


def models_needed(lang_codes: List[str]) -> List[Tuple[str, str, str]]:
    """
    Check which models need to be downloaded for the given languages.

    Args:
        lang_codes: List of PaddleOCR language codes

    Returns:
        List of (lang_code, model_type, url) tuples for models that need downloading
    """
    needed = []
    seen_dirs = set()

    for lang in lang_codes:
        urls = get_model_urls(lang)
        for model_type, (model_dir, url) in urls.items():
            if model_dir in seen_dirs:
                continue
            seen_dirs.add(model_dir)
            if not is_model_ready(model_dir):
                needed.append((lang, model_type, url, model_dir))

    return needed


class ModelDownloader(QObject):
    """
    Downloads PaddleOCR models with progress reporting via Qt signals.

    Signals:
        progress(current_bytes, total_bytes, message):
            Emitted during download with byte counts and descriptive message.
        download_complete(lang_code, model_type, success, error_msg):
            Emitted when a single model download finishes.
        all_complete(success, error_msg):
            Emitted when all requested downloads finish.
    """

    progress = Signal(int, int, str)  # current, total, message
    download_complete = Signal(str, str, bool, str)  # lang, type, success, error
    all_complete = Signal(bool, str)  # success, error

    def __init__(self, timeout: int = DOWNLOAD_TIMEOUT, parent=None):
        super().__init__(parent)
        self._timeout = timeout
        self._cancelled = False

    def cancel(self):
        """Cancel ongoing downloads."""
        self._cancelled = True

    def download_model(self, url: str, target_dir: str, label: str = "") -> Tuple[bool, str]:
        """
        Download and extract a single model tar file.

        Args:
            url: URL of the .tar model archive
            target_dir: Directory to extract model files into
            label: Human-readable label for progress messages

        Returns:
            (success, error_message) tuple
        """
        if self._cancelled:
            return False, "Download cancelled"

        # Check if already downloaded
        if is_model_ready(target_dir):
            self.progress.emit(100, 100, f"{label}: Already available")
            return True, ""

        os.makedirs(target_dir, exist_ok=True)
        tar_filename = url.split('/')[-1]
        tmp_path = os.path.join(target_dir, tar_filename + ".tmp")

        for attempt in range(1, DOWNLOAD_RETRIES + 1):
            if self._cancelled:
                self._cleanup_tmp(tmp_path)
                return False, "Download cancelled"

            try:
                self.progress.emit(0, 0, f"{label}: Connecting... (attempt {attempt}/{DOWNLOAD_RETRIES})")

                response = requests.get(url, stream=True, timeout=self._timeout)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(tmp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if self._cancelled:
                            self._cleanup_tmp(tmp_path)
                            return False, "Download cancelled"

                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            self.progress.emit(
                                downloaded, total_size,
                                f"{label}: {downloaded / (1024*1024):.1f} / {total_size / (1024*1024):.1f} MB"
                            )

                # Verify download size
                actual_size = os.path.getsize(tmp_path)
                if total_size > 0 and actual_size != total_size:
                    self._cleanup_tmp(tmp_path)
                    error = f"Size mismatch: expected {total_size}, got {actual_size}"
                    logger.warning(f"{label}: {error}")
                    if attempt < DOWNLOAD_RETRIES:
                        time.sleep(DOWNLOAD_RETRY_DELAY)
                        continue
                    return False, error

                # Extract tar
                self.progress.emit(downloaded, total_size, f"{label}: Extracting...")
                tar_file_name_list = [".pdiparams", ".pdiparams.info", ".pdmodel"]

                with tarfile.open(tmp_path, "r") as tar_obj:
                    for member in tar_obj.getmembers():
                        filename = None
                        for tar_file_name in tar_file_name_list:
                            if member.name.endswith(tar_file_name):
                                filename = "inference" + tar_file_name
                        if filename is None:
                            continue
                        file = tar_obj.extractfile(member)
                        if file is not None:
                            out_path = os.path.join(target_dir, filename)
                            with open(out_path, "wb") as f:
                                f.write(file.read())

                # Cleanup temp file
                self._cleanup_tmp(tmp_path)

                # Verify extracted model
                if is_model_ready(target_dir):
                    self.progress.emit(total_size, total_size, f"{label}: Ready")
                    logger.info(f"Model downloaded and verified: {target_dir}")
                    return True, ""
                else:
                    error = f"Extraction failed — required files missing in {target_dir}"
                    logger.warning(error)
                    if attempt < DOWNLOAD_RETRIES:
                        time.sleep(DOWNLOAD_RETRY_DELAY)
                        continue
                    return False, error

            except requests.exceptions.Timeout:
                self._cleanup_tmp(tmp_path)
                error = f"Download timed out after {self._timeout}s"
                logger.warning(f"{label}: {error} (attempt {attempt}/{DOWNLOAD_RETRIES})")
                if attempt < DOWNLOAD_RETRIES:
                    time.sleep(DOWNLOAD_RETRY_DELAY)
                    continue
                return False, error

            except requests.exceptions.RequestException as e:
                self._cleanup_tmp(tmp_path)
                error = f"Download error: {e}"
                logger.warning(f"{label}: {error} (attempt {attempt}/{DOWNLOAD_RETRIES})")
                if attempt < DOWNLOAD_RETRIES:
                    time.sleep(DOWNLOAD_RETRY_DELAY)
                    continue
                return False, error

            except tarfile.TarError as e:
                self._cleanup_tmp(tmp_path)
                error = f"Extraction error: {e}"
                logger.warning(f"{label}: {error}")
                if attempt < DOWNLOAD_RETRIES:
                    time.sleep(DOWNLOAD_RETRY_DELAY)
                    continue
                return False, error

            except Exception as e:
                self._cleanup_tmp(tmp_path)
                error = f"Unexpected error: {e}"
                logger.error(f"{label}: {error}", exc_info=True)
                return False, error

        return False, f"All {DOWNLOAD_RETRIES} attempts failed"

    def ensure_models_ready(self, lang_codes: List[str]) -> Tuple[bool, str]:
        """
        Ensure all models for the given languages are downloaded and ready.

        Args:
            lang_codes: List of PaddleOCR language codes (e.g., ['en', 'ch'])

        Returns:
            (success, error_message) tuple
        """
        self._cancelled = False
        needed = models_needed(lang_codes)

        if not needed:
            self.progress.emit(100, 100, "All models already available")
            self.all_complete.emit(True, "")
            return True, ""

        total_models = len(needed)
        self.progress.emit(0, total_models, f"Downloading {total_models} model(s)...")
        logger.info(f"Need to download {total_models} model(s) for languages: {lang_codes}")

        errors = []
        for i, (lang, model_type, url, target_dir) in enumerate(needed, 1):
            label = f"[{i}/{total_models}] {lang}/{model_type}"

            success, error = self.download_model(url, target_dir, label)
            self.download_complete.emit(lang, model_type, success, error)

            if not success:
                errors.append(f"{label}: {error}")
                if self._cancelled:
                    break

        if errors:
            error_msg = "Model download errors:\n" + "\n".join(errors)
            self.all_complete.emit(False, error_msg)
            return False, error_msg

        self.all_complete.emit(True, "")
        return True, ""

    @staticmethod
    def _cleanup_tmp(tmp_path: str):
        """Remove temporary download file if it exists."""
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError as e:
            logger.warning(f"Failed to clean up temp file {tmp_path}: {e}")
