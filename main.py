# main.py — Lite version (no AI, no chat, no complex features)

import sys
import os
import platform
import logging
import tempfile
import time
import traceback
import threading
import datetime
import requests

from utils.config import (
    FLASK_SERVER_HOST, FLASK_SERVER_PORT,
    SERVER_READY_CHECK_TIMEOUT, SERVER_READY_CHECK_INTERVAL, SERVER_READY_REQUEST_TIMEOUT
)

# --- Waitress and Flask App Import ---
try:
    from waitress import serve
    WAITRESS_AVAILABLE = True
except ImportError:
    WAITRESS_AVAILABLE = False
    if sys.stderr:
        print("ERROR: Waitress library not found. Please install it using: pip install waitress", file=sys.stderr)

try:
    from app import app as flask_app
    FLASK_APP_AVAILABLE = True
except ImportError as e:
    if sys.stderr:
        print(f"ERROR: Could not import Flask app from app.py: {e}. Local server unavailable.", file=sys.stderr)
    FLASK_APP_AVAILABLE = False
    flask_app = None


os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Qt Imports
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen, QSystemTrayIcon, QProgressDialog
from PySide6.QtGui import QIcon, QFont, QPixmap
from PySide6.QtCore import Qt, QTimer, QLockFile

# Project Imports
from utils.config import PROJECT_ROOT, logger, ensure_support_folder
from utils.helpers import load_settings, apply_theme, resource_path
from utils.ocr_utils import configure_paddle_ocr
from utils.model_downloader import ModelDownloader, models_needed
from gui.control_window import ControlWindow


# --- Exception Hook ---
def global_except_hook(exc_type, exc_value, exc_tb):
    logger.critical("Unhandled exception caught by global hook:", exc_info=(exc_type, exc_value, exc_tb))
    tb_details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    error_msg = f"A critical error occurred:\n\n{exc_value}\n\nTraceback:\n{tb_details}"
    try:
         msg_box = QMessageBox()
         msg_box.setIcon(QMessageBox.Icon.Critical)
         msg_box.setWindowTitle("Critical Application Error")
         msg_box.setText("An unrecoverable error occurred. Please check the logs.")
         msg_box.setDetailedText(error_msg)
         msg_box.exec()
    except Exception as mb_error:
         if sys.stderr:
             print(f"CRITICAL ERROR (GUI Error Box Failed: {mb_error}):\n{error_msg}", file=sys.stderr)
    finally:
         os._exit(1)

sys.excepthook = global_except_hook


# --- Flask Server Runner Function ---
def run_flask_server():
    if not FLASK_APP_AVAILABLE:
        logger.error("Flask app instance not available. Cannot start server thread.")
        return
    if not WAITRESS_AVAILABLE:
        logger.error("Waitress library not available. Cannot start server thread.")
        return

    host = FLASK_SERVER_HOST
    port = FLASK_SERVER_PORT
    threads = 4

    logger.info(f"Starting embedded Waitress server on http://{host}:{port} with {threads} threads...")
    try:
        serve(flask_app, host=host, port=port, threads=threads, _quiet=True)
        logger.info("Waitress server thread finished.")
    except OSError as e:
        if "Only one usage of each socket address" in str(e) or "Address already in use" in str(e):
             logger.error(f"Failed to start Waitress server: Port {port} is already in use.")
        else:
             logger.critical(f"Waitress server thread encountered an OSError: {e}", exc_info=True)
    except Exception as e:
        logger.critical(f"Waitress server thread encountered an unexpected error: {e}", exc_info=True)


def check_server_readiness(timeout=SERVER_READY_CHECK_TIMEOUT):
    server_url = f"http://{FLASK_SERVER_HOST}:{FLASK_SERVER_PORT}/"
    max_retries = int(timeout / SERVER_READY_CHECK_INTERVAL)
    
    logger.info(f"Checking Flask server readiness (timeout: {timeout}s)...")
    
    for attempt in range(max_retries):
        try:
            response = requests.get(server_url, timeout=SERVER_READY_REQUEST_TIMEOUT)
            if 200 <= response.status_code < 400:
                logger.info(f"Flask server is ready (attempt {attempt + 1}).")
                return True
        except requests.exceptions.ConnectionError:
            logger.debug(f"Server check attempt {attempt + 1}: Connection refused, retrying...")
        except requests.exceptions.Timeout:
            logger.debug(f"Server check attempt {attempt + 1}: Timeout, retrying...")
        except Exception as e:
            logger.warning(f"Server check attempt {attempt + 1}: Unexpected error: {e}")
        
        time.sleep(SERVER_READY_CHECK_INTERVAL)
    
    logger.error(f"Flask server did not become ready within {timeout} seconds.")
    return False


# --- Main Application Execution ---
if __name__ == '__main__':
    # --- Set Windows AUMID so tray notifications show app name, not "Python" ---
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('OverlayTranslate.Lite.1')
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("OverlayTranslateLite")
    app.setOrganizationName("YourOrganization")
    app.setQuitOnLastWindowClosed(False)
    
    # --- Initialize Settings Manager ---
    from utils.config import CONFIG_FILE
    from utils.settings_manager import get_settings_manager
    settings_manager = get_settings_manager()
    settings_manager.initialize(CONFIG_FILE)
    logger.info(f"Settings manager initialized with config file: {CONFIG_FILE}")
    
    # === Initialize Translation Manager ===
    from utils.translation_manager import init_translation_manager
    translation_manager = init_translation_manager(app)
    
    preferred_lang = translation_manager.load_language_preference()
    translation_manager.load_language(preferred_lang)
    logger.info(f"Translation manager initialized with language: {preferred_lang}")
    
    # --- Instance Locking ---
    lock_file_path = os.path.join(tempfile.gettempdir(), "overlay_translate_lite_instance.lock")
    
    lock_file = QLockFile(lock_file_path)
    lock_file.setStaleLockTime(0)

    if not lock_file.tryLock(100):
        error = lock_file.error()
        if error == QLockFile.LockError.LockFailedError:
            if lock_file.removeStaleLockFile():
                logger.info("Removed stale lock file.")
                if not lock_file.tryLock(100):
                     QMessageBox.warning(None, "Already Running", "Another instance seems to be running (failed lock after stale removed).")
                     sys.exit(0)
                else:
                     logger.info("Acquired lock after removing stale file.")
            else:
                 QMessageBox.warning(None, "Already Running", "Another instance of Overlay Translate Lite is already running.")
                 sys.exit(0)
        else:
            QMessageBox.warning(None, "Already Running", "Another instance of Overlay Translate Lite is already running.")
            sys.exit(0)

    logger.info(f"Acquired instance lock file: {lock_file_path}")

    ensure_support_folder()

    # --- Start Flask Server Thread ---
    server_thread = None
    if FLASK_APP_AVAILABLE and WAITRESS_AVAILABLE:
        server_thread = threading.Thread(target=run_flask_server, name="FlaskWaitressThread", daemon=True)
        server_thread.start()
        logger.info("Flask server thread started.")
        time.sleep(SERVER_READY_CHECK_INTERVAL)
    else:
        if not FLASK_APP_AVAILABLE:
            logger.error("Local server component (app.py) could not be loaded.")
            QMessageBox.critical(None, "Server Error", "Could not load the local translation server component (app.py).\nOffline translation will be unavailable.")
        elif not WAITRESS_AVAILABLE:
            logger.error("Waitress library missing. Cannot start local server.")
            QMessageBox.warning(None, "Server Error", "Waitress library is missing (install with 'pip install waitress').\nOffline translation will be unavailable.")

    # --- Load Settings and Apply Theme ---
    logger.info("Loading initial settings and theme...")
    initial_settings = load_settings()
    apply_theme()
    logger.info("Initial settings loaded and theme applied.")

    # --- Load PaddleOCR config from config.ini ---
    try:
        import configparser
        _ini = configparser.ConfigParser()
        _ini.read(os.path.join(PROJECT_ROOT, "config.ini"))
        _paddle_model_dir = _ini.get("PaddleOCR", "model_dir", fallback="").strip()
        if _paddle_model_dir:
            from utils.ocr_utils import set_model_directory
            set_model_directory(_paddle_model_dir)
    except Exception as e:
        logger.debug(f"No custom PaddleOCR config: {e}")

    # --- Set Application Icon and Font ---
    icon_path = resource_path(os.path.join("assets", "icon.png"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        logger.warning(f"Application icon not found at {icon_path}")

    default_font_family = "Segoe UI" if platform.system() == "Windows" else "Roboto"
    default_font_size = 9 if platform.system() == "Windows" else 10
    app.setFont(QFont(default_font_family, default_font_size))
    logger.info(f"Set application default font: {default_font_family} {default_font_size}pt")

    # --- Splash Screen ---
    splash_pix = None
    if os.path.exists(icon_path):
        try:
            splash_pix = QPixmap(icon_path).scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception as splash_err:
            logger.warning(f"Could not load splash image: {splash_err}")

    splash = None
    if splash_pix:
        splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        splash.show()
        app.processEvents()

    # --- Download PaddleOCR Models (with progress dialog) ---
    default_langs = ['en', 'ch']
    needed = models_needed(default_langs)

    if needed:
        logger.info(f"Need to download {len(needed)} OCR model(s) before startup...")

        if splash:
            splash.close()
            splash = None

        progress_dlg = QProgressDialog(
            "Downloading OCR models...\nThis only happens on first launch.",
            "Cancel", 0, 100
        )
        progress_dlg.setWindowTitle("Overlay Translate Lite — Preparing OCR")
        progress_dlg.setWindowModality(Qt.WindowModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.setAutoClose(False)
        progress_dlg.setAutoReset(False)
        progress_dlg.show()
        app.processEvents()

        downloader = ModelDownloader()

        def on_progress(current, total, message):
            if total > 0:
                pct = int((current / total) * 100)
                progress_dlg.setValue(pct)
            progress_dlg.setLabelText(message)
            app.processEvents()

        downloader.progress.connect(on_progress)
        progress_dlg.canceled.connect(downloader.cancel)

        success, error_msg = downloader.ensure_models_ready(default_langs)

        progress_dlg.close()
        progress_dlg.deleteLater()

        if not success:
            logger.error(f"Model download failed: {error_msg}")
            QMessageBox.critical(
                None, "Model Download Failed",
                f"Could not download OCR models:\n\n{error_msg}\n\n"
                "The application will try to start anyway, but OCR may not work."
            )
    else:
        logger.info("All OCR models already available.")
        if splash:
            splash.showMessage("Initializing OCR Engine...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
            app.processEvents()

    # --- Configure PaddleOCR Engine ---
    logger.info("Configuring PaddleOCR Engine...")
    ocr_config_success = configure_paddle_ocr()

    if splash:
        status_msg = "OCR Engine Initialized." if ocr_config_success else "OCR Engine Config Failed!"
        splash.showMessage(status_msg, Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        app.processEvents()
        time.sleep(0.5 if ocr_config_success else 1.5)
        splash.close()

    if not ocr_config_success:
        logger.critical("PaddleOCR engine failed to configure during startup.")
        sys.exit(1)
    logger.info("PaddleOCR configuration complete.")


    # --- Main Execution ---
    control_window = None
    try:
        control_window = ControlWindow()

        # --- Wait for Flask Server Readiness Check ---
        logger.info("Waiting for local translation server check...")
        flask_ready = False
        if server_thread and server_thread.is_alive():
            flask_ready = check_server_readiness(timeout=12.0)
            
            if flask_ready:
                logger.info("Local server readiness check successful (Waitress responded).")
            else:
                if not server_thread.is_alive():
                    logger.error("Local server thread terminated unexpectedly (check logs for errors like 'Port already in use').")
                else:
                    logger.error("Local server readiness check timed out (server started but not responding).")
                
                if control_window.tray_icon and control_window.tray_icon.isVisible():
                    control_window.tray_icon.showMessage(
                        "Server Status", 
                        "Local translation server check failed or timed out.", 
                        QSystemTrayIcon.MessageIcon.Warning, 
                        5000
                    )
        elif FLASK_APP_AVAILABLE and WAITRESS_AVAILABLE:
            logger.error("Flask server thread failed to start or terminated immediately (check logs).")
        else:
            logger.info("Local translation server is not available (import failed or Waitress missing).")

        control_window.show()

        exit_code = app.exec()
        logger.info(f"Application event loop finished with exit code: {exit_code}")
        sys.exit(exit_code)

    except Exception as main_err:
        logger.critical(f"Critical error during application startup or execution: {main_err}", exc_info=True)
        sys.exit(1)
