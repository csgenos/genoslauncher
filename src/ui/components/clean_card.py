"""
CleanCard — a minimal white card widget for GenosLauncher (light theme).

Replaces GlassCard. Uses a subtle drop shadow that deepens on hover.
No color changes, no glow — just a clean white surface that lifts slightly.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QVBoxLayout, QWidget

from ..styles import COLORS as C


class CleanCard(QWidget):
    """
    White card with 1px #E5E7EB border and 12px border-radius.

    Shadow at rest: blur=12, offset=(0,2), alpha=18.
    Shadow on hover (when hover_lift=True): blur=20, offset=(0,4), alpha=30.
    Animated with a 200ms QPropertyAnimation.

    Usage:
        card = CleanCard(hover_lift=True)
        card.layout().addWidget(my_label)
    """

    def __init__(
        self,
        radius: int = 12,
        bg: str = C['bg_card'],
        border: str = C['border'],
        hover_lift: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._radius = radius
        self._bg = QColor(bg)
        self._border = QColor(border)
        self._hover_lift = hover_lift
        self._hover_progress: float = 0.0

        # Inner layout that callers use to add children
        self._inner = QVBoxLayout(self)
        self._inner.setContentsMargins(0, 0, 0, 0)
        self._inner.setSpacing(0)

        # Drop shadow effect
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(12)
        self._shadow.setOffset(0, 2)
        self._shadow.setColor(QColor(0, 0, 0, 18))
        self.setGraphicsEffect(self._shadow)

        if hover_lift:
            self._anim = QPropertyAnimation(self, b"hover_progress", self)
            self._anim.setDuration(200)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # Override layout() so users can do card.layout().addWidget(...)
    def layout(self) -> QVBoxLayout:
        return self._inner

    # --- Qt property -------------------------------------------------------

    def _get_hover(self) -> float:
        return self._hover_progress

    def _set_hover(self, val: float) -> None:
        self._hover_progress = val
        # Animate shadow depth
        blur   = int(12 + val * 8)     # 12 → 20
        offset = int(2  + val * 2)     # 2  → 4
        alpha  = int(18 + val * 12)    # 18 → 30
        self._shadow.setBlurRadius(blur)
        self._shadow.setOffset(0, offset)
        self._shadow.setColor(QColor(0, 0, 0, alpha))
        self.update()

    hover_progress = Property(float, _get_hover, _set_hover)

    # --- Events ------------------------------------------------------------

    def enterEvent(self, event) -> None:
        if self._hover_lift:
            self._anim.stop()
            self._anim.setStartValue(self._hover_progress)
            self._anim.setEndValue(1.0)
            self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover_lift:
            self._anim.stop()
            self._anim.setStartValue(self._hover_progress)
            self._anim.setEndValue(0.0)
            self._anim.start()
        super().leaveEvent(event)

    # --- Paint -------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = float(self._radius)

        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)

        # White fill
        painter.fillPath(path, self._bg)

        # 1px border
        painter.setPen(self._border)
        painter.setBrush(__import__('PySide6.QtCore', fromlist=['Qt']).Qt.NoBrush)
        painter.drawRoundedRect(0.5, 0.5, w - 1, h - 1, r, r)

        painter.end()
