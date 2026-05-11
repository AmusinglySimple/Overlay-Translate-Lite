# gui/custom_widgets.py — Lite version
import logging
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QFrame, QToolButton, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QLinearGradient, QIcon
from PySide6.QtSvg import QSvgRenderer
from utils.helpers import resource_path

logger = logging.getLogger("OverlayTranslateLite")


class ColorBarPicker(QWidget):
    colorChanged = Signal(QColor)

    def __init__(self, initial_color=QColor(0, 0, 255, 255), parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 80)
        h, s, v, a = initial_color.getHsvF()
        self.hue = h if h != -1 else 0.0
        self.saturation = s
        self.value = v
        self.alpha = initial_color.alpha()
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
            gradient.setColorAt(i / steps, QColor.fromHsvF(i / steps, 1.0, 1.0, 1.0))
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
        sat_start_color = QColor.fromHsvF(self.hue, 0.0, self.value, 1.0)
        sat_end_color = QColor.fromHsvF(self.hue, 1.0, self.value, 1.0)
        slider_style = """
            QSlider::groove:horizontal { height: 8px; background: #555; border-radius: 4px; }
            QSlider::handle:horizontal { background: white; border: 1px solid #aaa; width: 14px; height: 14px; border-radius: 7px; margin: -3px 0; }
            QSlider::sub-page:horizontal { border-radius: 4px; }
        """
        sat_style = slider_style + f"QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {sat_start_color.name()}, stop:1 {sat_end_color.name()}); }}"
        self.saturation_slider.setStyleSheet(sat_style)
        val_start_color = QColor.fromHsvF(self.hue, self.saturation, 0.0, 1.0)
        val_end_color = QColor.fromHsvF(self.hue, self.saturation, 1.0, 1.0)
        val_style = slider_style + f"QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {val_start_color.name()}, stop:1 {val_end_color.name()}); }}"
        self.value_slider.setStyleSheet(val_style)

    def hueBarMousePress(self, event):
        if event.button() == Qt.LeftButton:
            self.updateHueFromMouse(event.position())

    def hueBarMouseMove(self, event):
        if event.buttons() & Qt.LeftButton:
            self.updateHueFromMouse(event.position())

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
        new_color = QColor.fromHsvF(self.hue, self.saturation, self.value, self.alpha / 255.0)
        self.colorChanged.emit(new_color)

    def getColor(self):
        return QColor.fromHsvF(self.hue, self.saturation, self.value, self.alpha / 255.0)

    def setColor(self, color):
        self.updateColorFromQColor(color)


class CollapsibleBox(QWidget):
    toggled = Signal(bool)

    def __init__(self, title="", parent=None, expanded=True):
        super().__init__(parent)
        self._is_expanded = expanded
        self.animation_duration = 200

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.toggle_button = QToolButton(self)
        self.toggle_button.setObjectName("CollapsibleHeader")
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(expanded)
        self.toggle_button.clicked.connect(self.toggle)

        arrow_icon_path = resource_path(os.path.join("assets", "icons", "arrow_down.svg"))
        if os.path.exists(arrow_icon_path):
            self.toggle_button.setIcon(QIcon(arrow_icon_path))
        else:
            self.toggle_button.setText(("▼ " if expanded else "▶ ") + title)

        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toggle_button.setStyleSheet("""
            QToolButton#CollapsibleHeader {
                font-weight: bold; font-size: 13px;
                border: none; padding: 8px 12px;
                text-align: left; border-radius: 6px;
            }
            QToolButton#CollapsibleHeader:hover { background: rgba(255,255,255,0.05); }
        """)

        self.header_frame = QFrame(self)
        self.header_frame.setFrameShape(QFrame.NoFrame)
        header_layout = QVBoxLayout(self.header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(self.toggle_button)

        self.content_widget = QWidget(self)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(10, 5, 10, 10)
        self.content_layout.setSpacing(8)

        self.animation = QPropertyAnimation(self.content_widget, b"maximumHeight", self)
        self.animation.setDuration(self.animation_duration)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)

        self.main_layout.addWidget(self.header_frame)
        self.main_layout.addWidget(self.content_widget)

        if not expanded:
            self.content_widget.setMaximumHeight(0)
        else:
            self.content_widget.setMaximumHeight(16777215)

    def toggle(self):
        self._is_expanded = not self._is_expanded
        self.toggle_button.setChecked(self._is_expanded)

        if self._is_expanded:
            self.animation.setStartValue(0)
            self.content_widget.setMaximumHeight(16777215)
            content_height = self.content_widget.sizeHint().height()
            self.animation.setEndValue(content_height)
            self.animation.start()
            current_text = self.toggle_button.text()
            if current_text.startswith("▶ "):
                self.toggle_button.setText("▼ " + current_text[2:])
        else:
            content_height = self.content_widget.sizeHint().height()
            self.animation.setStartValue(content_height)
            self.animation.setEndValue(0)
            self.animation.start()
            current_text = self.toggle_button.text()
            if current_text.startswith("▼ "):
                self.toggle_button.setText("▶ " + current_text[2:])

        self.toggled.emit(self._is_expanded)

    def set_expanded(self, expanded: bool, animate=False):
        if self._is_expanded == expanded:
            return
        if animate:
            self.toggle()
        else:
            self._is_expanded = expanded
            self.toggle_button.setChecked(expanded)
            if expanded:
                self.content_widget.setMaximumHeight(16777215)
            else:
                self.content_widget.setMaximumHeight(0)
            self.toggled.emit(self._is_expanded)

    def is_expanded(self) -> bool:
        return self._is_expanded

    def set_title(self, title: str):
        current_text = self.toggle_button.text()
        if current_text.startswith("▼ ") or current_text.startswith("▶ "):
            prefix = current_text[:2]
            self.toggle_button.setText(prefix + title)
        else:
            self.toggle_button.setText(title)


class SectionSeparator(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)
        self.setStyleSheet("margin: 3px 0;")
        self.setFixedHeight(2)


class SvgSpinner(QWidget):
    def __init__(self, svg_path=None, size=32, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.setInterval(30)

        if not svg_path:
            self._svg_data = b'''
            <svg viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg">
                <circle cx="25" cy="25" r="20" fill="none" stroke="#6366f1" stroke-width="5" stroke-linecap="round" stroke-dasharray="31.4 150">
                    <animateTransform attributeName="transform" type="rotate" repeatCount="indefinite" dur="1s" values="0 25 25;360 25 25"/>
                </circle>
                <circle cx="25" cy="25" r="20" fill="none" stroke="#a855f7" stroke-width="5" stroke-linecap="round" stroke-dasharray="90 150" stroke-dashoffset="-40">
                    <animateTransform attributeName="transform" type="rotate" repeatCount="indefinite" dur="1.5s" values="0 25 25;360 25 25"/>
                </circle>
            </svg>
            '''
            self._renderer = QSvgRenderer(self._svg_data)
        else:
            self._renderer = QSvgRenderer(svg_path)

    def start(self):
        self.show()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _rotate(self):
        self._angle = (self._angle + 5) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)
        painter.translate(-self.width() / 2, -self.height() / 2)
        self._renderer.render(painter, self.rect())
