import logging
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QApplication, QWidget, QMenu
)
from PySide6.QtCore import Qt, QPoint, QRect, Signal, QSize
from PySide6.QtGui import (
    QColor, QPainter, QPen, QLinearGradient, QPixmap, QImage, QMouseEvent
)

logger = logging.getLogger("OverlayTranslate")

class ColorBarPicker(QWidget):
    # (Keep the existing ColorBarPicker class here)
    # ... (copy the class from otfull2.py) ...
    colorChanged = Signal(QColor)

    def __init__(self, initial_color=QColor(0, 0, 255, 255), parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 80) # Adjusted height for value slider
        h, s, v, a = initial_color.getHsvF()
        self.hue = h if h != -1 else 0.0
        self.saturation = s
        self.value = v
        self.alpha = initial_color.alpha() # Store alpha as int 0-255
        self.setMouseTracking(True)
        self.initUI()
        self.updateSliders()
        self.updateSlidersBackground()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.hue_bar_widget = QWidget(self)
        self.hue_bar_widget.setFixedHeight(20)
        self.hue_bar_widget.setCursor(Qt.PointingHandCursor)
        self.hue_bar_widget.paintEvent = self.paintHueBar
        self.hue_bar_widget.mousePressEvent = self.hueBarMousePress
        self.hue_bar_widget.mouseMoveEvent = self.hueBarMouseMove
        layout.addWidget(self.hue_bar_widget)

        saturation_layout = QHBoxLayout()
        saturation_layout.addWidget(QLabel("S:"))
        self.saturation_slider = QSlider(Qt.Horizontal, self)
        self.saturation_slider.setRange(0, 100)
        self.saturation_slider.valueChanged.connect(self.updateSaturation)
        saturation_layout.addWidget(self.saturation_slider)
        layout.addLayout(saturation_layout)

        value_layout = QHBoxLayout()
        value_layout.addWidget(QLabel("V:"))
        self.value_slider = QSlider(Qt.Horizontal, self)
        self.value_slider.setRange(0, 100)
        self.value_slider.valueChanged.connect(self.updateValue)
        value_layout.addWidget(self.value_slider)
        layout.addLayout(value_layout)

    def paintHueBar(self, event):
        painter = QPainter(self.hue_bar_widget)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.hue_bar_widget.rect()
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        steps = 6
        for i in range(steps + 1):
            gradient.setColorAt(i / steps, QColor.fromHsvF(i / steps, 1.0, 1.0, 1.0)) # Opaque
        painter.fillRect(rect, gradient)
        hue_pos_x = int(self.hue * rect.width())
        indicator_color = Qt.white if self.value < 0.5 else Qt.black
        painter.setPen(QPen(indicator_color, 2))
        painter.drawLine(hue_pos_x, rect.top(), hue_pos_x, rect.bottom())

    def updateColorFromQColor(self, color):
        h, s, v, a = color.getHsvF()
        self.hue = h if h != -1 else self.hue
        self.saturation = s
        self.value = v
        self.alpha = color.alpha()
        self.updateSliders()
        self.updateSlidersBackground()
        self.hue_bar_widget.update()

    def updateSliders(self):
        self.saturation_slider.blockSignals(True)
        self.value_slider.blockSignals(True)
        self.saturation_slider.setValue(int(self.saturation * 100))
        self.value_slider.setValue(int(self.value * 100))
        self.saturation_slider.blockSignals(False)
        self.value_slider.blockSignals(False)

    def updateSlidersBackground(self):
         sat_start_color = QColor.fromHsvF(self.hue, 0.0, self.value, 1.0) # Opaque
         sat_end_color = QColor.fromHsvF(self.hue, 1.0, self.value, 1.0)   # Opaque
         slider_style = """
             QSlider::groove:horizontal { height: 8px; background: #555; border-radius: 4px; }
             QSlider::handle:horizontal { background: white; border: 1px solid #aaa; width: 14px; height: 14px; border-radius: 7px; margin: -3px 0; }
             QSlider::sub-page:horizontal { border-radius: 4px; }
         """
         sat_style = slider_style + f"QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {sat_start_color.name()}, stop:1 {sat_end_color.name()}); }}"
         self.saturation_slider.setStyleSheet(sat_style)

         val_start_color = QColor.fromHsvF(self.hue, self.saturation, 0.0, 1.0) # Black (Opaque)
         val_end_color = QColor.fromHsvF(self.hue, self.saturation, 1.0, 1.0) # Full value color (Opaque)
         val_style = slider_style + f"QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {val_start_color.name()}, stop:1 {val_end_color.name()}); }}"
         self.value_slider.setStyleSheet(val_style)

    def hueBarMousePress(self, event):
        if event.button() == Qt.LeftButton: self.updateHueFromMouse(event.position())
    def hueBarMouseMove(self, event):
        if event.buttons() & Qt.LeftButton: self.updateHueFromMouse(event.position())

    def updateHueFromMouse(self, pos):
        x = max(0, min(pos.x(), self.hue_bar_widget.width()))
        self.hue = x / self.hue_bar_widget.width()
        self.hue_bar_widget.update()
        self.updateSlidersBackground()
        self.emitColorChange()

    def updateSaturation(self, value):
        self.saturation = value / 100.0
        self.updateSlidersBackground()
        self.emitColorChange()

    def updateValue(self, value):
        self.value = value / 100.0
        self.updateSlidersBackground()
        self.hue_bar_widget.update()
        self.emitColorChange()

    def emitColorChange(self):
        new_color = QColor.fromHsv(int(self.hue * 359), int(self.saturation * 255), int(self.value * 255), self.alpha)
        self.colorChanged.emit(new_color)

    def getColor(self):
        return QColor.fromHsv(int(self.hue * 359), int(self.saturation * 255), int(self.value * 255), self.alpha)

    def setColor(self, color):
        self.updateColorFromQColor(color)


class DraggableResizableWidget(QWidget):
    # (Keep the existing DraggableResizableWidget class here)
    # ... (copy the class from otfull2.py) ...
    def __init__(self, widget, parent=None):
        super().__init__(parent)
        self.widget = widget
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(widget)
        self.setMinimumSize(50, 50)

        self.dragging = False
        self.resizing = False
        self.drag_start_pos = None
        self.resize_start_pos = None
        self.original_pos = None
        self.original_size = None
        self.is_in_design_mode = False # Controlled externally

        self.handle_size = 10
        self.drag_handle_rect = QRect() # Initialized in paintEvent
        self.resize_handle_rect = QRect() # Initialized in paintEvent

        self.setMouseTracking(True) # Needed for hover cursors

    def set_design_mode(self, enabled):
        self.is_in_design_mode = enabled
        self.update() # Trigger repaint

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.is_in_design_mode:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Dashed border around the widget
            pen = QPen(QColor(0, 255, 204, 150), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush) # No fill for the border rectangle
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1)) # Adjust to be inside bounds

            # Drag handle (Top-Left)
            painter.setBrush(QColor(0, 255, 204, 180))
            painter.setPen(Qt.NoPen)
            self.drag_handle_rect = QRect(0, 0, self.handle_size, self.handle_size)
            painter.drawRect(self.drag_handle_rect)

            # Resize handle (Bottom-Right)
            self.resize_handle_rect = QRect(self.width() - self.handle_size, self.height() - self.handle_size, self.handle_size, self.handle_size)
            painter.drawRect(self.resize_handle_rect)

    def mousePressEvent(self, event: QMouseEvent):
        if not self.is_in_design_mode:
            child_pos = self.widget.mapFrom(self, event.position().toPoint())
            child_event = QtGui.QMouseEvent(event.type(), child_pos, event.globalPosition(), event.button(), event.buttons(), event.modifiers())
            QApplication.sendEvent(self.widget, child_event)
            return

        if event.button() == Qt.LeftButton:
            if self.drag_handle_rect.contains(event.position().toPoint()):
                self.dragging = True
                self.drag_start_pos = event.globalPosition().toPoint()
                self.original_pos = self.pos()
                self.setCursor(Qt.SizeAllCursor)
                event.accept()
            elif self.resize_handle_rect.contains(event.position().toPoint()):
                self.resizing = True
                self.resize_start_pos = event.globalPosition().toPoint()
                self.original_size = self.size()
                self.setCursor(Qt.SizeFDiagCursor)
                event.accept()
            else:
                event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.is_in_design_mode:
             child_pos = self.widget.mapFrom(self, event.position().toPoint())
             child_event = QtGui.QMouseEvent(event.type(), child_pos, event.globalPosition(), event.button(), event.buttons(), event.modifiers())
             QApplication.sendEvent(self.widget, child_event)
             return

        if self.dragging and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self.drag_start_pos
            new_pos = self.original_pos + delta
            parent_rect = self.parentWidget().rect() if self.parentWidget() else QRect()
            if not parent_rect.isEmpty():
                 new_pos.setX(max(0, min(new_pos.x(), parent_rect.width() - self.width())))
                 new_pos.setY(max(0, min(new_pos.y(), parent_rect.height() - self.height())))
            self.move(new_pos)
            event.accept()

        elif self.resizing and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self.resize_start_pos
            new_width = max(self.minimumWidth(), self.original_size.width() + delta.x())
            new_height = max(self.minimumHeight(), self.original_size.height() + delta.y())
            parent_rect = self.parentWidget().rect() if self.parentWidget() else QRect()
            if not parent_rect.isEmpty():
                if self.x() + new_width > parent_rect.width():
                    new_width = parent_rect.width() - self.x()
                if self.y() + new_height > parent_rect.height():
                    new_height = parent_rect.height() - self.y()
            self.resize(new_width, new_height)
            event.accept()
        else:
             if self.is_in_design_mode:
                 pos = event.position().toPoint() # Convert QPointF to QPoint
                 if self.drag_handle_rect.contains(pos) or self.resize_handle_rect.contains(pos):
                     self.setCursor(Qt.SizeAllCursor if self.drag_handle_rect.contains(pos) else Qt.SizeFDiagCursor)
                 else:
                     self.unsetCursor()
             event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self.is_in_design_mode:
            child_pos = self.widget.mapFrom(self, event.position().toPoint())
            child_event = QtGui.QMouseEvent(event.type(), child_pos, event.globalPosition(), event.button(), event.buttons(), event.modifiers())
            QApplication.sendEvent(self.widget, child_event)
            return

        if event.button() == Qt.LeftButton:
            if self.dragging:
                self.dragging = False
                self.unsetCursor()
                event.accept()
            elif self.resizing:
                self.resizing = False
                self.unsetCursor()
                event.accept()
            else:
                event.ignore()
        else:
             event.ignore()
