"""
GenosLauncher — Splash screen shown during startup.

440×270 frameless, centered, white background.
Animated indeterminate progress bar at the bottom (accent blue, 3 px).
Public API: close_animated(callback) — fades opacity 1→0 over 250 ms.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QMovie,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles import C, FONT


def _asset(name: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", name)


class SplashScreen(QWidget):
    """440×270 frameless splash screen with indeterminate progress bar."""

    WIDTH = 440
    HEIGHT = 270

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.SplashScreen | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setStyleSheet(f"background-color: {C['bg_primary']}; border-radius: 0px;")

        self._build_ui()
        self._center_on_screen()

        # Drive the "fake" indeterminate progress with a QTimer
        self._prog_value: int = 0
        self._prog_timer = QTimer(self)
        self._prog_timer.setInterval(30)
        self._prog_timer.timeout.connect(self._tick_progress)
        self._prog_timer.start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Content area ─────────────────────────────────────────────────
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(40, 48, 40, 32)
        content_layout.setSpacing(0)
        content_layout.setAlignment(Qt.AlignCenter)

        # Animated logo — 80×80
        icon_row = QHBoxLayout()
        icon_row.setAlignment(Qt.AlignCenter)
        gif_path = _asset("animationlauncher.gif")
        if os.path.exists(gif_path):
            icon_label = QLabel()
            icon_label.setFixedSize(80, 80)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setStyleSheet("background: transparent;")
            self._gif_movie = QMovie(gif_path)
            self._gif_movie.setScaledSize(QSize(80, 80))
            icon_label.setMovie(self._gif_movie)
            self._gif_movie.start()
        else:
            icon_label = self._make_icon_box(80)
        icon_row.addWidget(icon_label)
        content_layout.addLayout(icon_row)
        content_layout.addSpacing(20)

        # App title
        title = QLabel("GenosLauncher")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {C['text_primary']};"
            "font-size: 26px;"
            "font-weight: 700;"
            "letter-spacing: -0.5px;"
            "background: transparent;"
        )
        content_layout.addWidget(title)
        content_layout.addSpacing(8)

        # Tagline
        tagline = QLabel("Open-source · Fast · Elegant")
        tagline.setAlignment(Qt.AlignCenter)
        tagline.setStyleSheet(
            f"color: {C['text_tertiary']};"
            f"font-size: {FONT['sm']};"
            "background: transparent;"
        )
        content_layout.addWidget(tagline)
        content_layout.addStretch()

        root.addWidget(content, stretch=1)

        # ── Progress bar — bottom edge, 3 px, accent blue ─────────────
        self._progress = QProgressBar()
        self._progress.setFixedHeight(3)
        self._progress.setTextVisible(False)
        self._progress.setMinimum(0)
        self._progress.setMaximum(100)
        self._progress.setValue(0)
        self._progress.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {C['border']};
                border: none;
                border-radius: 0px;
            }}
            QProgressBar::chunk {{
                background-color: {C['accent_blue']};
                border-radius: 0px;
            }}
            """
        )
        root.addWidget(self._progress)

    @staticmethod
    def _make_icon_box(size: int) -> QLabel:
        """Return a QLabel rendered as a dark rounded-square G icon."""
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(C["accent"]))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, size, size, 10, 10)
        painter.setPen(QColor(C["text_inverse"]))
        font = QFont("Segoe UI", max(1, int(size * 0.52)), QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pix.rect(), Qt.AlignCenter, "G")
        painter.end()

        label = QLabel()
        label.setPixmap(pix)
        label.setFixedSize(size, size)
        label.setStyleSheet("background: transparent;")
        return label

    # ------------------------------------------------------------------
    # Fake-indeterminate progress animation
    # ------------------------------------------------------------------

    def _tick_progress(self) -> None:
        self._prog_value = (self._prog_value + 2) % 101
        self._progress.setValue(self._prog_value)

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.WIDTH) // 2
            y = geo.y() + (geo.height() - self.HEIGHT) // 2
            self.move(x, y)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def close_animated(self, callback: Optional[Callable[[], None]] = None) -> None:
        """Fade from opacity 1 → 0 over 250 ms, then call callback and close."""
        self._prog_timer.stop()

        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setDuration(250)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _on_finished() -> None:
            self.close()
            if callback is not None:
                callback()

        anim.finished.connect(_on_finished)
        anim.start()
        # Keep a reference so the GC doesn't collect the animation mid-flight
        self._fade_anim = anim
