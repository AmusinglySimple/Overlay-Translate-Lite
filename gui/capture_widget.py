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
    get_current_theme, DEFAULT_THEME
)
from utils.helpers import load_settings, get_system_font_path

# Flask server is managed by main.py, no imports needed here

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
        self.threshold = 10 # Increased from 5px to 10px for better hit area
        self.contrast_factor = 1.0 # Default contrast
        self.tempDir = os.path.join(SUPPORT_FOLDER, "temp") # Use support/temp
        
        # Visual enhancements
        self.snap_threshold = 20 # Distance in pixels to trigger snap-to-edge
        self.show_guides = False # Toggle for visual guides (grid, rulers)
        self.capture_history = [] # Store last N capture regions
        self.max_history = 5 # Maximum number of regions to remember

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

        # Server management removed - now handled by main.py
        # Flask server is started in main.py before CaptureWidget initialization

        self.initUI()
        self.populate_fonts()
        # self.start_flask_server() # Removed - server managed by main.py
        self.load_state() # Load geometry and opacity

    # NOTE: First initUI() definition removed — canonical version is below with correct geometry setup

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

    def initUI(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(100, 100, 600, 400)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setMouseTracking(True)
        # Styles applied by global theme in main.py

    # Server management methods removed - Flask server is now managed by main.py
    # No need for start_flask_server(), run_flask(), check_flask_server_readiness()
    # shutdown_flask_server() is also removed as server lifecycle is handled centrally

    def cleanup(self):
        """Clean up CaptureWidget resources."""
        logger.info("Cleaning up CaptureWidget resources...")
        # Server shutdown is now handled by main.py
        
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

        # === ENHANCED RESIZE HANDLE INDICATORS ===
        # Draw corner resize handle (bottom-right)
        painter.setBrush(QBrush(border_color))
        painter.setPen(Qt.NoPen)
        handle_size = 20  # Larger, more visible handle
        handle_x = self.width() - handle_size - 2
        handle_y = self.height() - handle_size - 2
        
        # Draw three lines forming a corner grip pattern
        painter.setPen(QPen(border_color, 2))
        grip_offset = 5
        for i in range(3):
            y_pos = handle_y + grip_offset + (i * 5)
            x_start = handle_x + grip_offset + (i * 5)
            painter.drawLine(x_start, y_pos, handle_x + handle_size - grip_offset, y_pos)
            painter.drawLine(x_start, y_pos, x_start, handle_y + handle_size - grip_offset)
        
        # Draw corner indicators at all four corners
        corner_size = 8
        corner_length = 20
        painter.setPen(QPen(border_color, 2))
        
        # Top-left
        painter.drawLine(2, corner_length, 2, 2)
        painter.drawLine(2, 2, corner_length, 2)
        
        # Top-right
        painter.drawLine(self.width() - corner_length - 2, 2, self.width() - 2, 2)
        painter.drawLine(self.width() - 2, 2, self.width() - 2, corner_length)
        
        # Bottom-left
        painter.drawLine(2, self.height() - corner_length, 2, self.height() - 2)
        painter.drawLine(2, self.height() - 2, corner_length, self.height() - 2)
        
        # Draw center crosshair (optional guide)
        if self.show_guides:
            painter.setPen(QPen(QColor(255, 255, 255, 100), 1, Qt.DashLine))
            center_x = self.width() // 2
            center_y = self.height() // 2
            crosshair_size = 30
            
            # Horizontal line
            painter.drawLine(center_x - crosshair_size, center_y, center_x + crosshair_size, center_y)
            # Vertical line
            painter.drawLine(center_x, center_y - crosshair_size, center_x, center_y + crosshair_size)
            
            # Draw dimension text
            painter.setPen(QPen(QColor(255, 255, 255, 200)))
            painter.drawText(center_x + 10, center_y - 10, f"{self.width()}x{self.height()}")


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
             QMessageBox.critical(self.control_window, self.tr("Viewer Error"), self.tr("Cannot display result: Original image file missing."))
             return

        # Pass necessary font info and language code to the viewer
        try:
            logger.debug("Creating TranslatedImageViewer instance...")
            
            viewer = TranslatedImageViewer(
                image_path=file_name,
                boxes=boxes,
                translated_lines=translated_lines,
                initial_font_size=self.default_font_size, # Pass size hint
                target_language_code=target_language_code, # Crucial for font selection
                control_window_ref=self.control_window, # Pass the reference
                parent=self.control_window # Parent to control window
            )
            logger.debug("Showing TranslatedImageViewer dialog...")
            viewer.exec() # Show as modal dialog
            logger.debug("TranslatedImageViewer closed.")
        except RuntimeError as re:
            # Handle C++ object deleted (e.g. control_window destroyed during viewer creation)
            logger.warning(f"RuntimeError creating viewer (C++ object may be deleted): {re}")
            try:
                viewer = TranslatedImageViewer(
                    image_path=file_name, boxes=boxes, translated_lines=translated_lines,
                    initial_font_size=self.default_font_size, target_language_code=target_language_code,
                    control_window_ref=None, parent=None
                )
                viewer.exec()
            except Exception as fallback_e:
                logger.error(f"Fallback viewer also failed: {fallback_e}", exc_info=True)
        except Exception as e:
            logger.error(f"Failed to create or show TranslatedImageViewer: {e}", exc_info=True)
            try:
                QMessageBox.critical(self.control_window, self.tr("Viewer Error"), self.tr("Could not display the translated image viewer:\n{}").format(e))
            except RuntimeError:
                logger.critical(f"Could not display error dialog because control_window is dead. Error was: {e}")

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
                 
                 # === MULTI-SCREEN SUPPORT ===
                 # Get the screen where the cursor currently is
                 current_screen = QApplication.screenAt(global_pos)
                 if current_screen is None:
                     # Fallback to primary screen if cursor is not on any screen
                     current_screen = QApplication.primaryScreen()
                 
                 screen_geo = current_screen.availableGeometry()
                 
                 # === SNAP-TO-EDGE FUNCTIONALITY ===
                 # Check if near screen edges and snap if within threshold
                 if abs(new_pos.x() - screen_geo.left()) < self.snap_threshold:
                     new_pos.setX(screen_geo.left())  # Snap to left edge
                 elif abs(new_pos.x() + self.width() - screen_geo.right()) < self.snap_threshold:
                     new_pos.setX(screen_geo.right() - self.width())  # Snap to right edge
                 
                 if abs(new_pos.y() - screen_geo.top()) < self.snap_threshold:
                     new_pos.setY(screen_geo.top())  # Snap to top edge
                 elif abs(new_pos.y() + self.height() - screen_geo.bottom()) < self.snap_threshold:
                     new_pos.setY(screen_geo.bottom() - self.height())  # Snap to bottom edge
                 
                 # Allow movement across all screens - no hard boundaries
                 # The window can be moved freely between monitors
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
                 # Save current region to history when resize finishes
                 self.save_to_history()
                 logger.debug("Resize finished.")
                 event.accept()
             elif self.dragging:
                 self.dragging = False
                 self.unsetCursor()
                 # Save current region to history when drag finishes
                 self.save_to_history()
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
    
    # === CAPTURE HISTORY METHODS ===
    
    def save_to_history(self):
        """Save current capture region to history."""
        current_region = {
            'x': self.x(),
            'y': self.y(),
            'width': self.width(),
            'height': self.height(),
            'timestamp': time.time()
        }
        
        # Check if this region is significantly different from the last one
        if self.capture_history:
            last = self.capture_history[-1]
            # Don't add if position/size changed by less than 5 pixels
            if (abs(current_region['x'] - last['x']) < 5 and
                abs(current_region['y'] - last['y']) < 5 and
                abs(current_region['width'] - last['width']) < 5 and
                abs(current_region['height'] - last['height']) < 5):
                return  # Too similar, skip
        
        self.capture_history.append(current_region)
        
        # Keep only last N regions
        if len(self.capture_history) > self.max_history:
            self.capture_history.pop(0)
        
        logger.debug(f"Saved capture region to history ({len(self.capture_history)}/{self.max_history})")
    
    def restore_from_history(self, index=-1):
        """
        Restore a capture region from history.
        
        Args:
            index: Index in history list (default -1 = most recent)
        """
        if not self.capture_history:
            logger.warning("No capture history available")
            return False
        
        try:
            region = self.capture_history[index]
            self.setGeometry(region['x'], region['y'], region['width'], region['height'])
            logger.info(f"Restored capture region from history: {region['width']}x{region['height']} at ({region['x']}, {region['y']})")
            return True
        except IndexError:
            logger.error(f"Invalid history index: {index}")
            return False
    
    def get_history_list(self):
        """Get list of capture regions in history with human-readable info."""
        result = []
        for i, region in enumerate(self.capture_history):
            result.append({
                'index': i,
                'size': f"{region['width']}x{region['height']}",
                'position': f"({region['x']}, {region['y']})",
                'timestamp': region['timestamp']
            })
        return result
    
    def toggle_guides(self):
        """Toggle visual guides (grid, crosshair, dimensions)."""
        self.show_guides = not self.show_guides
        self.update()  # Trigger repaint
        logger.debug(f"Visual guides {'enabled' if self.show_guides else 'disabled'}")
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts for capture widget."""
        # Ctrl+G: Toggle guides
        if event.key() == Qt.Key_G and event.modifiers() & Qt.ControlModifier:
            self.toggle_guides()
            event.accept()
        # Ctrl+H: Show history (cycle through)
        elif event.key() == Qt.Key_H and event.modifiers() & Qt.ControlModifier:
            if self.restore_from_history(-1):  # Restore most recent
                event.accept()
            else:
                event.ignore()
        # Ctrl+Left/Right: Navigate history
        elif event.key() == Qt.Key_Left and event.modifiers() & Qt.ControlModifier:
            if len(self.capture_history) > 1:
                # Move to previous
                self.restore_from_history(-2)
                event.accept()
            else:
                event.ignore()
        else:
            super().keyPressEvent(event)