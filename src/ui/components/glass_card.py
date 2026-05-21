"""
GlassCard — a glassmorphic container widget.

Renders a rounded, semi-transparent card with a subtle border
and optional animated glow on hover.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QVBoxLayout, QWidget

from ..styles import COLORS as C


class GlassCard(QWidget):
    """
    A premium glassmorphic card widget.

    Usage:
        card = GlassCard(hover_glow=True)
        card.layout().addWidget(my_label)
    """

    def __init__(
        self,
        bg: str = C["bg_card"],
        border: str = C["border"],
        radius: int = 14,
        hover_glow: bool = False,
        glow_color: str = C["accent_blue"],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._bg = QColor(bg)
        self._border = QColor(border)
        self._radius = radius
        self._hover_glow = hover_glow
        self._glow_color = QColor(glow_color)
        self._hover_progress: float = 0.0

        # Layout (pass-through so children can be added directly)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        if hover_glow:
            self._shadow = QGraphicsDropShadowEffect(self)
            self._shadow.setBlurRadius(0)
            self._shadow.setOffset(0, 0)
            self._shadow.setColor(self._glow_color)
            self.setGraphicsEffect(self._shadow)

            self._anim = QPropertyAnimation(self, b"hover_prog", self)
            self._anim.setDuration(250)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def layout(self) -> QVBoxLayout:
        return self._layout

    # ------------------------------------------------------------------
    # Property
    # ------------------------------------------------------------------

    def _get_hover_prog(self) -> float:
        return self._hover_progress

    def _set_hover_prog(self, val: float) -> None:
        self._hover_progress = val
        if self._hover_glow:
            blur = int(val * 28)
            self._shadow.setBlurRadius(blur)
            self._shadow.setColor(QColor(
                self._glow_color.red(),
                self._glow_color.green(),
                self._glow_color.blue(),
                int(val * 160),
            ))
        self.update()

    hover_prog = Property(float, _get_hover_prog, _set_hover_prog)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def enterEvent(self, event) -> None:
        if self._hover_glow:
            self._anim.stop()
            self._anim.setStartValue(self._hover_progress)
            self._anim.setEndValue(1.0)
            self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover_glow:
            self._anim.stop()
            self._anim.setStartValue(self._hover_progress)
            self._anim.setEndValue(0.0)
            self._anim.start()
        super().leaveEvent(event)

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = self._radius

        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)

        # Background with hover brightening
        t = self._hover_progress
        bg = QColor(
            min(255, int(self._bg.red() + t * 12)),
            min(255, int(self._bg.green() + t * 12)),
            min(255, int(self._bg.blue() + t * 18)),
        )
        painter.fillPath(path, bg)

        # Top gloss line
        gloss = QLinearGradient(0, 0, 0, r * 2)
        gloss.setColorAt(0.0, QColor(255, 255, 255, 18))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(path, gloss)

        # Border
        border_alpha = int(self._border.alpha() if self._border.alpha() < 255 else 255)
        if t > 0:
            border_alpha = min(255, int(border_alpha + t * 80))
        border_color = QColor(
            self._border.red(), self._border.green(), self._border.blue(), border_alpha
        )
        # Accent bleed on hover
        if t > 0.01:
            gc = self._glow_color if self._hover_glow else QColor(C["accent_blue"])
            final_r = int(border_color.red() + (gc.red() - border_color.red()) * t * 0.5)
            final_g = int(border_color.green() + (gc.green() - border_color.green()) * t * 0.5)
            final_b = int(border_color.blue() + (gc.blue() - border_color.blue()) * t * 0.5)
            border_color = QColor(final_r, final_g, final_b, border_alpha)

        painter.setPen(border_color)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(0, 0, w - 1, h - 1, r, r)

        painter.end()
