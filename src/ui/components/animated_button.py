"""
Premium animated buttons for GenosLauncher.

AnimatedButton  — base with hover scale + glow
LaunchButton    — big gradient CTA with pulse animation
GhostButton     — outline-only, fills on hover
"""

from __future__ import annotations

import math

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QRadialGradient,
)
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QPushButton, QSizePolicy

from ..styles import COLORS as C, FONT


# ---------------------------------------------------------------------------
# Animated Button (base)
# ---------------------------------------------------------------------------

class AnimatedButton(QPushButton):
    """
    Button with smooth hover glow and subtle scale animation.
    Override gradient colors via constructor arguments.
    """

    def __init__(
        self,
        text: str = "",
        color_start: str = C["bg_card"],
        color_end: str = C["bg_card_hover"],
        accent: str = C["accent_cyan"],
        text_color: str = C["text_primary"],
        parent=None,
    ) -> None:
        super().__init__(text, parent)
        self._color_start = QColor(color_start)
        self._color_end = QColor(color_end)
        self._accent = QColor(accent)
        self._text_color = QColor(text_color)

        self._hover_progress: float = 0.0
        self._press_progress: float = 0.0

        self.setMinimumHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(0, 0)
        self._shadow.setColor(QColor(self._accent))
        self.setGraphicsEffect(self._shadow)

        # Hover animation
        self._hover_anim = QPropertyAnimation(self, b"hover_progress", self)
        self._hover_anim.setDuration(200)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

    # ------------------------------------------------------------------
    # Qt property for animation
    # ------------------------------------------------------------------

    def _get_hover(self) -> float:
        return self._hover_progress

    def _set_hover(self, val: float) -> None:
        self._hover_progress = val
        blur = int(val * 20)
        self._shadow.setBlurRadius(blur)
        self._shadow.setColor(QColor(
            self._accent.red(),
            self._accent.green(),
            self._accent.blue(),
            int(val * 180),
        ))
        self.update()

    hover_progress = Property(float, _get_hover, _set_hover)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def enterEvent(self, event) -> None:
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self._press_progress = 1.0
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press_progress = 0.0
        self.update()
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = min(h // 2, 10)

        # Lerp background color
        t = self._hover_progress
        bg_r = int(self._color_start.red() + (self._color_end.red() - self._color_start.red()) * t)
        bg_g = int(self._color_start.green() + (self._color_end.green() - self._color_start.green()) * t)
        bg_b = int(self._color_start.blue() + (self._color_end.blue() - self._color_start.blue()) * t)
        bg = QColor(bg_r, bg_g, bg_b)

        # Press darken
        if self._press_progress > 0:
            factor = 1.0 - self._press_progress * 0.15
            bg = QColor(int(bg.red() * factor), int(bg.green() * factor), int(bg.blue() * factor))

        # Draw rounded rect background
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)
        painter.setClipPath(path)
        painter.fillPath(path, bg)

        # Accent border
        border_alpha = int(80 + self._hover_progress * 120)
        border_color = QColor(
            self._accent.red(), self._accent.green(), self._accent.blue(), border_alpha
        )
        painter.setPen(border_color)
        painter.drawRoundedRect(0, 0, w - 1, h - 1, r, r)

        # Text
        painter.setPen(self._text_color)
        font = QFont("Segoe UI", 10, QFont.Weight.SemiBold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())

        painter.end()


# ---------------------------------------------------------------------------
# Launch Button
# ---------------------------------------------------------------------------

class LaunchButton(QPushButton):
    """
    Large, animated LAUNCH button with:
    - Gradient background (purple → cyan)
    - Pulsing glow shadow when idle
    - Scale + brightness on hover
    - Press depression effect
    """

    def __init__(self, text: str = "LAUNCH", parent=None) -> None:
        super().__init__(text, parent)
        self.setFixedHeight(64)
        self.setMinimumWidth(220)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

        self._hover_progress: float = 0.0
        self._press_progress: float = 0.0
        self._pulse_phase: float = 0.0
        self._is_launching: bool = False

        # Drop shadow
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 4)
        self._shadow.setBlurRadius(30)
        self._shadow.setColor(QColor(C["accent_cyan"] + "aa"))
        self.setGraphicsEffect(self._shadow)

        # Hover animation
        self._hover_anim = QPropertyAnimation(self, b"hover_prog", self)
        self._hover_anim.setDuration(220)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Pulse timer (idle glow)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)
        self._pulse_timer.start(30)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def _get_hover_prog(self) -> float:
        return self._hover_progress

    def _set_hover_prog(self, val: float) -> None:
        self._hover_progress = val
        self.update()

    hover_prog = Property(float, _get_hover_prog, _set_hover_prog)

    def _tick_pulse(self) -> None:
        self._pulse_phase = (self._pulse_phase + 0.04) % (2 * math.pi)
        self._update_shadow()
        if not self._is_launching:
            self.update()

    def _update_shadow(self) -> None:
        pulse = (math.sin(self._pulse_phase) + 1) / 2  # 0..1
        base_blur = 20 + self._hover_progress * 20
        pulse_blur = base_blur + pulse * 15
        alpha = int(120 + self._hover_progress * 80 + pulse * 40)
        self._shadow.setBlurRadius(pulse_blur)
        self._shadow.setColor(QColor(0, 229, 255, alpha))

    def set_launching(self, launching: bool) -> None:
        self._is_launching = launching
        self.setEnabled(not launching)
        self.update()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def enterEvent(self, event) -> None:
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self._press_progress = 1.0
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press_progress = 0.0
        self.update()
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = h // 2  # fully rounded (pill shape)

        # Scale effect on hover
        scale = 1.0 + self._hover_progress * 0.015 - self._press_progress * 0.02
        painter.translate(w / 2, h / 2)
        painter.scale(scale, scale)
        painter.translate(-w / 2, -h / 2)

        # Gradient background
        t = self._hover_progress
        pulse = (math.sin(self._pulse_phase) + 1) / 2
        brightness = 1.0 + t * 0.12 + pulse * 0.04

        c1 = QColor(C["accent_purple"])
        c2 = QColor(C["accent_cyan"])

        def brighten(color: QColor, factor: float) -> QColor:
            return QColor(
                min(255, int(color.red() * factor)),
                min(255, int(color.green() * factor)),
                min(255, int(color.blue() * factor)),
            )

        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, brighten(c1, brightness))
        grad.setColorAt(0.5, brighten(QColor(C["accent_blue"]), brightness * 0.95))
        grad.setColorAt(1.0, brighten(c2, brightness))

        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)
        painter.fillPath(path, grad)

        # Inner highlight (top gloss)
        gloss = QLinearGradient(0, 0, 0, h * 0.5)
        gloss.setColorAt(0.0, QColor(255, 255, 255, 40))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        gloss_path = QPainterPath()
        gloss_path.addRoundedRect(1, 1, w - 2, h * 0.5, r, r)
        painter.fillPath(gloss_path, gloss)

        # Press overlay
        if self._press_progress > 0:
            painter.fillPath(path, QColor(0, 0, 0, int(40 * self._press_progress)))

        # Text
        text_color = QColor(C["bg_deep"]) if not self._is_launching else QColor(C["text_primary"])
        painter.setPen(text_color)
        font = QFont("Segoe UI", 14, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
        painter.setFont(font)
        label = "LAUNCHING..." if self._is_launching else self.text()
        painter.drawText(self.rect(), Qt.AlignCenter, label)

        painter.end()


# ---------------------------------------------------------------------------
# Ghost Button (outline style)
# ---------------------------------------------------------------------------

class GhostButton(QPushButton):
    """Outline button that fills with accent color on hover."""

    def __init__(
        self,
        text: str = "",
        accent: str = C["accent_cyan"],
        parent=None,
    ) -> None:
        super().__init__(text, parent)
        self._accent = QColor(accent)
        self._hover_progress: float = 0.0

        self.setMinimumHeight(38)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

        self._anim = QPropertyAnimation(self, b"ghost_hover", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def _get_ghost_hover(self) -> float:
        return self._hover_progress

    def _set_ghost_hover(self, val: float) -> None:
        self._hover_progress = val
        self.update()

    ghost_hover = Property(float, _get_ghost_hover, _set_ghost_hover)

    def enterEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover_progress)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover_progress)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = 8

        t = self._hover_progress

        # Fill
        fill_alpha = int(t * 35)
        painter.setBrush(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), fill_alpha))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, w, h, r, r)

        # Border
        border_alpha = int(120 + t * 135)
        painter.setPen(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), border_alpha))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(0, 0, w - 1, h - 1, r, r)

        # Text
        text_alpha = int(180 + t * 75)
        painter.setPen(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), text_alpha))
        font = QFont("Segoe UI", 10, QFont.Weight.SemiBold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())

        painter.end()
