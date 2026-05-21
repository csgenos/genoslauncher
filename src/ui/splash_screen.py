"""
GenosLauncher — Splash screen shown on startup.

Clean 440×270 frameless window with an animated indeterminate progress bar
and a smooth fade-out via close_animated().
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QFont,
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

        # Indeterminate progress animation — advance the "fake" value in a loop
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

        # ── Main content area ─────────────────────────────────────────
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(40, 48, 40, 32)
        content_layout.setSpacing(0)
        content_layout.setAlignment(Qt.AlignCenter)

        # G icon box
        icon_box = self._make_icon_box(44)
        icon_row = QHBoxLayout()
        icon_row.setAlignment(Qt.AlignCenter)
        icon_row.addWidget(icon_box)
        content_layout.addLayout(icon_row)

        content_layout.addSpacing(20)

        # App name
        title = QLabel("GenosLauncher")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {C['text_primary']}; "
            f"font-size: 26px; "
            f"font-weight: 700; "
            f"letter-spacing: -0.5px; "
            f"background: transparent;"
        )
        content_layout.addWidget(title)

        content_layout.addSpacing(8)

        # Tagline
        tagline = QLabel("Open-source · Fast · Elegant")
        tagline.setAlignment(Qt.AlignCenter)
        tagline.setStyleSheet(
            f"color: {C['text_tertiary']}; "
            f"font-size: {FONT['sm']}; "
            f"background: transparent;"
        )
        content_layout.addWidget(tagline)

        content_layout.addStretch()

        root.addWidget(content, stretch=1)

        # ── Progress bar strip at the very bottom ─────────────────────
        self._progress = QProgressBar()
        self._progress.setFixedHeight(3)
        self._progress.setTextVisible(False)
        # min == max == 0 triggers Qt's built-in indeterminate animation
        # but cross-platform support is inconsistent, so we drive it manually.
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

    def _make_icon_box(self, size: int) -> QLabel:
        """Return a QLabel painted as the dark G icon box."""
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(C["accent"]))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, size, size, 10, 10)
        painter.setPen(QColor(C["text_inverse"]))
        font = QFont("Segoe UI", int(size * 0.52), QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pix.rect(), Qt.AlignCenter, "G")
        painter.end()

        label = QLabel()
        label.setPixmap(pix)
        label.setFixedSize(size, size)
        label.setStyleSheet("background: transparent;")
        return label

    # ------------------------------------------------------------------
    # Progress bar animation (fake indeterminate)
    # ------------------------------------------------------------------

    def _tick_progress(self) -> None:
        """Advance a bouncing progress indicator."""
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

    def close_animated(self, callback: Optional[Callable] = None) -> None:
        """Fade opacity 1→0 over 250 ms, then call callback and close."""
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
        # Keep a reference so the animation is not garbage-collected
        self._fade_anim = anim
