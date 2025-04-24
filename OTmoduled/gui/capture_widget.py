# gui/capture_widget.py
import os
import tempfile
import logging
import time
import requests
import threading
import math
from PIL import Image, ImageDraw, ImageFont # Keep PIL import if needed elsewhere, maybe not for paintEvent

from PySide6 import QtCore # Import QtCore here
from PySide6.QtCore import Qt, QPoint, QRect, QTimer, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QCursor, QImage, QPixmap, QMouseEvent
from PySide6.QtWidgets import QWidget, QApplication, QMessageBox

# Internal imports (relative where possible)
from .dialogs import TranslatedImageViewer # Import the viewer dialog

# Utility imports
from utils.config import (
    SUPPORT_FOLDER, MIN_OPACITY, logger, ensure_support_folder,
    get_current_theme, DEFAULT_THEME # <--- IMPORT get_current_theme and DEFAULT_THEME HERE
)
from utils.helpers import load_settings, get_system_font_path # Import helpers
# gui/capture_widget.py
# ... other imports ...

# Flask App import
# Correct way to import from the parent directory (project root)
try:
    import sys
    import os
    # Get the absolute path of the project root (one level up from gui)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Add the project root to the Python path ONLY IF it's not already there
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        logger.debug(f"Added project root to sys.path: {project_root}")

    from app import app as flask_app # Now this should work if app.py is in OTmoduled
    if flask_app:
        logger.info("Successfully imported Flask app from app.py")
    else:
        # This case shouldn't happen if import works, but good for debugging
        logger.error("Flask app import resulted in None.")
        flask_app = None

except ImportError as e:
    logger.critical(f"ImportError: Could not import 'app' from app.py: {e}. Ensure app.py is in the project root ({project_root}).", exc_info=True)
    flask_app = None # Indicate flask is not available
except Exception as flask_import_err:
    logger.critical(f"Unexpected error importing Flask app: {flask_import_err}", exc_info=True)
    flask_app = None

# ... rest of the CaptureWidget class ...

class CaptureWidget(QWidget):
    def __init__(self, parent=None, control_window=None):
        super().__init__(parent)
        if control_window is None:
             logger.critical("CaptureWidget initialized without ControlWindow!")
             raise ValueError("ControlWindow reference is required for CaptureWidget.")

        self.control_window = control_window
        # Initialize from control window's state
        self.target_language = control_window.target_language
        self.default_font_size = control_window.default_font_size
        self.default_font_type = control_window.default_font_type

        self.fonts = {} # Populated in populate_fonts
        self.threshold = 5 # For resize handle detection
        self.contrast_factor = 1.0 # Default contrast
        self.tempDir = os.path.join(SUPPORT_FOLDER, "temp") # Use support/temp

        try:
             if not os.path.exists(self.tempDir):
                 os.makedirs(self.tempDir)
             logger.info(f"Using temporary directory: {self.tempDir}")
        except OSError as e:
             logger.error(f"Failed to create temporary directory {self.tempDir}: {e}. Falling back.")
             self.tempDir = tempfile.mkdtemp(prefix="OverlayTranslate_") # Fallback

        self.original_text = ""
        self.translated_text = ""
        self.current_capture_path = "" # Path of the original PNG saved
        self.resizing = False
        self.dragging = False
        self.offset = QPoint()
        self.borderRadius = 15
        self.force_click_through = False

        # Flask server management
        self.flask_thread = None
        self.flask_running = False
        self.flask_server_ready = threading.Event()

        self.initUI()
        self.populate_fonts()
        self.start_flask_server()
        self.load_state() # Load geometry and opacity

    def initUI(self):
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMouseTracking(True)
        # Styles applied by global theme in main.py

    def populate_fonts(self):
        # Use helper function
        self.fonts = {
            "default": get_system_font_path("default"),
            "Arial": get_system_font_path("Arial"),
            "zh": get_system_font_path("zh"),
            "ja": get_system_font_path("ja"),
            "ko": get_system_font_path("ko")
        }
        logger.debug(f"Populated fonts for CaptureWidget: {self.fonts}")

    def start_flask_server(self):
        # (Keep the existing start_flask_server method here)
        # Ensure it uses the logger and flask_app imported correctly
        if self.flask_running:
            logger.warning("Flask server thread already marked as running.")
            return
        if not flask_app:
            logger.error("Flask app not imported. Cannot start internal server.")
            self.flask_server_ready.set() # Signal immediately (as failure)
            return

        def run_flask():
            # Use nonlocal self if needed, but it should be accessible via instance
            try:
                logger.info("Starting Flask server thread...")
                # Mark as running *before* starting the blocking call
                # Use self directly as it's part of the instance method scope
                self.flask_running = True
                # We cannot easily pass the logger here, Flask logs independently
                flask_app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
                # This line is reached only after the server stops
                logger.info("Flask server run() method finished.")
            except OSError as e:
                 if "address already in use" in str(e).lower():
                     logger.warning(f"Flask server port 5000 already in use. Assuming external server.")
                     # Don't set flask_running to false here if external is assumed
                     self.flask_server_ready.set() # Signal readiness (or assumed readiness)
                     if self.control_window:
                          # Use invokeMethod for thread safety calling GUI slots
                          QtCore.QMetaObject.invokeMethod(self.control_window, "displayTranslationError", Qt.QueuedConnection, QtCore.Q_ARG(str, "Port 5000 in use. Using existing server?"))
                 else:
                     logger.error(f"Flask server thread OS error: {e}", exc_info=True)
                     self.flask_running = False # Mark as not running on error
                     self.flask_server_ready.set() # Signal completion/failure
                     if self.control_window:
                         QtCore.QMetaObject.invokeMethod(self.control_window, "displayTranslationError", Qt.QueuedConnection, QtCore.Q_ARG(str, f"Failed to start translation server (OS Error): {e}"))
            except Exception as e:
                logger.error(f"Flask server thread exception: {e}", exc_info=True)
                self.flask_running = False # Mark as not running on error
                self.flask_server_ready.set() # Signal completion/failure
                if self.control_window:
                     QtCore.QMetaObject.invokeMethod(self.control_window, "displayTranslationError", Qt.QueuedConnection, QtCore.Q_ARG(str, f"Failed to start translation server (Exception): {e}"))
            finally:
                logger.info("Flask server thread function exiting.")
                self.flask_running = False # Ensure flag is false on any exit path
                if not self.flask_server_ready.is_set():
                    self.flask_server_ready.set() # Ensure event is set if not already

        self.flask_thread = threading.Thread(target=run_flask, name="FlaskServerThread", daemon=True)
        self.flask_thread.start()

        # Start checker thread
        checker_thread = threading.Thread(target=self.check_flask_server_readiness, name="FlaskReadyCheckThread", daemon=True)
        checker_thread.start()


    def check_flask_server_readiness(self):
        # (Keep the existing check_flask_server_readiness method here)
        start_time = time.time()
        timeout = 10 # Check for 10 seconds
        server_ready = False
        # Check flask_running flag in the loop condition
        while time.time() - start_time < timeout and not server_ready and self.flask_running:
            try:
                # Use a simple endpoint that should exist in app.py
                response = requests.get("http://127.0.0.1:5000/", timeout=1) # Check base URL or /api/languages
                # Check for 200 OK or maybe redirect (3xx) if base URL redirects
                if 200 <= response.status_code < 400:
                    logger.info("Flask server is ready.")
                    server_ready = True
                    self.flask_server_ready.set() # Signal success
                    return # Exit checker thread
            except requests.ConnectionError:
                logger.debug("Flask server not ready yet (connection refused)...")
            except requests.Timeout:
                logger.debug("Flask server readiness check timed out, retrying...")
            except Exception as e:
                logger.error(f"Error checking Flask server readiness: {e}")

            if not server_ready:
                time.sleep(0.5)

        # After loop finishes or flask_running becomes False
        if not self.flask_server_ready.is_set():
            if not self.flask_running:
                 logger.error("Flask server thread terminated before readiness check completed.")
                 if self.control_window:
                     QtCore.QMetaObject.invokeMethod(self.control_window, "displayTranslationError", Qt.QueuedConnection, QtCore.Q_ARG(str, "Translation server stopped prematurely."))
            elif not server_ready:
                 logger.error(f"Flask server did not become ready within {timeout} seconds.")
                 if self.control_window:
                      QtCore.QMetaObject.invokeMethod(self.control_window, "displayTranslationError", Qt.QueuedConnection, QtCore.Q_ARG(str, "Translation server failed to start (timeout)."))
            self.flask_server_ready.set() # Ensure event is set on timeout or thread stop


    def shutdown_flask_server(self):
        # (Keep the existing shutdown_flask_server method here)
        if not self.flask_running:
            # Check if it might be running externally (port in use state)
            # This check is tricky, maybe just log based on flask_running flag
            logger.info("Internal Flask server not marked as running. Skipping shutdown request.")
            return

        logger.info("Requesting Flask server shutdown via HTTP...")
        shutdown_url = "http://127.0.0.1:5000/shutdown" # Assume this route exists in app.py
        try:
            # Send request, don't wait too long as server might close connection immediately
            requests.post(shutdown_url, timeout=2)
            logger.info("Flask server shutdown request sent.")
        except requests.exceptions.ConnectionError:
             # This is expected if the server shuts down quickly
             logger.info("Flask server connection closed during shutdown request (likely successful).")
        except requests.Timeout:
             logger.warning("Flask server shutdown request timed out.")
        except Exception as e:
            logger.error(f"Failed to send shutdown request to Flask server ({shutdown_url}): {e}")

        # Join the thread
        if self.flask_thread and self.flask_thread.is_alive():
            logger.debug("Flask server thread joining (short timeout)...")
            self.flask_thread.join(timeout=1.0) # Slightly longer timeout
            if self.flask_thread.is_alive():
                logger.warning("Flask server thread did not terminate quickly. Proceeding with exit.")
            else:
                logger.info("Flask server thread joined successfully.")
        else:
             logger.debug("Flask server thread was already finished or not started.")
        self.flask_running = False # Ensure flag is false after attempted shutdown


    def cleanup(self):
        # (Keep the existing cleanup method here)
        logger.info("Cleaning up CaptureWidget resources...")
        self.shutdown_flask_server()
        if hasattr(self, 'tempDir') and os.path.exists(self.tempDir):
            logger.info(f"Cleaning up temporary directory: {self.tempDir}")
            ensure_support_folder() # Ensure main support folder exists before cleanup
            try:
                # More robust cleanup: iterate and remove contents
                for item_name in os.listdir(self.tempDir):
                    item_path = os.path.join(self.tempDir, item_name)
                    try:
                        if os.path.isfile(item_path) or os.path.islink(item_path):
                            os.unlink(item_path)
                        elif os.path.isdir(item_path):
                            # Be cautious removing directories if not expected
                            # For now, only remove files.
                            logger.warning(f"Skipping directory in temp folder: {item_path}")
                            # If needed: import shutil; shutil.rmtree(item_path)
                    except Exception as e:
                        logger.error(f"Failed to delete temp item {item_path}: {e}")
                # Optionally remove the temp dir itself if empty
                # try:
                #     os.rmdir(self.tempDir)
                #     logger.info(f"Removed empty temporary directory: {self.tempDir}")
                # except OSError:
                #     logger.warning(f"Temporary directory {self.tempDir} not empty, leaving.")
            except Exception as e:
                logger.error(f"Error during temp directory cleanup: {e}")


    def paintEvent(self, event):
        # (Method where the error occurred - now fixed with import)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Use themed colors for the overlay background and border
        # Safely get theme, fallback to default if needed during init phases
        theme_data = get_current_theme() if get_current_theme() else DEFAULT_THEME
        theme_colors = theme_data.get("colors", DEFAULT_THEME["colors"])

        # --- Use opacity set on the window itself ---
        # bg_color = QColor(theme_colors.get("bg_groupbox", "#961E1E1E"))
        # # Make overlay slightly more transparent than default groupbox
        # bg_color.setAlpha(int(bg_color.alpha() * 0.7)) # Adjust alpha multiplier as needed
        # painter.setBrush(QBrush(bg_color))
        # --- No longer set brush alpha directly, rely on window opacity ---
        painter.setBrush(QBrush(QColor(theme_colors.get("bg_groupbox", "#961E1E1E"))))

        border_color = QColor(theme_colors.get("border_accent", "#FF00FFCC"))
        painter.setPen(QPen(border_color, 2)) # Use themed border color

        # Adjust draw rect slightly to prevent border being clipped at edges
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), self.borderRadius, self.borderRadius)

        # Draw resize handle indicator
        painter.setBrush(QBrush(border_color))
        painter.setPen(Qt.NoPen) # No border for the handle itself
        handle_size = self.borderRadius # Make handle size match radius
        # Adjust handle position to be fully inside the border
        handle_x = self.width() - handle_size - 1 # Offset by border width
        handle_y = self.height() - handle_size - 1 # Offset by border width
        handle_rect = QRect(handle_x, handle_y, handle_size, handle_size)
        # Draw a small square or triangle? Square is simpler.
        painter.drawRect(handle_rect)


    def displayTranslatedImage(self, result, original_file_path, target_language_code):
        # Ensure it imports TranslatedImageViewer from .dialogs
        # Ensure it passes necessary info like fonts, sizes, language code
        logger.info("Attempting to display TranslatedImageViewer...")
        logger.debug(f"Display Result Data: boxes={len(result.get('boxes',[]))}, lines={len(result.get('translated_lines',[]))}")
        logger.debug(f"Target Language for Viewer Font: {target_language_code}")

        file_name = original_file_path
        boxes = result.get('boxes', [])
        translated_lines = result.get('translated_lines', [])

        if not file_name or not os.path.exists(file_name):
             logger.error(f"Cannot display viewer: Original capture path '{file_name}' is invalid or missing.")
             QMessageBox.critical(self.control_window, "Viewer Error", "Cannot display result: Original image file missing.")
             return

        # Pass necessary font info and language code to the viewer
        try:
            logger.debug("Creating TranslatedImageViewer instance...")
            # --- CORRECTED CALL: Removed initial_font_path_unused ---
            viewer = TranslatedImageViewer(
                image_path=file_name,
                boxes=boxes,
                translated_lines=translated_lines,
                initial_font_size=self.default_font_size, # Pass size hint
                target_language_code=target_language_code, # Crucial for font selection
                control_window_ref=self.control_window, # Pass the reference
                parent=self.control_window # Parent to control window (optional but good)
            )
            # --- END CORRECTION ---
            logger.debug("Showing TranslatedImageViewer dialog...")
            viewer.exec() # Show as modal dialog
            logger.debug("TranslatedImageViewer closed.")
        except Exception as e:
            logger.error(f"Failed to create or show TranslatedImageViewer: {e}", exc_info=True)
            QMessageBox.critical(self.control_window, "Viewer Error", f"Could not display the translated image viewer:\n{e}")

    def toggleClickThrough(self):
        # (Keep the existing toggleClickThrough method here)
        self.force_click_through = not self.force_click_through
        self.updateClickThroughState()
        if self.control_window:
            # Update button text in control window
            button_text = "Make Interactive (F2)" if self.force_click_through else "Make Click-Through (F2)"
            tooltip = "Make overlay interactive (stops click-through)" if self.force_click_through else "Allow mouse clicks to pass through the overlay"
            self.control_window.toggle_btn.setText(button_text)
            self.control_window.toggle_btn.setToolTip(tooltip)
        logging.info(f"User forced click-through toggled {'ON' if self.force_click_through else 'OFF'}.")


    def updateClickThroughState(self):
        # --- Refined Logic ---
        opacity = self.windowOpacity()
        # Click-through ONLY if forced OR if opacity is effectively zero/minimal
        should_be_click_through = self.force_click_through or (opacity <= MIN_OPACITY)

        current_flags = self.windowFlags()
        is_currently_click_through = bool(current_flags & Qt.WindowTransparentForInput)

        needs_flag_update = (should_be_click_through != is_currently_click_through)

        # Check visibility state BEFORE potential hide/show
        was_visible = self.isVisible()
        should_be_visible = opacity > 0 # Widget should be visible if opacity > 0

        if needs_flag_update:
            logger.debug(f"Updating click-through flag. Should be: {should_be_click_through} (Forced: {self.force_click_through}, Opacity: {opacity:.3f})")
            if should_be_click_through:
                self.setWindowFlags(current_flags | Qt.WindowTransparentForInput)
                self.setCursor(Qt.ArrowCursor) # Ensure default cursor when click-through
            else:
                self.setWindowFlags(current_flags & ~Qt.WindowTransparentForInput)
                self.setCursor(Qt.ArrowCursor) # Default interactive cursor

            # Re-apply flags by hiding and showing (required)
            self.hide()
            # Re-show ONLY if it's supposed to be visible based on opacity AND was visible before
            if should_be_visible and was_visible:
                self.show()
            elif not should_be_visible and was_visible:
                 logger.debug("Widget remains hidden due to zero opacity after flag update.")
            elif should_be_visible and not was_visible:
                 # This case should be rare, but if it was hidden but opacity > 0, show it.
                 logger.debug("Widget was hidden but should be visible, showing after flag update.")
                 self.show()

        elif not self.isVisible() and should_be_visible:
            # If flags didn't need update, but widget is hidden and shouldn't be (opacity > 0)
            logger.debug(f"Widget is hidden but opacity={opacity:.3f} > 0. Showing.")
            self.show()
        elif self.isVisible() and not should_be_visible:
             # If flags didn't need update, but widget is visible and shouldn't be (opacity == 0)
             logger.debug(f"Widget is visible but opacity={opacity:.3f} <= 0. Hiding.")
             self.hide()
        # --- End Refined Logic ---


    def is_on_resize_corner(self, pos: QPoint): # Type hint
        # (Keep the existing is_on_resize_corner method here)
        handle_size = self.borderRadius + self.threshold # Add threshold to handle size
        return (pos.x() >= self.width() - handle_size and
                pos.y() >= self.height() - handle_size)

    def mousePressEvent(self, event: QMouseEvent): # Type hint
        # (Keep the existing mousePressEvent method here)
        is_click_through_active = bool(self.windowFlags() & Qt.WindowTransparentForInput)
        if is_click_through_active:
             event.ignore()
             return

        if event.button() == Qt.LeftButton:
             pos = event.position().toPoint() # Convert QPointF
             if self.is_on_resize_corner(pos):
                 self.resizing = True
                 # Calculate offset relative to bottom-right corner for stable resizing
                 self.offset = self.geometry().bottomRight() - event.globalPosition().toPoint()
                 self.setCursor(Qt.SizeFDiagCursor)
                 logger.debug("Resize started.")
                 event.accept()
             else:
                 self.dragging = True
                 self.offset = pos # Offset relative to click position within widget
                 self.setCursor(Qt.SizeAllCursor)
                 logger.debug("Drag started.")
                 event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent): # Type hint
        # (Keep the existing mouseMoveEvent method here)
         is_click_through_active = bool(self.windowFlags() & Qt.WindowTransparentForInput)
         if is_click_through_active:
              event.ignore()
              return

         if event.buttons() & Qt.LeftButton:
             global_pos = event.globalPosition().toPoint() # Convert QPointF
             if self.resizing:
                 new_bottom_right = global_pos + self.offset
                 # Prevent negative width/height and enforce minimums
                 new_width = max(100, new_bottom_right.x() - self.geometry().left())
                 new_height = max(50, new_bottom_right.y() - self.geometry().top())
                 # Add screen boundary checks if needed during resize
                 self.resize(new_width, new_height)
                 event.accept()
             elif self.dragging:
                 new_pos = global_pos - self.offset
                 screen_geo = QApplication.primaryScreen().availableGeometry()
                 # Keep window fully on screen
                 new_pos.setX(max(screen_geo.left(), min(new_pos.x(), screen_geo.right() - self.width())))
                 new_pos.setY(max(screen_geo.top(), min(new_pos.y(), screen_geo.bottom() - self.height())))
                 self.move(new_pos)
                 event.accept()
             else: # Redundant check inside button press, but safe
                  event.ignore()
         else: # Mouse move without button press (for cursor changes)
              pos = event.position().toPoint() # Convert QPointF
              if self.is_on_resize_corner(pos):
                  self.setCursor(Qt.SizeFDiagCursor)
              else:
                  self.setCursor(Qt.ArrowCursor) # Default cursor when interactive
              event.ignore()


    def mouseReleaseEvent(self, event: QMouseEvent): # Type hint
        # (Keep the existing mouseReleaseEvent method here)
         is_click_through_active = bool(self.windowFlags() & Qt.WindowTransparentForInput)
         if is_click_through_active:
              event.ignore()
              return

         if event.button() == Qt.LeftButton:
             if self.resizing:
                 self.resizing = False
                 self.unsetCursor()
                 # Saving handled by ControlWindow on exit
                 logger.debug("Resize finished.")
                 event.accept()
             elif self.dragging:
                 self.dragging = False
                 self.unsetCursor()
                 # Saving handled by ControlWindow on exit
                 logger.debug("Drag finished.")
                 event.accept()
             else:
                 event.ignore()
         else:
             super().mouseReleaseEvent(event)

    def load_state(self):
        # (Keep the existing load_state method here)
        settings = load_settings() # Load all settings
        if 'CaptureWidget' in settings:
             try:
                 state = settings['CaptureWidget']
                 opacity = 0.8 # Default
                 if all(k in state for k in ('x', 'y', 'width', 'height')):
                     self.setGeometry(int(state['x']), int(state['y']), int(state['width']), int(state['height']))
                     opacity = float(state.get('opacity', 0.8)) # Get opacity if saved
                     # Set initial opacity, MIN_OPACITY check handled by setter/slider
                     self.setWindowOpacity(max(MIN_OPACITY, opacity))
                     # Don't force click-through on load, let opacity/F2 decide
                     self.updateClickThroughState()
                     logger.debug(f"Loaded CaptureWidget state: Geo={self.geometry()}, Opacity: {self.windowOpacity():.2f}")
                 else:
                     logger.warning("CaptureWidget state incomplete. Using default geometry.")
                     self.setGeometry(100, 100, 600, 400)
                     self.setWindowOpacity(0.8) # Apply default opacity
                     self.updateClickThroughState()
             except (ValueError, TypeError, KeyError) as e:
                 logger.error(f"Error loading CaptureWidget state: {e}. Using default.", exc_info=True)
                 self.setGeometry(100, 100, 600, 400)
                 self.setWindowOpacity(0.8)
                 self.updateClickThroughState()
        else:
             logger.info("No CaptureWidget state found. Using default geometry and opacity.")
             self.setGeometry(100, 100, 600, 400)
             self.setWindowOpacity(0.8)
             self.updateClickThroughState()


    def get_state(self):
        # (Keep the existing get_state method here)
        # Returns a dict to be saved by ControlWindow
        return {
            'x': self.x(), 'y': self.y(),
            'width': self.width(), 'height': self.height(),
            'opacity': self.windowOpacity()
        }

    def closeEvent(self, event):
        # (Keep the existing closeEvent method here, saving is handled by ControlWindow)
        logger.debug("CaptureWidget closeEvent called.")
        # Cleanup is called explicitly by ControlWindow before closing this widget
        event.accept()