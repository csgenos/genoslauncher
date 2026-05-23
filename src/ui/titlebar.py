"""
Custom frameless title bar for GenosLauncher — light / white theme.

Handles window dragging, minimize/maximize/close, and displays the
app logo mark + name. Styled to match the premium light aesthetic.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from .styles import COLORS, FONT

C = COLORS
TITLEBAR_HEIGHT = 48


def _asset(name: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", name)


class LogoMark(QLabel):
    """App logo mark shown in the title bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setStyleSheet("background: transparent;")
        self.setAlignment(Qt.AlignCenter)
        logo_path = _asset("glauncherlogo.png")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.setPixmap(pix)
        else:
            self._draw_fallback()

    def _draw_fallback(self) -> None:
        pix = QPixmap(28, 28)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, 28, 28, 6, 6)
        painter.fillPath(path, QColor(C['accent']))
        painter.setPen(QColor(C['text_inverse']))
        painter.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        painter.drawText(0, 0, 28, 28, Qt.AlignCenter, "G")
        painter.end()
        self.setPixmap(pix)


class WindowControlButton(QWidget):
    """
    A single window control button (minimize / maximize / close).

    Renders as a transparent circle that reveals a colored background on hover,
    animated with a 150ms QPropertyAnimation on the hover_progress float property.
    """

    clicked = Signal()

    def __init__(
        self,
        symbol: str,
        hover_bg: str,
        symbol_color: str = C['text_secondary'],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._symbol = symbol
        self._hover_bg = QColor(hover_bg)
        self._symbol_color = QColor(symbol_color)
        self._hover_progress: float = 0.0

        self.setFixedSize(QSize(32, 32))
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        self._anim = QPropertyAnimation(self, b"hover_progress", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # --- Qt property -------------------------------------------------------

    def _get_hover(self) -> float:
        return self._hover_progress

    def _set_hover(self, val: float) -> None:
        self._hover_progress = val
        self.update()

    hover_progress = Property(float, _get_hover, _set_hover)

    # --- Events ------------------------------------------------------------

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

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    # --- Paint -------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        t = self._hover_progress
        cx, cy = self.width() // 2, self.height() // 2

        # Hover circle background
        if t > 0.01:
            bg = QColor(self._hover_bg)
            bg.setAlpha(int(t * 255))
            painter.setBrush(bg)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(cx - 13, cy - 13, 26, 26)

        # Symbol
        color = QColor(self._symbol_color)
        color.setAlpha(int(180 + t * 75))
        painter.setPen(color)
        font = QFont("Segoe UI", 12, QFont.Weight.Normal)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self._symbol)

        painter.end()


class TitleBar(QWidget):
    """
    Frameless custom title bar — 48px tall, white background.

    The parent window must have Qt.FramelessWindowHint set.
    Supports drag-to-move and double-click-to-maximize.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(TITLEBAR_HEIGHT)
        self.setObjectName("TitleBar")
        self.setStyleSheet(
            f"#TitleBar {{ "
            f"background-color: {C['bg_primary']}; "
            f"border-bottom: 1px solid {C['border']}; "
            f"}}"
        )

        self._drag_start: QPoint | None = None
        self._win_start_pos: QPoint | None = None
        self._maximized: bool = False

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(0)

        # Logo mark
        logo = LogoMark(self)
        layout.addWidget(logo)
        layout.addSpacing(10)

        # App name
        name_label = QLabel("GenosLauncher", self)
        name_label.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {C['text_primary']}; "
            f"letter-spacing: -0.2px;"
        )
        layout.addWidget(name_label)

        layout.addStretch()

        # Window control buttons
        self._btn_min = WindowControlButton(
            "−",
            hover_bg="#F3F4F6",
            symbol_color=C['text_secondary'],
            parent=self,
        )
        self._btn_max = WindowControlButton(
            "⬜",
            hover_bg="#F3F4F6",
            symbol_color=C['text_secondary'],
            parent=self,
        )
        self._btn_close = WindowControlButton(
            "×",
            hover_bg="#FEE2E2",
            symbol_color=C['accent_red'],
            parent=self,
        )

        self._btn_min.clicked.connect(self._on_minimize)
        self._btn_max.clicked.connect(self._on_maximize_restore)
        self._btn_close.clicked.connect(self._on_close)

        layout.addWidget(self._btn_min)
        layout.addSpacing(4)
        layout.addWidget(self._btn_max)
        layout.addSpacing(4)
        layout.addWidget(self._btn_close)
        layout.addSpacing(4)

    # --- Window actions ----------------------------------------------------

    def _window(self) -> QWidget:
        return self.window()

    def _on_minimize(self) -> None:
        self._window().showMinimized()

    def _on_maximize_restore(self) -> None:
        win = self._window()
        if self._maximized:
            win.showNormal()
        else:
            win.showMaximized()
        self._maximized = not self._maximized

    def _on_close(self) -> None:
        self._window().close()

    # --- Drag support ------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._win_start_pos = self._window().pos()

    def mouseMoveEvent(self, event) -> None:
        if (
            self._drag_start is not None
            and event.buttons() == Qt.LeftButton
            and not self._maximized
        ):
            delta = event.globalPosition().toPoint() - self._drag_start
            self._window().move(self._win_start_pos + delta)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start = None
        self._win_start_pos = None

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._on_maximize_restore()
