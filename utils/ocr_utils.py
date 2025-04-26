# utils/ocr_utils.py
import logging
import pytesseract
import os
import platform
import shutil
from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger("OverlayTranslate") # Use the named logger

# --- Language Code Mapping ---
# Maps the application's language codes to Tesseract's codes
APP_LANG_TO_TESSERACT = {
    'en': 'eng',
    'es': 'spa',
    'fr': 'fra',
    'de': 'deu',
    'it': 'ita',
    'pt': 'por',
    'ru': 'rus',
    'ch': 'chi_sim', # Map general Chinese to Simplified
    'zh': 'chi_sim', # Map specific Chinese to Simplified
    'zh-cn': 'chi_sim', # Explicit Simplified
    'ja': 'jpn',
    'ko': 'kor',
    # Add other mappings as needed
    # 'auto' is handled separately using langdetect first
}

def get_tesseract_langs():
    """Attempts to get the list of installed Tesseract languages."""
    try:
        return pytesseract.get_languages(config='')
    except Exception as e:
        logger.error(f"Could not get installed Tesseract languages: {e}")
        return [] # Return empty list on error

def configure_tesseract():
    """
    Configures the path to the Tesseract executable.
    Tries to find it automatically, otherwise prompts the user or uses a default path.
    Returns True if successful, False otherwise.
    """
    tesseract_path = None
    config_successful = False

    # 1. Check common installation paths
    common_paths = []
    if platform.system() == "Windows":
        # Common paths for Tesseract installed via installers
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        common_paths.extend([
            os.path.join(program_files, "Tesseract-OCR", "tesseract.exe"),
            os.path.join(program_files_x86, "Tesseract-OCR", "tesseract.exe"),
        ])
    elif platform.system() == "Darwin": # macOS
        common_paths.append("/opt/homebrew/bin/tesseract") # Apple Silicon Homebrew
        common_paths.append("/usr/local/bin/tesseract")    # Intel Homebrew / Manual install
    else: # Linux
        common_paths.append("/usr/bin/tesseract")

    for path in common_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            tesseract_path = path
            logger.info(f"Found Tesseract executable at common path: {tesseract_path}")
            break

    # 2. Check if Tesseract is in the system PATH
    if not tesseract_path:
        tesseract_path = shutil.which("tesseract")
        if tesseract_path:
            logger.info(f"Found Tesseract executable in system PATH: {tesseract_path}")

    # 3. Handle if not found automatically
    if not tesseract_path:
        logger.warning("Tesseract executable not found in common paths or system PATH.")
        msg = ("Tesseract OCR executable not found automatically.\n\n"
               "Please ensure Tesseract is installed and added to your system PATH, "
               "or specify the path manually (including 'tesseract.exe' on Windows).\n\n"
               "Visit the Tesseract GitHub page for installation instructions.")
        # We cannot easily prompt for path here as it's early startup.
        # Log the error and show a critical message. The app might fail later.
        QMessageBox.critical(None, "Tesseract Not Found", msg)
        return False # Configuration failed

    # 4. Set the command path for pytesseract
    try:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        # Verify by getting version or languages
        version = pytesseract.get_tesseract_version()
        installed_langs = get_tesseract_langs()
        logger.info(f"Tesseract configured successfully. Path: {tesseract_path}, Version: {version}, Installed Languages: {installed_langs}")
        if not installed_langs:
             logger.warning("Could not retrieve list of installed Tesseract languages. OCR might fail if languages are missing.")
        elif 'eng' not in installed_langs:
             logger.warning("English language pack ('eng') for Tesseract seems missing. Basic functionality might be affected.")
        config_successful = True
    except pytesseract.TesseractNotFoundError:
        logger.error(f"Pytesseract could not find Tesseract at the configured path: {tesseract_path}")
        QMessageBox.critical(None, "Tesseract Not Found", f"Pytesseract failed to verify Tesseract at:\n{tesseract_path}\n\nPlease check the path and installation.")
        config_successful = False
    except Exception as e:
        logger.error(f"Error configuring or verifying Tesseract: {e}", exc_info=True)
        QMessageBox.critical(None, "Tesseract Configuration Error", f"An unexpected error occurred while configuring Tesseract:\n{e}")
        config_successful = False

    return config_successful

