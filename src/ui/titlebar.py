"""
Custom frameless title bar for GenosLauncher.

Handles window dragging, minimize/maximize/close, and displays the
app logo + name. Fully styled to match the premium dark theme.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QLinearGradient
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QGraphicsDropShadowEffect,
)

from .styles import COLORS as C, FONT

TITLEBAR_HEIGHT = 52


class WindowControlButton(QPushButton):
    """Minimize / Maximize / Close button with hover animation."""

    def __init__(
        self,
        symbol: str,
        hover_color: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._symbol = symbol
        self._hover_color = QColor(hover_color)
        self._base_color = QColor(C["bg_sidebar"])
        self._current_color = QColor(self._base_color)

        self.setFixedSize(QSize(46, TITLEBAR_HEIGHT))
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.setToolTip(
            {"×": "Close", "□": "Maximize", "−": "Minimize"}.get(symbol, symbol)
        )

        # Opacity animation
        self._opacity: float = 0.0
        self._anim = QPropertyAnimation(self, b"_opacity_prop", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # Qt property for animation
    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, val: float) -> None:
        self._opacity = val
        # Interpolate between base and hover color
        base = self._base_color
        hover = self._hover_color
        r = int(base.red() + (hover.red() - base.red()) * val)
        g = int(base.green() + (hover.green() - base.green()) * val)
        b = int(base.blue() + (hover.blue() - base.blue()) * val)
        self._current_color = QColor(r, g, b)
        self.update()

    _opacity_prop = property(_get_opacity, _set_opacity)

    def enterEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._opacity)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._opacity)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background circle on hover
        if self._opacity > 0.01:
            color = QColor(self._current_color)
            color.setAlpha(int(180 * self._opacity))
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            cx, cy = self.width() // 2, self.height() // 2
            painter.drawEllipse(cx - 14, cy - 14, 28, 28)

        # Symbol
        text_color = QColor(C["text_primary"])
        painter.setPen(text_color)
        font = QFont("Segoe UI", 14, QFont.Weight.Normal)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self._symbol)
        painter.end()


class LogoWidget(QWidget):
    """Animated GenosLauncher logo mark."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(36, 36)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Outer glow
        glow = QColor(C["accent_cyan"])
        glow.setAlpha(60)
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 32, 32)

        # Gradient diamond / "G" shape
        grad = QLinearGradient(0, 0, 36, 36)
        grad.setColorAt(0.0, QColor(C["accent_purple"]))
        grad.setColorAt(1.0, QColor(C["accent_cyan"]))
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)

        path = QPainterPath()
        cx, cy, r = 18, 18, 12
        # Draw a rounded diamond
        path.moveTo(cx, cy - r)
        path.cubicTo(cx + r * 0.5, cy - r * 0.5, cx + r, cy - r * 0.5, cx + r, cy)
        path.cubicTo(cx + r, cy + r * 0.5, cx + r * 0.5, cy + r, cx, cy + r)
        path.cubicTo(cx - r * 0.5, cy + r, cx - r, cy + r * 0.5, cx - r, cy)
        path.cubicTo(cx - r, cy - r * 0.5, cx - r * 0.5, cy - r, cx, cy - r)
        painter.drawPath(path)

        # Inner highlight dot
        painter.setBrush(QColor(255, 255, 255, 120))
        painter.drawEllipse(14, 10, 6, 6)
        painter.end()


class TitleBar(QWidget):
    """
    Frameless custom title bar.

    Drop this at the top of the main window layout.
    The parent window must have Qt.FramelessWindowHint set.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(TITLEBAR_HEIGHT)
        self.setObjectName("TitleBar")
        self.setStyleSheet(f"""
            #TitleBar {{
                background-color: {C["bg_sidebar"]};
                border-bottom: 1px solid {C["border"]};
            }}
        """)

        self._drag_start: QPoint | None = None
        self._win_start_pos: QPoint | None = None
        self._maximized = False

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(0)

        # Logo
        logo = LogoWidget(self)
        layout.addWidget(logo)

        layout.addSpacing(10)

        # App name
        name_label = QLabel("GenosLauncher", self)
        name_label.setStyleSheet(f"""
            font-size: {FONT["lg"]};
            font-weight: 700;
            color: {C["text_primary"]};
            letter-spacing: 0.5px;
        """)
        layout.addWidget(name_label)

        # Version badge
        version_badge = QLabel("ALPHA", self)
        version_badge.setStyleSheet(f"""
            background-color: {C["accent_purple"]}33;
            color: {C["accent_purple"]};
            border: 1px solid {C["accent_purple"]}55;
            border-radius: 4px;
            padding: 2px 7px;
            font-size: {FONT["xs"]};
            font-weight: 700;
            letter-spacing: 1px;
            margin-left: 8px;
        """)
        layout.addWidget(version_badge)

        layout.addStretch()

        # Window controls
        self._btn_min = WindowControlButton("−", "#FBC02D", self)
        self._btn_max = WindowControlButton("□", "#43A047", self)
        self._btn_close = WindowControlButton("×", "#E53935", self)

        self._btn_min.clicked.connect(self._on_minimize)
        self._btn_max.clicked.connect(self._on_maximize_restore)
        self._btn_close.clicked.connect(self._on_close)

        layout.addWidget(self._btn_min)
        layout.addWidget(self._btn_max)
        layout.addWidget(self._btn_close)

    # ------------------------------------------------------------------
    # Window actions
    # ------------------------------------------------------------------

    def _get_window(self) -> QWidget:
        return self.window()

    def _on_minimize(self) -> None:
        self._get_window().showMinimized()

    def _on_maximize_restore(self) -> None:
        win = self._get_window()
        if self._maximized:
            win.showNormal()
            self._btn_max.setText("□")
        else:
            win.showMaximized()
            self._btn_max.setText("❐")
        self._maximized = not self._maximized

    def _on_close(self) -> None:
        self._get_window().close()

    # ------------------------------------------------------------------
    # Window drag (frameless)
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._win_start_pos = self._get_window().pos()

    def mouseMoveEvent(self, event) -> None:
        if (
            self._drag_start is not None
            and event.buttons() == Qt.LeftButton
            and not self._maximized
        ):
            delta = event.globalPosition().toPoint() - self._drag_start
            self._get_window().move(self._win_start_pos + delta)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start = None
        self._win_start_pos = None

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._on_maximize_restore()
