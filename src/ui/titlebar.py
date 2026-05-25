"""
Custom frameless title bar for GenosLauncher.

Desktop-first layout with compact controls and right-aligned branding.
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
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .styles import COLORS

C = COLORS
TITLEBAR_HEIGHT = 46


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
        painter.fillPath(path, QColor(C["accent"]))
        painter.setPen(QColor(C["text_inverse"]))
        painter.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        painter.drawText(0, 0, 28, 28, Qt.AlignCenter, "G")
        painter.end()
        self.setPixmap(pix)


class WindowControlButton(QWidget):
    """Custom minimize / maximize / close control with hover animation."""

    clicked = Signal()

    def __init__(
        self,
        symbol: str,
        hover_bg: str,
        symbol_color: str = C["text_secondary"],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._symbol = symbol
        self._hover_bg = QColor(hover_bg)
        self._symbol_color = QColor(symbol_color)
        self._hover_progress: float = 0.0

        self.setFixedSize(QSize(30, 30))
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        self._anim = QPropertyAnimation(self, b"hover_progress", self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def _get_hover(self) -> float:
        return self._hover_progress

    def _set_hover(self, val: float) -> None:
        self._hover_progress = val
        self.update()

    hover_progress = Property(float, _get_hover, _set_hover)

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

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        t = self._hover_progress
        cx, cy = self.width() // 2, self.height() // 2
        if t > 0.01:
            bg = QColor(self._hover_bg)
            bg.setAlpha(int(t * 255))
            painter.setBrush(bg)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(cx - 12, cy - 12, 24, 24)

        color = QColor(self._symbol_color)
        color.setAlpha(int(180 + t * 75))
        painter.setPen(color)
        font = QFont("Segoe UI", 10, QFont.Weight.Medium)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self._symbol)
        painter.end()


class TitleBar(QWidget):
    """Frameless custom title bar with drag support."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(TITLEBAR_HEIGHT)
        self.setObjectName("TitleBar")
        self._drag_start: QPoint | None = None
        self._win_start_pos: QPoint | None = None
        self._maximized: bool = False
        self._build_ui()
        self.refresh_theme()

    def refresh_theme(self) -> None:
        self.setStyleSheet(
            f"#TitleBar {{ background-color: {C['bg_primary']}; border-bottom: 1px solid {C['border']}; }}"
        )
        self._app_name.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {C['text_primary']}; letter-spacing: 0px;"
        )
        self._status_badge.setStyleSheet(
            f"""
            QLabel {{
                color: {C['text_secondary']};
                background: {C['bg_secondary']};
                border: 1px solid {C['border']};
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 600;
            }}
            """
        )
        self._logo_text.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {C['text_secondary']};")
        self.update()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 8, 0)
        layout.setSpacing(0)

        self._app_name = QLabel("GenosLauncher", self)
        layout.addWidget(self._app_name)
        layout.addSpacing(10)

        self._status_badge = QLabel("Desktop Mode", self)
        layout.addWidget(self._status_badge)
        layout.addStretch()

        right_logo = LogoMark(self)
        right_logo.setFixedSize(22, 22)
        layout.addWidget(right_logo)
        layout.addSpacing(6)
        self._logo_text = QLabel("Genos", self)
        layout.addWidget(self._logo_text)
        layout.addSpacing(8)

        hover_bg = C["bg_hover"]
        close_hover = "#FECACA" if C["text_primary"] == "#111827" else "#7F1D1D"
        self._btn_min = WindowControlButton("-", hover_bg, C["text_secondary"], self)
        self._btn_max = WindowControlButton("[]", hover_bg, C["text_secondary"], self)
        self._btn_close = WindowControlButton("x", close_hover, C["accent_red"], self)

        self._btn_min.clicked.connect(self._on_minimize)
        self._btn_max.clicked.connect(self._on_maximize_restore)
        self._btn_close.clicked.connect(self._on_close)

        layout.addWidget(self._btn_min)
        layout.addSpacing(4)
        layout.addWidget(self._btn_max)
        layout.addSpacing(4)
        layout.addWidget(self._btn_close)
        layout.addSpacing(4)

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

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._win_start_pos = self._window().pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is not None and event.buttons() == Qt.LeftButton and not self._maximized:
            delta = event.globalPosition().toPoint() - self._drag_start
            self._window().move(self._win_start_pos + delta)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start = None
        self._win_start_pos = None

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._on_maximize_restore()
