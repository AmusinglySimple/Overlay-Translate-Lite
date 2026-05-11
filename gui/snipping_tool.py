import os
import time
import datetime
import logging
import math

from PySide6.QtCore import Qt, QRect, QPoint, QSize, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QPixmap, QImage, QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QWidget, QApplication, QMessageBox

from utils.config import logger, ensure_support_folder, SUPPORT_FOLDER, get_current_theme, DEFAULT_THEME

class SnippingTool(QWidget):
    def __init__(self, capture_widget):
        super().__init__()
        if not capture_widget:
            logger.critical("SnippingTool requires a valid CaptureWidget instance.")
            raise ValueError("SnippingTool requires a valid CaptureWidget instance.")
        self.capture_widget = capture_widget
        # Get reference to ControlWindow via CaptureWidget
        self.parent_control_window = capture_widget.control_window

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

        self.selection_rect = QRect()
        self.start_point = QPoint()
        self.dragging = False

        # Animation Timer for Glow Effect
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.updateGlow)
        self.glow_phase = 0.0
        self.glow_intensity = 1.0

        self.overlay_color = QColor(0, 0, 0, 100) # Semi-transparent black overlay
        self.setVisible(False) # Initially hidden

    def showEvent(self, event):
        # (Keep the existing showEvent method here)
        logger.debug("SnippingTool shown.")
        desktop_geometry = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(desktop_geometry)
        self.selection_rect = QRect()
        self.dragging = False
        self.glow_phase = 0.0
        if not self.animation_timer.isActive():
            self.animation_timer.start(30) # ~33 FPS for animation
        self.update()
        self.activateWindow() # Try to bring to front
        self.raise_()
        super().showEvent(event)

    def hideEvent(self, event):
        # (Keep the existing hideEvent method here)
        logger.debug("SnippingTool hidden.")
        if self.animation_timer.isActive():
            self.animation_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        # (Keep the existing paintEvent method here, ensure it uses get_current_theme)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw the dark overlay over the entire screen
        painter.fillRect(self.rect(), self.overlay_color)

        # If a selection is being made or is complete
        if not self.selection_rect.isNull() and self.selection_rect.isValid():
            # Clear the selected area (make it transparent)
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self.selection_rect, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver) # Reset composition mode

            # --- Glow Effect ---
            theme_colors = get_current_theme().get("colors", DEFAULT_THEME["colors"])
            glow_base_color = QColor(theme_colors.get("border_accent", "#00ffcc"))
            # Calculate pulsating alpha
            current_glow_alpha = 150 + int(80 * self.glow_intensity * abs(math.sin(self.glow_phase)))
            glow_color = QColor(glow_base_color.red(), glow_base_color.green(), glow_base_color.blue(), current_glow_alpha)

            pen_width = 3
            glow_pen = QPen(glow_color, pen_width)
            glow_pen.setJoinStyle(Qt.RoundJoin) # Nicer corners

            painter.setPen(glow_pen)
            painter.setBrush(Qt.NoBrush)
            # Draw rounded rect slightly outside the selection for the glow
            painter.drawRoundedRect(self.selection_rect.adjusted(-1, -1, 1, 1), 8, 8)

            # --- Dashed Outline ---
            dash_color = QColor(theme_colors.get("border_light", "rgba(255, 255, 255, 50)"))
            dash_pen = QPen(dash_color, 1, Qt.DashLine)
            painter.setPen(dash_pen)
            # Draw rounded rect exactly on the selection boundary
            painter.drawRoundedRect(self.selection_rect, 8, 8)

    def updateGlow(self):
        # (Keep the existing updateGlow method here)
        self.glow_phase += 0.15 # Adjust speed of pulsation
        if self.glow_phase > 2 * math.pi:
            self.glow_phase -= 2 * math.pi
        # Only update the area around the selection rectangle if it exists
        if not self.selection_rect.isNull():
             update_rect = self.selection_rect.adjusted(-5, -5, 5, 5) # Area including glow
             self.update(update_rect)

    def mousePressEvent(self, event: QMouseEvent): # Type hint
        # (Keep the existing mousePressEvent method here)
        if event.button() == Qt.LeftButton:
            self.start_point = event.pos()
            # Start with a tiny rectangle to make it valid
            self.selection_rect = QRect(self.start_point, QSize(1, 1))
            self.dragging = True
            self.update() # Redraw immediately
            event.accept()
        elif event.button() == Qt.RightButton:
             # Cancel snipping on right-click
             logger.debug("Snipping cancelled via right-click.")
             self.hide()
             # Ensure capture widget is shown again if it was hidden
             if self.capture_widget and not self.capture_widget.isVisible():
                 self.capture_widget.show()
             event.accept()

    def mouseMoveEvent(self, event: QMouseEvent): # Type hint
        # (Keep the existing mouseMoveEvent method here)
        if self.dragging and event.buttons() & Qt.LeftButton:
            # Update selection rectangle based on current mouse position
            self.selection_rect = QRect(self.start_point, event.pos()).normalized()
            self.update() # Redraw to show the updated selection
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent): # Type hint
        # (Keep the existing mouseReleaseEvent method here)
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            # Check if the selection is reasonably sized
            if self.selection_rect.width() > 10 and self.selection_rect.height() > 10:
                logger.debug(f"Snip selection finished: {self.selection_rect}")
                self.takeSnip() # Capture the selected area
            else:
                logger.debug("Snip selection too small, cancelled.")
            # Hide the snipping tool after completion or cancellation
            self.hide()
            # Ensure capture widget is shown again
            if self.capture_widget and not self.capture_widget.isVisible():
                self.capture_widget.show()
            event.accept()

    def keyPressEvent(self, event: QKeyEvent): # Type hint
        # (Keep the existing keyPressEvent method here)
         if event.key() == Qt.Key_Escape:
             logger.debug("Snipping cancelled via Escape key.")
             self.hide()
             if self.capture_widget and not self.capture_widget.isVisible():
                 self.capture_widget.show()
             event.accept()
         else:
             super().keyPressEvent(event)

    def takeSnip(self):
        # === MULTI-MONITOR FIX ===
        # Find the correct screen based on where the selection rectangle is
        selection_center = self.selection_rect.center()
        screen = QApplication.screenAt(selection_center)
        if not screen:
            screen = QApplication.primaryScreen()
        if not screen:
             logger.error("Could not get any screen for snipping.")
             QMessageBox.warning(self.parent_control_window, "Snip Error", "Could not access screen for capture.")
             return
        
        # Convert virtual desktop coordinates to screen-relative coordinates
        screen_geo = screen.geometry()
        adjusted_rect = QRect(
            self.selection_rect.x() - screen_geo.x(),
            self.selection_rect.y() - screen_geo.y(),
            self.selection_rect.width(),
            self.selection_rect.height()
        )
        
        # Delay slightly to ensure the semi-transparent overlay is gone
        QTimer.singleShot(50, lambda: self._perform_grab(screen, adjusted_rect))

    def _perform_grab(self, screen, rect):
        # (Keep the existing _perform_grab method here)
        try:
             # Ensure the main capture widget is hidden (should be already, but double-check)
             if self.capture_widget and self.capture_widget.isVisible():
                 logger.warning("CaptureWidget was visible during snip grab attempt - hiding.")
                 self.capture_widget.hide()
                 QApplication.processEvents()
                 time.sleep(0.05)

             # Use 0 for window ID to capture the desktop directly (works across platforms)
             screenshot = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())

             # Show capture widget again immediately after grab
             if self.capture_widget and not self.capture_widget.isVisible():
                 self.capture_widget.show()

             if screenshot.isNull():
                  logger.error("Snipping grabWindow returned a null pixmap.")
                  QMessageBox.warning(self.parent_control_window, "Snip Error", "Failed to capture the selected screen area.")
                  return

             timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
             ensure_support_folder() # Use helper
             fileName = os.path.join(SUPPORT_FOLDER, f"snip_{timestamp}.png") # Use constant

             if not screenshot.save(fileName, "PNG", quality=95): # Good quality PNG
                  logger.error(f"Failed to save snip screenshot to {fileName}")
                  QMessageBox.warning(self.parent_control_window, "Snip Error", "Failed to save the captured snip.")
                  return

             logger.info(f"Snip captured successfully: {fileName}")

             # Update the main capture widget's path for potential metadata saving later
             if self.capture_widget:
                 self.capture_widget.current_capture_path = fileName

             # Trigger translation via the parent ControlWindow
             if self.parent_control_window:
                 # Use helper method in ControlWindow to start translation
                 self.parent_control_window.initiate_translation_from_file(fileName, is_snip=True)
             else:
                  logger.error("Cannot start translation: Parent ControlWindow reference lost.")

        except Exception as e:
             logger.error(f"Error during snip capture or saving: {e}", exc_info=True)
             QMessageBox.critical(self.parent_control_window, "Snip Error", f"An error occurred during snipping:\n{e}")
             # Ensure capture widget is shown even if error occurs
             if self.capture_widget and not self.capture_widget.isVisible():
                 self.capture_widget.show()
