import logging
import gc
from paddleocr import PaddleOCR
from PySide6.QtWidgets import QMessageBox

# --- Global Variables & Initial Setup ---
paddle_ocr_instance = None
logger = logging.getLogger("OverlayTranslate") # Use the named logger


def get_ocr_instance():
    """Returns the initialized PaddleOCR instance."""
    return paddle_ocr_instance


def initialize_paddle_ocr(lang='en'):
    global paddle_ocr_instance
    logger.info(f"Attempting to initialize PaddleOCR with language: {lang}")
    try:
        # Explicitly free memory if replacing an existing instance
        if paddle_ocr_instance:
            logger.debug("Deleting existing PaddleOCR instance...")
            del paddle_ocr_instance
            paddle_ocr_instance = None
            gc.collect()
            logger.debug("Existing PaddleOCR instance deleted and GC called.")

        paddle_ocr_instance = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            use_gpu=False, # Keep GPU off for broader compatibility
            det=True,
            rec=True,
            show_log=False # Keep console clean
        )
        logger.info(f"PaddleOCR initialized successfully for language: {lang}")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize PaddleOCR: {e}", exc_info=True)
        paddle_ocr_instance = None
        msg = f"Failed to initialize PaddleOCR for language '{lang}'.\n\nError: {e}\n\n"
        msg += "Please ensure PaddleOCR and PaddlePaddle are correctly installed.\n"
        msg += "Try running: pip install --upgrade paddleocr paddlepaddle\n"
        msg += "Check internet connection if models need downloading."
        # Use QMessageBox directly here as it's a critical failure during init
        QMessageBox.critical(None, "OCR Initialization Failed", msg)
        return False