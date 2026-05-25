"""
Clean light sidebar navigation for GenosLauncher.

SidebarItem       — individual nav row (icon + label, 40px tall)
SidebarSection    — ALL CAPS section header label
Sidebar           — 200px wide container, emits tab_changed signal
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from .account_widget import AccountWidget

SIDEBAR_WIDTH = 186
ITEM_HEIGHT   = 36


class SidebarItem(QWidget):
    """
    A single navigation row.

    Active state: soft orange bg, orange marker, 2px solid left indicator.
    Hover (inactive): #F4F6F8 bg.
    All drawn via paintEvent, animated at 150ms on hover_progress.
    """

    clicked = Signal(str)

    def __init__(
        self,
        key: str,
        icon: str,
        label: str,
        parent: QWidget | None = None,
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
        self.setAttribute(Qt.WA_Hover, True)

        self._anim = QPropertyAnimation(self, b"hover_progress", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # --- Active state ------------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            self._hover_progress = 0.0
        self.update()

    # --- Qt property -------------------------------------------------------

    def _get_hover(self) -> float:
        return self._hover_progress

    def _set_hover(self, val: float) -> None:
        self._hover_progress = val
        self.update()

    hover_progress = Property(float, _get_hover, _set_hover)

    # --- Events ------------------------------------------------------------

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

    # --- Paint -------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        if self._active:
            # Active background
            bg_path = QPainterPath()
            bg_path.addRoundedRect(8, 2, w - 14, h - 4, 6, 6)
            painter.fillPath(bg_path, QColor(C['accent_blue_soft']))

            # Left 2px indicator
            ind = QPainterPath()
            ind.addRoundedRect(0, 8, 2, h - 16, 1, 1)
            painter.fillPath(ind, QColor(C['accent_blue']))

        elif self._hover_progress > 0.01:
            # Hover background
            bg = QColor(C['bg_hover'])
            bg.setAlpha(int(self._hover_progress * 255))
            bg_path = QPainterPath()
            bg_path.addRoundedRect(8, 2, w - 14, h - 4, 6, 6)
            painter.fillPath(bg_path, bg)

        # Compact marker replaces emoji glyphs so rows align consistently.
        marker_color = QColor(C['accent_orange'] if self._active else C['border_strong'])
        if not self._active:
            marker_color.setAlpha(int(110 + self._hover_progress * 80))
        painter.setBrush(marker_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(18, h // 2 - 3, 6, 6, 3, 3)

        # Label
        if self._active:
            label_color = QColor(C['accent_blue'])
        else:
            label_color = QColor(C['text_secondary'])
            label_alpha = int(160 + self._hover_progress * 95)
            label_color.setAlpha(min(255, label_alpha))
        painter.setPen(label_color)
        label_font = QFont("Segoe UI", 9)
        label_font.setWeight(
            QFont.Weight.DemiBold if self._active else QFont.Weight.Medium
        )
        painter.setFont(label_font)
        painter.drawText(34, 0, w - 40, h, Qt.AlignVCenter | Qt.AlignLeft, self._label)

        painter.end()


class SidebarSection(QWidget):
    """ALL CAPS 10px section header in text_tertiary color."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text.upper()
        self.setFixedHeight(28)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor(C['text_tertiary']))
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
        painter.setFont(font)
        painter.drawText(16, 0, self.width() - 16, self.height(), Qt.AlignVCenter | Qt.AlignLeft, self._text)
        painter.end()


class Sidebar(QWidget):
    """
    200px wide sidebar navigation.
    Background: #FAFBFC, right border: 1px #E5E7EB.

    Signals:
        tab_changed(str)  — key of the newly selected tab
    """

    tab_changed = Signal(str)
    login_requested  = Signal()
    logout_requested = Signal()

    NAV_ITEMS: list[tuple[str, str, str]] = [
        ("home",      "", "Home"),
        ("instances", "", "Instances"),
        ("mods",      "", "Mods"),
        ("modpacks",  "", "Modpacks"),
        ("shaders",   "", "Shaders"),
        ("servers",   "", "Servers"),
        ("accounts",  "", "Accounts"),
        ("settings",  "", "Settings"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setObjectName("Sidebar")
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
        nav = QVBoxLayout(nav_widget)
        nav.setContentsMargins(0, 10, 0, 10)
        nav.setSpacing(0)

        nav.addWidget(SidebarSection("Navigation", nav_widget))
        nav.addSpacing(4)

        for key, icon, label in self.NAV_ITEMS:
            item = SidebarItem(key, icon, label, nav_widget)
            item.clicked.connect(self._on_item_clicked)
            if key == self._active_key:
                item.set_active(True)
            self._items[key] = item
            nav.addWidget(item)

        nav.addStretch()
        scroll.setWidget(nav_widget)
        outer.addWidget(scroll)

        # Account widget at bottom
        self.account_widget = AccountWidget(self)
        self.account_widget.login_requested.connect(self.login_requested)
        self.account_widget.logout_requested.connect(self.logout_requested)
        outer.addWidget(self.account_widget)

    def _on_item_clicked(self, key: str) -> None:
        if key == self._active_key:
            return
        if self._active_key in self._items:
            self._items[self._active_key].set_active(False)
        self._active_key = key
        self._items[key].set_active(True)
        self.tab_changed.emit(key)

    def set_active(self, key: str) -> None:
        """Programmatically switch the active tab."""
        self._on_item_clicked(key)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        # Sidebar background
        painter.fillRect(self.rect(), QColor(C['bg_sidebar']))
        # Right border
        painter.setPen(QColor(C['border']))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        painter.end()
