"""
Clean animated buttons for GenosLauncher — light / white theme.

CleanButton   — base rounded button, hover scale + darker bg
PrimaryButton — dark navy CTA, white text
LaunchButton  — big 56px play button, authoritative and clean
OutlineButton — ghost / transparent with 1px border
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QPushButton, QSizePolicy

from ..styles import COLORS as C, FONT


# ---------------------------------------------------------------------------
# CleanButton — base
# ---------------------------------------------------------------------------

class CleanButton(QPushButton):
    """
    Base button with subtle hover scale (1.01x) and bg darkening.
    150ms QPropertyAnimation on hover_progress (0.0 to 1.0).
    No glow, no shadow, no gradient.
    """

    _BG_NORMAL  = C['bg_secondary']
    _BG_HOVER   = C['bg_hover']
    _BG_PRESS   = C['bg_pressed']
    _TEXT_COLOR = C['text_primary']
    _BORDER     = C['border']

    def __init__(self, text: str = "", icon_char: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._icon_char = icon_char
        self._hover_progress: float = 0.0
        self._pressed: bool = False

        self.setMinimumHeight(36)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._hover_anim = QPropertyAnimation(self, b"hover_progress", self)
        self._hover_anim.setDuration(150)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

    # --- Qt property -------------------------------------------------------

    def _get_hover(self) -> float:
        return self._hover_progress

    def _set_hover(self, val: float) -> None:
        self._hover_progress = val
        self.update()

    hover_progress = Property(float, _get_hover, _set_hover)

    # --- Events ------------------------------------------------------------

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
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    # --- Paint helpers -----------------------------------------------------

    def _lerp_color(self, c1: QColor, c2: QColor, t: float) -> QColor:
        return QColor(
            int(c1.red()   + (c2.red()   - c1.red())   * t),
            int(c1.green() + (c2.green() - c1.green()) * t),
            int(c1.blue()  + (c2.blue()  - c1.blue())  * t),
        )

    def _resolve_bg(self) -> QColor:
        if self._pressed:
            return QColor(self._BG_PRESS)
        return self._lerp_color(
            QColor(self._BG_NORMAL), QColor(self._BG_HOVER), self._hover_progress
        )

    def _resolve_scale(self) -> float:
        if self._pressed:
            return 0.99
        return 1.0 + self._hover_progress * 0.01

    # --- Paint -------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        scale = self._resolve_scale()

        painter.translate(w / 2, h / 2)
        painter.scale(scale, scale)
        painter.translate(-w / 2, -h / 2)

        r = 8.0
        bg = self._resolve_bg()
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)

        painter.fillPath(path, bg)

        # Border
        border_col = QColor(self._BORDER)
        painter.setPen(border_col)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(0.5, 0.5, w - 1, h - 1, r, r)

        # Text (with optional icon prefix)
        painter.setPen(QColor(self._TEXT_COLOR))
        font = QFont("Segoe UI", 10, QFont.Weight.Medium)
        painter.setFont(font)
        label = f"{self._icon_char} {self.text()}" if self._icon_char else self.text()
        painter.drawText(0, 0, w, h, Qt.AlignCenter, label)

        painter.end()


# ---------------------------------------------------------------------------
# PrimaryButton — dark navy CTA
# ---------------------------------------------------------------------------

class PrimaryButton(CleanButton):
    """
    Dark navy (#111827) button with white text.
    Hover lightens to #1F2937, press deepens to #0F172A.
    """

    _BG_NORMAL  = '#111827'
    _BG_HOVER   = '#1F2937'
    _BG_PRESS   = '#0F172A'
    _TEXT_COLOR = '#FFFFFF'
    _BORDER     = '#111827'

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        scale = self._resolve_scale()

        painter.translate(w / 2, h / 2)
        painter.scale(scale, scale)
        painter.translate(-w / 2, -h / 2)

        r = 8.0
        bg = self._resolve_bg()
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)
        painter.fillPath(path, bg)

        painter.setPen(QColor(self._TEXT_COLOR))
        font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        painter.setFont(font)
        label = f"{self._icon_char} {self.text()}" if self._icon_char else self.text()
        painter.drawText(0, 0, w, h, Qt.AlignCenter, label)

        painter.end()


# ---------------------------------------------------------------------------
# LaunchButton — big 56px play button
# ---------------------------------------------------------------------------

class LaunchButton(QPushButton):
    """
    The main launch CTA button. 56px tall, 200px min-width.
    Clean dark navy fill, white text. No glow, no pulse.
    Shows 'LAUNCHING...' text when in launching state.
    """

    def __init__(self, text: str = "PLAY", parent=None) -> None:
        super().__init__(text, parent)
        self._launch_text = text
        self._is_launching: bool = False
        self._hover_progress: float = 0.0
        self._pressed: bool = False

        self.setFixedHeight(56)
        self.setMinimumWidth(200)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._hover_anim = QPropertyAnimation(self, b"hover_progress", self)
        self._hover_anim.setDuration(150)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _get_hover(self) -> float:
        return self._hover_progress

    def _set_hover(self, val: float) -> None:
        self._hover_progress = val
        self.update()

    hover_progress = Property(float, _get_hover, _set_hover)

    def set_launching(self, launching: bool) -> None:
        """Toggle the launching state (disables button, changes label)."""
        self._is_launching = launching
        self.setEnabled(not launching)
        self.update()

    def enterEvent(self, event) -> None:
        if not self._is_launching:
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
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        t = self._hover_progress

        # Scale
        if self._pressed:
            scale = 0.98
        else:
            scale = 1.0 + t * 0.015
        painter.translate(w / 2, h / 2)
        painter.scale(scale, scale)
        painter.translate(-w / 2, -h / 2)

        # Background color
        if self._is_launching or not self.isEnabled():
            bg = QColor(C['text_disabled'])
        elif self._pressed:
            bg = QColor('#0F172A')
        else:
            # lerp between #111827 and #1F2937
            c1 = QColor('#111827')
            c2 = QColor('#1F2937')
            bg = QColor(
                int(c1.red()   + (c2.red()   - c1.red())   * t),
                int(c1.green() + (c2.green() - c1.green()) * t),
                int(c1.blue()  + (c2.blue()  - c1.blue())  * t),
            )

        r = 10.0
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)
        painter.fillPath(path, bg)

        # Subtle inset shadow at bottom edge
        if not self._is_launching:
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect(2, h - 4, w - 4, 4, r, r)
            painter.fillPath(shadow_path, QColor(0, 0, 0, 25))

        # Label
        painter.setPen(QColor(C['text_inverse']))
        font = QFont("Segoe UI", 12, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        painter.setFont(font)
        label = "LAUNCHING..." if self._is_launching else self._launch_text
        painter.drawText(0, 0, w, h, Qt.AlignCenter, label)

        painter.end()


# ---------------------------------------------------------------------------
# OutlineButton — ghost / transparent
# ---------------------------------------------------------------------------

class OutlineButton(CleanButton):
    """
    Transparent background with 1px border. On hover the bg fills
    lightly to #F4F6F8 and the border darkens. 150ms animation.
    """

    _BG_NORMAL  = 'transparent'
    _BG_HOVER   = C['bg_hover']
    _BG_PRESS   = C['bg_pressed']
    _TEXT_COLOR = C['text_primary']
    _BORDER     = C['border_strong']

    def _resolve_bg(self) -> QColor:
        if self._pressed:
            return QColor(self._BG_PRESS)
        if self._hover_progress < 0.001:
            return QColor(Qt.transparent)
        return self._lerp_color(
            QColor(0, 0, 0, 0), QColor(self._BG_HOVER), self._hover_progress
        )

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        scale = self._resolve_scale()

        painter.translate(w / 2, h / 2)
        painter.scale(scale, scale)
        painter.translate(-w / 2, -h / 2)

        r = 8.0
        t = self._hover_progress
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)

        bg = self._resolve_bg()
        painter.fillPath(path, bg)

        # Border darkens slightly on hover
        border_c1 = QColor(C['border_strong'])
        border_c2 = QColor(C['text_tertiary'])
        border_col = QColor(
            int(border_c1.red()   + (border_c2.red()   - border_c1.red())   * t),
            int(border_c1.green() + (border_c2.green() - border_c1.green()) * t),
            int(border_c1.blue()  + (border_c2.blue()  - border_c1.blue())  * t),
        )
        painter.setPen(border_col)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(0.5, 0.5, w - 1, h - 1, r, r)

        painter.setPen(QColor(self._TEXT_COLOR))
        font = QFont("Segoe UI", 10, QFont.Weight.Medium)
        painter.setFont(font)
        label = f"{self._icon_char} {self.text()}" if self._icon_char else self.text()
        painter.drawText(0, 0, w, h, Qt.AlignCenter, label)

        painter.end()
