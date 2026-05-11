# utils/ocr_utils.py
import logging
import os
from typing import Optional
from PySide6.QtWidgets import QMessageBox
from utils.retry_utils import retry_with_backoff
from utils.model_downloader import get_model_urls, is_model_ready, get_default_model_dir

logger = logging.getLogger("OverlayTranslate")

# --- Global PaddleOCR Instance Cache ---
_paddle_ocr_cache = {}

# --- Configurable Model Directory ---
_custom_model_dir: Optional[str] = None


def set_model_directory(path: str):
    """
    Set a custom directory for PaddleOCR model storage.
    Must be called before any OCR initialization.

    Args:
        path: Absolute path to model directory (will be created if needed)
    """
    global _custom_model_dir
    _custom_model_dir = os.path.expanduser(path)
    logger.info(f"PaddleOCR model directory set to: {_custom_model_dir}")


def get_paddle_model_directory() -> str:
    """Returns the configured PaddleOCR model directory."""
    if _custom_model_dir:
        return _custom_model_dir
    return get_default_model_dir()


# --- Language Code Mapping ---
# Maps the application's language codes to PaddleOCR's supported codes.
# PaddleOCR supports: ch, en, korean, japan, chinese_cht, ta, te, ka,
#                      latin, arabic, cyrillic, devanagari, german
APP_LANG_TO_PADDLE = {
    'en': 'en',
    'es': 'latin',         # Spanish → latin script
    'fr': 'latin',         # French → latin script
    'de': 'german',        # German has its own PaddleOCR model
    'it': 'latin',         # Italian → latin script
    'pt': 'latin',         # Portuguese → latin script
    'nl': 'latin',         # Dutch → latin script
    'pl': 'latin',         # Polish → latin script
    'ro': 'latin',         # Romanian → latin script
    'hr': 'latin',         # Croatian → latin script
    'cs': 'latin',         # Czech → latin script
    'sk': 'latin',         # Slovak → latin script
    'hu': 'latin',         # Hungarian → latin script
    'sv': 'latin',         # Swedish → latin script
    'da': 'latin',         # Danish → latin script
    'no': 'latin',         # Norwegian → latin script
    'fi': 'latin',         # Finnish → latin script
    'ru': 'cyrillic',      # Russian → cyrillic script
    'uk': 'cyrillic',      # Ukrainian → cyrillic script
    'bg': 'cyrillic',      # Bulgarian → cyrillic script
    'sr': 'cyrillic',      # Serbian → cyrillic script
    'hi': 'devanagari',    # Hindi → devanagari script
    'ar': 'arabic',        # Arabic
    'ta': 'ta',            # Tamil
    'te': 'te',            # Telugu
    'ka': 'ka',            # Kannada
    # Chinese language variants
    'ch': 'ch',            # General Chinese (Simplified)
    'zh': 'ch',            # Generic Chinese (Simplified)
    'zh-cn': 'ch',         # Simplified Chinese (Mainland)
    'zh-tw': 'chinese_cht',  # Traditional Chinese (Taiwan)
    'zh-hk': 'chinese_cht',  # Traditional Chinese (Hong Kong)
    'ja': 'japan',
    'ko': 'korean',
    # 'auto' is handled by using 'ch' which is a good multilingual base
}


def _get_model_dir_kwargs(lang_code: str) -> dict:
    """
    Build PaddleOCR constructor kwargs for model directories.

    If models have been pre-downloaded (by ModelDownloader), pass their
    explicit paths so PaddleOCR skips its own download logic.
    """
    urls = get_model_urls(lang_code)
    if not urls:
        return {}

    kwargs = {}
    for model_type, (model_dir, _url) in urls.items():
        if is_model_ready(model_dir):
            key = f"{model_type}_model_dir"
            kwargs[key] = model_dir

    return kwargs


def get_paddle_ocr_instance(lang_code='en'):
    """
    Returns a cached instance of the PaddleOCR engine for a specific language.
    If the instance is not in the cache, it will be created and initialized.
    """
    global _paddle_ocr_cache

    # Ensure the lang_code is valid before creating an instance
    # These are the ACTUAL PaddleOCR supported language codes (not app codes)
    valid_paddle_langs = ['ch', 'en', 'korean', 'japan', 'chinese_cht', 'ta', 'te', 'ka', 'latin', 'arabic', 'cyrillic', 'devanagari', 'german']
    if lang_code not in valid_paddle_langs:
        logger.warning(f"Unsupported language code '{lang_code}' requested for PaddleOCR. Defaulting to 'en'.")
        lang_code = 'en'

    if lang_code in _paddle_ocr_cache:
        logger.debug(f"Returning cached PaddleOCR instance for lang='{lang_code}'")
        return _paddle_ocr_cache[lang_code]

    logger.info(f"Creating new PaddleOCR instance for lang='{lang_code}'. This may download models...")
    
    # Inner function with retry logic for OCR initialization
    @retry_with_backoff(
        max_attempts=3,
        initial_delay=2.0,
        backoff_factor=2.0,
        exceptions=(Exception,),
        on_retry=lambda e, attempt, delay: logger.info(
            f"Retrying PaddleOCR initialization for '{lang_code}': attempt {attempt}, waiting {delay:.1f}s"
        )
    )
    def _create_ocr_instance():
        from paddleocr import PaddleOCR
        import sys
        import io
        # Redirect stdout/stderr temporarily to catch initialization output
        # This prevents NoneType write errors in frozen environments
        old_stdout, old_stderr = sys.stdout, sys.stderr
        try:
            sys.stdout = io.StringIO() if not hasattr(sys.stdout, 'write') else sys.stdout
            sys.stderr = io.StringIO() if not hasattr(sys.stderr, 'write') else sys.stderr
            # Pass pre-downloaded model dirs to avoid PaddleOCR's own download
            model_kwargs = _get_model_dir_kwargs(lang_code)
            return PaddleOCR(use_angle_cls=True, lang=lang_code, use_gpu=False, show_log=False, **model_kwargs)
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
    
    try:
        new_instance = _create_ocr_instance()
        _paddle_ocr_cache[lang_code] = new_instance
        logger.info(f"Successfully created and cached PaddleOCR instance for '{lang_code}'.")
        return new_instance
    except Exception as e:
        logger.critical(f"Failed to create PaddleOCR instance for lang='{lang_code}': {e}", exc_info=True)
        # Check for the specific assertion error to give a better message
        if isinstance(e, AssertionError) and "param lang must in" in str(e):
             msg = f"The language code '{lang_code}' is invalid for the installed PaddleOCR version.\nPlease check for library updates or use a different language."
             QMessageBox.critical(None, "PaddleOCR Language Error", msg)
        else:
            QMessageBox.critical(None, "PaddleOCR Initialization Error", f"Could not create the OCR engine for language '{lang_code}'.\nError: {e}")
        return None

def configure_paddle_ocr():
    """
    Checks for PaddleOCR library and pre-warms the cache with the default
    English and multilingual models to speed up first use.
    Returns True if successful, False otherwise.
    """
    try:
        from paddleocr import PaddleOCR
    except ImportError as e:
        logger.critical(f"PaddleOCR or PaddlePaddle library not found. Error: {e}")
        import traceback
        logger.critical(f"Full traceback:\n{traceback.format_exc()}")
        msg = (f"The 'paddleocr' or 'paddlepaddle' library is not installed.\n\n"
               f"Import error: {e}\n\n"
               "Please install it to use OCR features:\n\n"
               "pip install paddleocr paddlepaddle")
        QMessageBox.critical(None, "Library Not Found", msg)
        return False

    try:
        logger.info("Pre-caching default OCR models...")
        # Pre-cache English
        get_paddle_ocr_instance('en')
        # --- CORRECTED: Use 'ch' for the multilingual model ---
        get_paddle_ocr_instance('ch')
        logger.info("OCR models pre-cached successfully.")
        return True
    except Exception as e:
        logger.error(f"Error pre-caching PaddleOCR models: {e}", exc_info=True)
        QMessageBox.critical(None, "PaddleOCR Model Error", f"An error occurred while downloading/loading default OCR models:\n{e}")
        return False