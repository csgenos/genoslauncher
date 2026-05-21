"""
Animated progress widgets for the launch sequence.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Property, QPropertyAnimation, Qt, QTimer, QEasingCurve
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..styles import COLORS as C, FONT


class GlowProgressBar(QWidget):
    """
    A custom progress bar with animated gradient fill and outer glow.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(10)
        self._value: float = 0.0       # 0.0 .. 1.0
        self._shimmer_phase: float = 0.0

        # Shimmer animation
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

        # Value animation
        self._anim = QPropertyAnimation(self, b"progress_val", self)
        self._anim.setDuration(400)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # ------------------------------------------------------------------
    # Property
    # ------------------------------------------------------------------

    def _get_val(self) -> float:
        return self._value

    def _set_val(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self.update()

    progress_val = Property(float, _get_val, _set_val)

    def set_progress(self, value: float) -> None:
        """Set progress (0.0 – 1.0) with animation."""
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(value)
        self._anim.start()

    def _tick(self) -> None:
        self._shimmer_phase = (self._shimmer_phase + 0.05) % (2 * math.pi)
        self.update()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = h / 2

        # Track
        track_path = QPainterPath()
        track_path.addRoundedRect(0, 0, w, h, r, r)
        painter.fillPath(track_path, QColor(C["bg_secondary"]))

        if self._value <= 0.0:
            painter.end()
            return

        # Fill
        fill_w = max(r * 2, int(w * self._value))
        fill_path = QPainterPath()
        fill_path.addRoundedRect(0, 0, fill_w, h, r, r)

        grad = QLinearGradient(0, 0, fill_w, 0)
        grad.setColorAt(0.0, QColor(C["accent_purple"]))
        grad.setColorAt(0.5, QColor(C["accent_blue"]))
        grad.setColorAt(1.0, QColor(C["accent_cyan"]))
        painter.fillPath(fill_path, grad)

        # Shimmer overlay
        shimmer_x = (math.sin(self._shimmer_phase) + 1) / 2 * fill_w
        shimmer_grad = QLinearGradient(shimmer_x - 40, 0, shimmer_x + 40, 0)
        shimmer_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        shimmer_grad.setColorAt(0.5, QColor(255, 255, 255, 60))
        shimmer_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(fill_path, shimmer_grad)

        # Tip glow
        tip_grad = QLinearGradient(fill_w - 20, 0, fill_w + 8, 0)
        tip_grad.setColorAt(0.0, QColor(0, 229, 255, 0))
        tip_grad.setColorAt(1.0, QColor(0, 229, 255, 180))
        painter.fillPath(track_path, tip_grad)

        painter.end()


class LaunchProgressPanel(QWidget):
    """
    Full launch status panel shown during launch sequence.
    Contains a GlowProgressBar, status label, and step indicator.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        # Status text
        self._status_label = QLabel("Preparing...", self)
        self._status_label.setStyleSheet(
            f"color: {C['text_secondary']}; font-size: {FONT['sm']};"
        )
        self._status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_label)

        # Progress bar
        self._bar = GlowProgressBar(self)
        layout.addWidget(self._bar)

        # Percentage
        self._pct_label = QLabel("0%", self)
        self._pct_label.setStyleSheet(
            f"color: {C['accent_cyan']}; font-size: {FONT['xs']}; font-weight: 700;"
        )
        self._pct_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self._pct_label)

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def set_progress(self, current: int, maximum: int) -> None:
        if maximum <= 0:
            return
        pct = current / maximum
        self._bar.set_progress(pct)
        self._pct_label.setText(f"{int(pct * 100)}%")

    def show_panel(self) -> None:
        self.setVisible(True)

    def hide_panel(self) -> None:
        self.setVisible(False)
        self._bar.set_progress(0.0)
        self._status_label.setText("Preparing...")
        self._pct_label.setText("0%")
