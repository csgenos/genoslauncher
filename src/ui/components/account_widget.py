"""
Sidebar account widget — shows avatar circle + username + logout.
Displayed at the bottom of the sidebar when a user is logged in.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import OutlineButton


class _AvatarCircle(QWidget):
    def __init__(self, initials: str, size: int = 32, parent=None) -> None:
        super().__init__(parent)
        self._initials = initials[:2].upper()
        self.setFixedSize(size, size)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        painter.setBrush(QColor("#DBEAFE"))
        painter.setPen(QColor("#93C5FD"))
        painter.drawEllipse(1, 1, w - 2, h - 2)
        painter.setPen(QColor(C["accent_blue"]))
        font = QFont("Segoe UI", w // 3, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(0, 0, w, h, Qt.AlignCenter, self._initials)
        painter.end()


class AccountWidget(QWidget):
    """
    Compact account strip for the sidebar bottom.

    Signals:
      logout_requested — user clicked Logout
      login_requested  — user clicked the widget while logged out
    """

    logout_requested = Signal()
    login_requested  = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._logged_in = False
        self._build_ui()
        self.set_logged_out()

    def _build_ui(self) -> None:
        self.setFixedHeight(64)
        self.setStyleSheet(f"""
            AccountWidget {{
                background: {C["bg_primary"]};
                border-top: 1px solid {C["border"]};
            }}
        """)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 0, 12, 0)
        outer.setSpacing(10)

        self._avatar = _AvatarCircle("?", 32, self)
        outer.addWidget(self._avatar)

        info = QVBoxLayout()
        info.setSpacing(1)
        self._name_lbl = QLabel("Not signed in")
        self._name_lbl.setStyleSheet(
            f"font-size: {FONT['sm']}; font-weight: 600; color: {C['text_primary']};"
        )
        info.addWidget(self._name_lbl)

        self._type_lbl = QLabel("Sign in for online play")
        self._type_lbl.setStyleSheet(
            f"font-size: {FONT['xs']}; color: {C['text_tertiary']};"
        )
        info.addWidget(self._type_lbl)
        outer.addLayout(info, 1)

        self._action_btn = OutlineButton("Sign In")
        self._action_btn.setFixedSize(60, 26)
        self._action_btn.clicked.connect(self._on_action)
        outer.addWidget(self._action_btn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_logged_in(self, username: str, account_type: str = "Microsoft") -> None:
        self._logged_in = True
        initials = "".join(w[0] for w in username.split()[:2]) or "?"
        self._avatar._initials = initials.upper()
        self._avatar.update()
        self._name_lbl.setText(username)
        self._type_lbl.setText(account_type)
        self._action_btn.setText("Sign Out")
        self._action_btn.setFixedSize(68, 26)

    def set_logged_out(self) -> None:
        self._logged_in = False
        self._avatar._initials = "?"
        self._avatar.update()
        self._name_lbl.setText("Not signed in")
        self._type_lbl.setText("Sign in for online play")
        self._action_btn.setText("Sign In")
        self._action_btn.setFixedSize(60, 26)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_action(self) -> None:
        if self._logged_in:
            self.logout_requested.emit()
        else:
            self.login_requested.emit()
