"""
Animated sidebar navigation for GenosLauncher.

SidebarItem   — individual nav button with icon, label, active state
Sidebar       — vertical nav container with section grouping
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT

# Sidebar dimensions
SIDEBAR_WIDTH = 220
ITEM_HEIGHT = 48


class SidebarItem(QWidget):
    """
    A single navigation item in the sidebar.
    Renders icon + text with a smooth active/hover animation.
    """

    clicked = Signal(str)   # emits the item's key

    def __init__(
        self,
        key: str,
        icon: str,
        label: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self._icon = icon
        self._label = label
        self._active = False
        self._hover_progress: float = 0.0

        self.setFixedHeight(ITEM_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

        self._anim = QPropertyAnimation(self, b"hover_prog", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # ------------------------------------------------------------------
    # Active state
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    # ------------------------------------------------------------------
    # Hover property
    # ------------------------------------------------------------------

    def _get_hover(self) -> float:
        return self._hover_progress

    def _set_hover(self, val: float) -> None:
        self._hover_progress = val
        self.update()

    hover_prog = Property(float, _get_hover, _set_hover)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def enterEvent(self, event) -> None:
        if not self._active:
            self._anim.stop()
            self._anim.setStartValue(self._hover_progress)
            self._anim.setEndValue(1.0)
            self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if not self._active:
            self._anim.stop()
            self._anim.setStartValue(self._hover_progress)
            self._anim.setEndValue(0.0)
            self._anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        t = 1.0 if self._active else self._hover_progress

        # Background fill
        if t > 0.01:
            bg_alpha = int(t * (self._active and 30 or 15))
            accent = QColor(C["accent_cyan"])
            if not self._active:
                accent = QColor(C["text_secondary"])
            accent.setAlpha(bg_alpha)

            path = QPainterPath()
            path.addRoundedRect(8, 4, w - 16, h - 8, 8, 8)
            painter.fillPath(path, accent)

        # Left indicator stripe (active only)
        if self._active:
            grad = QLinearGradient(0, 4, 0, h - 4)
            grad.setColorAt(0.0, QColor(C["accent_cyan"] + "88"))
            grad.setColorAt(0.5, QColor(C["accent_cyan"]))
            grad.setColorAt(1.0, QColor(C["accent_cyan"] + "88"))
            stripe = QPainterPath()
            stripe.addRoundedRect(0, 8, 3, h - 16, 1.5, 1.5)
            painter.fillPath(stripe, grad)

        # Icon
        icon_alpha = int(160 + t * 95)
        icon_color = QColor(C["accent_cyan"]) if self._active else QColor(C["text_secondary"])
        icon_color.setAlpha(min(255, icon_alpha))
        painter.setPen(icon_color)
        icon_font = QFont("Segoe UI Emoji", 16)
        painter.setFont(icon_font)
        painter.drawText(0, 0, 52, h, Qt.AlignCenter, self._icon)

        # Label
        label_color = QColor(C["text_primary"] if self._active else C["text_secondary"])
        label_alpha = int(140 + t * 115)
        label_color.setAlpha(min(255, label_alpha))
        painter.setPen(label_color)
        label_font = QFont("Segoe UI", 10)
        label_font.setWeight(QFont.Weight.SemiBold if self._active else QFont.Weight.Medium)
        painter.setFont(label_font)
        painter.drawText(52, 0, w - 52 - 12, h, Qt.AlignVCenter | Qt.AlignLeft, self._label)

        painter.end()


class SidebarSectionLabel(QWidget):
    """A subtle section header in the sidebar."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self._text = text
        self.setFixedHeight(32)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        painter.setPen(QColor(C["text_muted"]))
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        painter.setFont(font)
        painter.drawText(16, 0, self.width() - 16, h, Qt.AlignVCenter | Qt.AlignLeft, self._text.upper())
        painter.end()


class Sidebar(QWidget):
    """
    Full sidebar navigation widget.

    Signals:
        tab_changed(str)  — emitted with the key of the selected tab
    """

    tab_changed = Signal(str)

    NAV_ITEMS = [
        ("home",      "🏠", "Home"),
        ("instances", "📦", "Instances"),
        ("mods",      "🔧", "Mods"),
        ("accounts",  "👤", "Accounts"),
        ("settings",  "⚙", "Settings"),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setObjectName("Sidebar")
        self.setStyleSheet(f"#Sidebar {{ background-color: {C['bg_sidebar']}; border-right: 1px solid {C['border']}; }}")

        self._items: dict[str, SidebarItem] = {}
        self._active_key: str = "home"

        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scrollable nav area
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        nav_widget = QWidget()
        nav_widget.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 16, 0, 16)
        nav_layout.setSpacing(2)

        # Section label
        nav_layout.addWidget(SidebarSectionLabel("Navigation"))
        nav_layout.addSpacing(4)

        for key, icon, label in self.NAV_ITEMS:
            item = SidebarItem(key, icon, label, nav_widget)
            item.clicked.connect(self._on_item_clicked)
            if key == self._active_key:
                item.set_active(True)
            self._items[key] = item
            nav_layout.addWidget(item)

        nav_layout.addStretch()
        scroll.setWidget(nav_widget)
        outer.addWidget(scroll)

        # Bottom: version info
        bottom = QWidget(self)
        bottom.setFixedHeight(60)
        bottom.setStyleSheet(f"border-top: 1px solid {C['border']}; background: transparent;")
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(16, 10, 16, 10)
        version_lbl = QLabel("GenosLauncher v0.1.0", bottom)
        version_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: {FONT['xs']};")
        bl.addWidget(version_lbl)
        outer.addWidget(bottom)

    def _on_item_clicked(self, key: str) -> None:
        if key == self._active_key:
            return
        # Deactivate old
        if self._active_key in self._items:
            self._items[self._active_key].set_active(False)
        # Activate new
        self._active_key = key
        self._items[key].set_active(True)
        self.tab_changed.emit(key)

    def set_active(self, key: str) -> None:
        self._on_item_clicked(key)

    # ------------------------------------------------------------------
    # Paint — full background
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(C["bg_sidebar"]))
        painter.end()
