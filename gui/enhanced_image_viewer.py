"""Enhanced image viewer widget with stable zoom, pan, and overlay rendering."""

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QInputDialog, QLabel

logger = logging.getLogger(__name__)


class AnnotationTool(Enum):
    NONE = auto()
    ARROW = auto()
    RECTANGLE = auto()
    TEXT = auto()
    PAN = auto()


class Annotation:
    def __init__(self, start_point: QPointF, color: QColor, line_width: int = 2):
        self.start_point = start_point
        self.end_point = start_point
        self.color = color
        self.line_width = line_width
        self.is_complete = False

    def update_end_point(self, point: QPointF):
        self.end_point = point

    def draw(self, painter: QPainter):
        raise NotImplementedError


class ArrowAnnotation(Annotation):
    def draw(self, painter: QPainter):
        pen = QPen(self.color, self.line_width, Qt.SolidLine)
        painter.setPen(pen)
        painter.drawLine(self.start_point, self.end_point)
        if self.start_point == self.end_point:
            return
        import math
        angle = math.atan2(self.end_point.y() - self.start_point.y(), self.end_point.x() - self.start_point.x())
        arrow_size = 10 * (self.line_width / 2)
        arrow_p1 = QPointF(self.end_point.x() - arrow_size * math.cos(angle + 3.14159 / 6), self.end_point.y() - arrow_size * math.sin(angle + 3.14159 / 6))
        arrow_p2 = QPointF(self.end_point.x() - arrow_size * math.cos(angle - 3.14159 / 6), self.end_point.y() - arrow_size * math.sin(angle - 3.14159 / 6))
        painter.setBrush(QBrush(self.color))
        path = QPainterPath()
        path.moveTo(self.end_point)
        path.lineTo(arrow_p1)
        path.lineTo(arrow_p2)
        path.closeSubpath()
        painter.fillPath(path, QBrush(self.color))


class RectangleAnnotation(Annotation):
    def draw(self, painter: QPainter):
        pen = QPen(self.color, self.line_width, Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(self.start_point, self.end_point).normalized())


class TextAnnotation(Annotation):
    def __init__(self, start_point: QPointF, color: QColor, text: str = "", font_size: int = 12):
        super().__init__(start_point, color, line_width=1)
        self.text = text
        self.font_size = font_size
        self.end_point = start_point

    def draw(self, painter: QPainter):
        if not self.text:
            return
        font = QFont("Arial", self.font_size, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_rect = metrics.boundingRect(self.text)
        text_rect.moveTopLeft(self.start_point.toPoint())
        painter.fillRect(QRectF(text_rect.adjusted(-4, -4, 4, 4)), QColor(0, 0, 0, 180))
        painter.setPen(QPen(self.color))
        painter.drawText(QRectF(text_rect), Qt.AlignLeft | Qt.AlignTop, self.text)


@dataclass
class TranslationOverlayBlock:
    rect: QRectF
    text: str
    font_family: str
    font_size: int
    text_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 255))
    fill_color: QColor = field(default_factory=lambda: QColor(24, 28, 35, 225))
    border_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 40))
    accent_color: QColor = field(default_factory=lambda: QColor(120, 220, 255, 140))
    shadow_color: QColor = field(default_factory=lambda: QColor(0, 0, 0, 80))
    shadow_offset: QPointF = field(default_factory=lambda: QPointF(0.0, 4.0))
    corner_radius: float = 14.0
    text_padding_x: float = 14.0
    text_padding_y: float = 10.0

    def draw(self, painter: QPainter):
        if not self.text:
            return
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.shadow_color)
        painter.drawRoundedRect(self.rect.translated(self.shadow_offset), self.corner_radius, self.corner_radius)
        painter.setBrush(self.fill_color)
        painter.setPen(QPen(self.border_color, 1.0))
        painter.drawRoundedRect(self.rect, self.corner_radius, self.corner_radius)
        if self.accent_color.alpha() > 10:
            accent_rect = QRectF(self.rect.left() + 4, self.rect.top() + 4, 3, max(8.0, self.rect.height() - 8))
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.accent_color)
            painter.drawRoundedRect(accent_rect, 2, 2)
        font = QFont(self.font_family or "Arial", int(self.font_size))
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(self.text_color)
        painter.drawText(self.rect.adjusted(self.text_padding_x, self.text_padding_y, -self.text_padding_x, -self.text_padding_y), int(Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap), self.text)


class ZoomableImageLabel(QLabel):
    zoomChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._zoom_factor = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 10.0
        self._scene_margin = 120
        self._is_panning = False
        self._pan_start = QPoint()
        self._pan_offset = QPoint(0, 0)
        self._annotations: List[Annotation] = []
        self._translation_overlays: List[TranslationOverlayBlock] = []
        self._current_annotation: Optional[Annotation] = None
        self._annotation_tool = AnnotationTool.NONE
        self._annotation_color = QColor(255, 0, 0, 255)
        self._annotation_line_width = 2
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAlignment(Qt.AlignCenter)

    def set_pixmap(self, pixmap: QPixmap, preserve_view: bool = False):
        self._pixmap = pixmap
        if not preserve_view:
            self._zoom_factor = 1.0
            self._pan_offset = QPoint(0, 0)
        else:
            self._clamp_pan_offset()
        self.update()

    def get_pixmap(self) -> Optional[QPixmap]:
        return self._pixmap

    def set_scene_margin(self, margin: int):
        self._scene_margin = max(0, margin)
        self._clamp_pan_offset()
        self.update()

    def set_translation_overlays(self, overlays: List[TranslationOverlayBlock], scene_margin: Optional[int] = None):
        self._translation_overlays = list(overlays)
        if scene_margin is not None:
            self._scene_margin = max(0, scene_margin)
        self._clamp_pan_offset()
        self.update()

    def clear_translation_overlays(self):
        self._translation_overlays.clear()
        self.update()

    def set_annotation_tool(self, tool: AnnotationTool):
        self._annotation_tool = tool
        if tool == AnnotationTool.PAN:
            self.setCursor(Qt.OpenHandCursor)
        elif tool == AnnotationTool.NONE:
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    def set_annotation_color(self, color: QColor):
        self._annotation_color = color

    def set_annotation_line_width(self, width: int):
        self._annotation_line_width = width

    def get_annotations(self):
        return self._annotations.copy()

    def clear_annotations(self):
        self._annotations.clear()
        self._current_annotation = None
        self.update()

    def undo_last_annotation(self):
        if self._annotations:
            self._annotations.pop()
            self.update()

    def _set_zoom_factor(self, new_zoom: float, anchor_pos: Optional[QPoint] = None):
        if not self._pixmap:
            return
        bounded_zoom = max(self._min_zoom, min(new_zoom, self._max_zoom))
        if abs(bounded_zoom - self._zoom_factor) < 1e-6:
            return
        anchor_scene = self._widget_to_scene(anchor_pos) if anchor_pos is not None else None
        self._zoom_factor = bounded_zoom
        if anchor_pos is not None and anchor_scene is not None:
            self._pan_offset += anchor_pos - self._scene_to_widget(anchor_scene)
        self._clamp_pan_offset()
        self.update()
        self.zoomChanged.emit(self._zoom_factor)

    def zoom_in(self):
        self._set_zoom_factor(self._zoom_factor * 1.2)

    def zoom_out(self):
        self._set_zoom_factor(self._zoom_factor / 1.2)

    def zoom_fit(self):
        if not self._pixmap:
            return
        scene_width = self._pixmap.width() + (self._scene_margin * 2)
        scene_height = self._pixmap.height() + (self._scene_margin * 2)
        self._zoom_factor = min(self.width() / max(1, scene_width), self.height() / max(1, scene_height), 1.0)
        self._pan_offset = QPoint(0, 0)
        self.update()
        self.zoomChanged.emit(self._zoom_factor)

    def zoom_actual(self):
        self._zoom_factor = 1.0
        self._pan_offset = QPoint(0, 0)
        self.update()
        self.zoomChanged.emit(self._zoom_factor)

    def get_zoom_factor(self) -> float:
        return self._zoom_factor

    def _get_scene_size(self) -> QPointF:
        if not self._pixmap:
            return QPointF(0, 0)
        return QPointF(self._pixmap.width() + (self._scene_margin * 2), self._pixmap.height() + (self._scene_margin * 2))

    def _get_scene_origin(self) -> QPointF:
        scene_size = self._get_scene_size()
        return QPointF((self.width() - (scene_size.x() * self._zoom_factor)) / 2 + self._pan_offset.x(), (self.height() - (scene_size.y() * self._zoom_factor)) / 2 + self._pan_offset.y())

    def _clamp_pan_offset(self):
        if not self._pixmap:
            self._pan_offset = QPoint(0, 0)
            return
        scene_size = self._get_scene_size()
        overflow_x = max(0.0, ((scene_size.x() * self._zoom_factor) - self.width()) / 2.0)
        overflow_y = max(0.0, ((scene_size.y() * self._zoom_factor) - self.height()) / 2.0)
        slack = 60
        limit_x = int(overflow_x + slack)
        limit_y = int(overflow_y + slack)
        self._pan_offset = QPoint(max(-limit_x, min(limit_x, self._pan_offset.x())), max(-limit_y, min(limit_y, self._pan_offset.y())))

    def wheelEvent(self, event):
        if not self._pixmap:
            return
        anchor = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if event.angleDelta().y() > 0:
            self._set_zoom_factor(self._zoom_factor * 1.2, anchor)
        else:
            self._set_zoom_factor(self._zoom_factor / 1.2, anchor)
        event.accept()

    def mousePressEvent(self, event):
        if not self._pixmap:
            return
        if event.button() == Qt.LeftButton:
            if self._annotation_tool == AnnotationTool.PAN or event.modifiers() & Qt.ControlModifier:
                self._is_panning = True
                self._pan_start = event.pos()
                self.setCursor(Qt.ClosedHandCursor)
            elif self._annotation_tool != AnnotationTool.NONE:
                scene_pos = self._widget_to_scene(event.pos())
                if self._annotation_tool == AnnotationTool.ARROW:
                    self._current_annotation = ArrowAnnotation(scene_pos, self._annotation_color, self._annotation_line_width)
                elif self._annotation_tool == AnnotationTool.RECTANGLE:
                    self._current_annotation = RectangleAnnotation(scene_pos, self._annotation_color, self._annotation_line_width)
                elif self._annotation_tool == AnnotationTool.TEXT:
                    text, ok = QInputDialog.getText(self, "Add Text", "Enter annotation text:")
                    if ok and text:
                        self._current_annotation = TextAnnotation(scene_pos, self._annotation_color, text, font_size=max(8, int(12 / max(0.25, self._zoom_factor))))
                        self._current_annotation.is_complete = True
                        self._annotations.append(self._current_annotation)
                        self._current_annotation = None
                        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._pixmap:
            return
        if self._is_panning:
            self._pan_offset += event.pos() - self._pan_start
            self._pan_start = event.pos()
            self._clamp_pan_offset()
            self.update()
        elif self._current_annotation and not self._current_annotation.is_complete:
            self._current_annotation.update_end_point(self._widget_to_scene(event.pos()))
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._is_panning:
                self._is_panning = False
                if self._annotation_tool == AnnotationTool.PAN:
                    self.setCursor(Qt.OpenHandCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
            elif self._current_annotation:
                self._current_annotation.is_complete = True
                self._annotations.append(self._current_annotation)
                self._current_annotation = None
                self.update()
        event.accept()

    def _widget_to_scene(self, widget_pos: QPoint) -> QPointF:
        if not self._pixmap:
            return QPointF(widget_pos)
        scene_origin = self._get_scene_origin()
        return QPointF(((widget_pos.x() - scene_origin.x()) / self._zoom_factor) - self._scene_margin, ((widget_pos.y() - scene_origin.y()) / self._zoom_factor) - self._scene_margin)

    def _scene_to_widget(self, scene_pos: QPointF) -> QPoint:
        if not self._pixmap:
            return scene_pos.toPoint()
        scene_origin = self._get_scene_origin()
        return QPoint(int((scene_pos.x() + self._scene_margin) * self._zoom_factor + scene_origin.x()), int((scene_pos.y() + self._scene_margin) * self._zoom_factor + scene_origin.y()))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        gradient = QLinearGradient(0, 0, 0, max(1, self.height()))
        gradient.setColorAt(0.0, QColor(14, 18, 24))
        gradient.setColorAt(1.0, QColor(20, 26, 34))
        painter.fillRect(self.rect(), gradient)
        if not self._pixmap:
            super().paintEvent(event)
            return
        scene_origin = self._get_scene_origin()
        scene_size = self._get_scene_size()
        scene_rect = QRectF(scene_origin.x(), scene_origin.y(), scene_size.x() * self._zoom_factor, scene_size.y() * self._zoom_factor)
        image_rect = QRectF(scene_origin.x() + (self._scene_margin * self._zoom_factor), scene_origin.y() + (self._scene_margin * self._zoom_factor), self._pixmap.width() * self._zoom_factor, self._pixmap.height() * self._zoom_factor)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 36))
        painter.drawRoundedRect(scene_rect.adjusted(0, 8, 0, 8), 18, 18)
        painter.setBrush(QColor(23, 28, 36, 180))
        painter.setPen(QPen(QColor(255, 255, 255, 24), 1.0))
        painter.drawRoundedRect(scene_rect, 18, 18)
        painter.setBrush(QColor(0, 0, 0, 52))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(image_rect.adjusted(0, 6, 0, 6), 14, 14)
        image_path = QPainterPath()
        image_path.addRoundedRect(image_rect, 14, 14)
        painter.save()
        painter.setClipPath(image_path)
        painter.drawPixmap(image_rect, self._pixmap, QRectF(self._pixmap.rect()))
        painter.restore()
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(image_rect, 14, 14)
        painter.save()
        painter.translate(scene_origin)
        painter.scale(self._zoom_factor, self._zoom_factor)
        painter.translate(self._scene_margin, self._scene_margin)
        for overlay in self._translation_overlays:
            overlay.draw(painter)
        for annotation in self._annotations:
            annotation.draw(painter)
        if self._current_annotation:
            self._current_annotation.draw(painter)
        painter.restore()

    def get_rendered_pixmap(self, include_scene_margin: bool = False) -> QPixmap:
        if not self._pixmap:
            return QPixmap()
        margin = self._scene_margin if include_scene_margin else 0
        result = QPixmap(self._pixmap.width() + (margin * 2), self._pixmap.height() + (margin * 2))
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(margin, margin, self._pixmap)
        painter.save()
        painter.translate(margin, margin)
        for overlay in self._translation_overlays:
            overlay.draw(painter)
        for annotation in self._annotations:
            annotation.draw(painter)
        painter.restore()
        painter.end()
        return result
