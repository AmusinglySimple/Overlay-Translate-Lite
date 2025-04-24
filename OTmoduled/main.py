import sys
import os
import platform
import logging
import tempfile
import time # For sleep
import traceback

# Qt Imports
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen # Added QSplashScreen
from PySide6.QtGui import QIcon, QFont, QPixmap # Added QPixmap
from PySide6.QtCore import Qt, QTimer, QLockFile # Added QLockFile

# Project Imports
from utils.config import PROJECT_ROOT, logger, ensure_support_folder # Use named logger
from utils.helpers import load_settings, apply_theme
from utils.ocr_utils import initialize_paddle_ocr, get_ocr_instance
from gui.control_window import ControlWindow
from gui.dialogs import IntroDialog # Intro dialog needed early

# --- Exception Hook ---
def global_except_hook(exc_type, exc_value, exc_tb):
    logger.critical("Unhandled exception caught by global hook:", exc_info=(exc_type, exc_value, exc_tb))
    tb_details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    error_msg = f"A critical error occurred:\n\n{exc_value}\n\nTraceback:\n{tb_details}"
    try:
         # Try showing a message box if GUI is potentially available
         msg_box = QMessageBox()
         msg_box.setIcon(QMessageBox.Icon.Critical)
         msg_box.setWindowTitle("Critical Application Error")
         msg_box.setText("An unrecoverable error occurred. Please check the logs.")
         msg_box.setDetailedText(error_msg)
         msg_box.exec()
    except Exception as mb_error:
         # Fallback to console if message box fails
         print(f"CRITICAL ERROR (GUI Error Box Failed: {mb_error}):\n{error_msg}")
    finally:
         # Use os._exit for forceful exit, especially if threads might hang
         os._exit(1)

sys.excepthook = global_except_hook

# --- Main Application Execution ---
if __name__ == '__main__':
    # --- Application Setup ---
    # Enable DPI scaling for better visuals on high-res displays
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
         QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
         QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # Create the Application instance
    app = QApplication(sys.argv)
    app.setApplicationName("OverlayTranslate")
    app.setOrganizationName("YourOrganization") # Optional, used for settings path on some OS

    # --- Instance Locking ---
    lock_file_path = os.path.join(tempfile.gettempdir(), "overlay_translate_instance.lock")
    lock_file = QLockFile(lock_file_path)
    lock_file.setStaleLockTime(0) # Consider stale immediately

    if not lock_file.tryLock(100):
        error = lock_file.error() # Get the error type
        # Check if it's potentially stale (process might have crashed)
        # LockFailedError indicates it couldn't acquire lock (could be held or stale)
        if error == QLockFile.LockError.LockFailedError:
            if lock_file.removeStaleLockFile():
                logger.info("Removed stale lock file.")
                if not lock_file.tryLock(100): # Try locking again
                     QMessageBox.warning(None, "Already Running", "Another instance seems to be running (failed lock after stale removed).")
                     sys.exit(0)
                else:
                     logger.info("Acquired lock after removing stale file.")
            else:
                 # Couldn't remove stale lock - another instance is likely running properly
                 QMessageBox.warning(None, "Already Running", "Another instance of Overlay Translate is already running.")
                 sys.exit(0)
        else:
            # Other lock errors or definitely held by another process
            QMessageBox.warning(None, "Already Running", "Another instance of Overlay Translate is already running.")
            sys.exit(0) # Exit if lock fails

    logger.info(f"Acquired instance lock file: {lock_file_path}")

    # --- Ensure Support Folder Exists ---
    ensure_support_folder()

    # --- Load Settings and Apply Theme EARLY ---
    # This loads window positions, theme, AI config into shared state
    logger.info("Loading initial settings and theme...")
    initial_settings = load_settings() # Loads theme into config._current_theme_data
    apply_theme() # Applies the loaded theme globally
    logger.info("Initial settings loaded and theme applied.")

    # --- Set Application Icon and Font ---
    icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        logger.warning(f"Application icon not found at {icon_path}")

    default_font_family = "Segoe UI" if platform.system() == "Windows" else "Roboto"
    default_font_size = 9 if platform.system() == "Windows" else 10
    app.setFont(QFont(default_font_family, default_font_size))
    logger.info(f"Set application default font: {default_font_family} {default_font_size}pt")

    # --- Splash Screen (Optional but nice during OCR init) ---
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
        app.processEvents() # Ensure splash is shown
        splash.showMessage("Initializing OCR Engine...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        app.processEvents()

    # --- Initialize OCR Engine ---
    logger.info("Initializing OCR Engine...")
    # Determine initial OCR language (default 'en', could be loaded from settings if saved)
    ocr_init_lang = 'en' # Default, simplest approach
    # Example if source_language was saved in control window settings:
    # cw_settings = initial_settings.get('ControlWindow', {}) # Assuming you save lang there
    # saved_lang = cw_settings.get('source_language', 'auto')
    # if saved_lang != 'auto': ocr_init_lang = saved_lang

    ocr_success = initialize_paddle_ocr(ocr_init_lang)

    if splash: # Update splash after OCR init
        status_msg = "OCR Ready." if ocr_success else "OCR Failed!"
        splash.showMessage(status_msg, Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        app.processEvents()
        time.sleep(0.5 if ocr_success else 1.5) # Show status briefly
        splash.close()

    if not ocr_success:
         logger.critical("OCR engine failed to initialize during startup.")
         # QMessageBox shown by initialize_paddle_ocr
         sys.exit(1)
    logger.info("OCR engine initialization complete.")


    # --- Main Execution ---
    control_window = None
    try:
        # Create the main window instance
        control_window = ControlWindow()

        # Re-apply theme? Usually not necessary if applied early, but can ensure consistency.
        # apply_theme()

        # --- Wait for Flask Server Readiness Check ---
        logger.info("Waiting for local translation server check...")
        flask_ready = False
        if hasattr(control_window, 'capture_widget') and control_window.capture_widget:
            # Wait on the event set by the checker thread in CaptureWidget
            # Timeout allows application to start even if server check hangs/fails
            flask_ready = control_window.capture_widget.flask_server_ready.wait(timeout=12.0) # Wait up to 12 sec

            if flask_ready:
                # Check if the server thread is actually running (covers port-in-use case partly)
                if control_window.capture_widget.flask_running:
                    logger.info("Flask server readiness check successful (thread running).")
                else:
                    logger.warning("Flask server readiness event received, but thread not marked running (likely external or port conflict).")
            else:
                logger.error("Flask server readiness check timed out or failed. Offline translation might not work.")
                # Error messages should have been emitted by the checker thread/server startup
                # Optionally show a non-critical tray message if possible
                if control_window.tray_icon and control_window.tray_icon.isVisible():
                     control_window.tray_icon.showMessage("Server Status", "Local translation server check failed or timed out.", QSystemTrayIcon.MessageIcon.Warning, 5000)
        else:
            logger.error("Capture widget not available for Flask server check.")
            QMessageBox.critical(None, "Startup Error", "Core component (Capture Widget) failed. Cannot check translation server.")
            # Decide whether to exit or continue without offline translation
            # sys.exit(1) # Exit might be safer

        # Show the main window
        control_window.show()

        # Start the application event loop
        exit_code = app.exec()
        logger.info(f"Application event loop finished with exit code: {exit_code}")
        sys.exit(exit_code)

    except Exception as main_err:
        logger.critical(f"Critical error during application startup or execution: {main_err}", exc_info=True)
        # Exception hook should handle displaying the error
        sys.exit(1) # Ensure exit

    finally:
        # Release the instance lock file if held
        if lock_file.isLocked():
             lock_file.unlock()
             logger.info("Released instance lock file.")

        # Final log message before handlers might be closed by closeApplication
        logger.info("--- Application Shutdown Sequence Initiated ---")
        # Note: Further logging might happen inside control_window.closeApplication
        # Logging shutdown now happens within closeApplication