"""
Accounts tab — Microsoft login + offline account management.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import OutlineButton, PrimaryButton


# ---------------------------------------------------------------------------
# Account avatar (circular initials badge)
# ---------------------------------------------------------------------------

class AccountAvatar(QWidget):
    """Circular avatar with user initials."""

    def __init__(self, initials: str, size: int = 44, parent=None) -> None:
        super().__init__(parent)
        self._initials = initials[:2].upper()
        self.setFixedSize(size, size)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Circle background
        painter.setBrush(QColor(C["bg_tertiary"]))
        painter.setPen(QColor(C["border_strong"]))
        painter.drawEllipse(1, 1, w - 2, h - 2)

        # Initials
        painter.setPen(QColor(C["text_secondary"]))
        font = QFont("Segoe UI", w // 3, QFont.Weight.SemiBold)
        painter.setFont(font)
        painter.drawText(0, 0, w, h, Qt.AlignCenter, self._initials)
        painter.end()


# ---------------------------------------------------------------------------
# Account row card
# ---------------------------------------------------------------------------

class AccountRow(QFrame):
    """A single account entry card."""

    def __init__(
        self,
        username: str,
        account_type: str = "Offline",
        is_active: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AccountRow")
        self.setFixedHeight(72)
        border_color = C["accent_blue"] if is_active else C["border"]
        self.setStyleSheet(f"""
            #AccountRow {{
                background: {C["bg_primary"]};
                border: 1px solid {border_color};
                border-radius: 10px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)

        initials = "".join(w[0] for w in username.split()[:2]) or "?"
        avatar = AccountAvatar(initials, 40, self)
        layout.addWidget(avatar)

        info = QVBoxLayout()
        info.setSpacing(2)
        name_lbl = QLabel(username)
        name_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        info.addWidget(name_lbl)
        type_lbl = QLabel(account_type)
        type_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        info.addWidget(type_lbl)
        layout.addLayout(info)
        layout.addStretch()

        if is_active:
            badge = QLabel("● Active")
            badge.setStyleSheet(f"""
                color: {C["success"]};
                background: {C["accent_green_soft"]};
                border: 1px solid #6EE7B7;
                border-radius: 8px;
                padding: 2px 10px;
                font-size: {FONT["xs"]};
                font-weight: 700;
            """)
            layout.addWidget(badge)
        else:
            select_btn = OutlineButton("Select")
            select_btn.setFixedSize(72, 30)
            layout.addWidget(select_btn)

        remove_btn = OutlineButton("✕")
        remove_btn.setFixedSize(32, 30)
        layout.addWidget(remove_btn)


# ---------------------------------------------------------------------------
# Accounts Tab
# ---------------------------------------------------------------------------

class AccountsTab(QWidget):
    """Accounts management tab."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 28, 40, 28)
        root.setSpacing(20)

        # Page header
        title = QLabel("Accounts")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        root.addWidget(title)
        sub = QLabel("Sign in with Microsoft for online play, or add an offline account for solo play.")
        sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']}; margin-top: -12px;")
        root.addWidget(sub)

        # Microsoft login card
        ms_card = QFrame()
        ms_card.setObjectName("MsCard")
        ms_card.setFixedHeight(96)
        ms_card.setStyleSheet(f"""
            #MsCard {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 12px;
            }}
        """)
        ms_h = QHBoxLayout(ms_card)
        ms_h.setContentsMargins(20, 0, 20, 0)
        ms_h.setSpacing(18)

        # M icon
        m_icon = QLabel("M")
        m_icon.setFixedSize(52, 52)
        m_icon.setAlignment(Qt.AlignCenter)
        m_icon.setStyleSheet("""
            background: #0078D4;
            color: white;
            border-radius: 10px;
            font-size: 22px;
            font-weight: 900;
        """)
        ms_h.addWidget(m_icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        ms_title = QLabel("Sign in with Microsoft")
        ms_title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        text_col.addWidget(ms_title)
        ms_sub = QLabel("Required for online multiplayer. Links your Xbox / Minecraft account.")
        ms_sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        text_col.addWidget(ms_sub)
        ms_h.addLayout(text_col)
        ms_h.addStretch()

        sign_in_btn = PrimaryButton("Sign In")
        sign_in_btn.setFixedSize(100, 38)
        ms_h.addWidget(sign_in_btn)

        root.addWidget(ms_card)

        # Offline account row
        offline_row = QHBoxLayout()
        offline_lbl = QLabel("Or add an offline account:")
        offline_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        offline_row.addWidget(offline_lbl)
        offline_row.addStretch()
        add_offline = OutlineButton("+ Add Offline Account")
        add_offline.setFixedHeight(34)
        offline_row.addWidget(add_offline)
        root.addLayout(offline_row)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {C['border']}; border: none;")
        root.addWidget(div)

        # Accounts list
        list_title = QLabel("Your Accounts")
        list_title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        root.addWidget(list_title)

        root.addWidget(AccountRow("Player", "Offline · Unverified", is_active=True))
        root.addWidget(AccountRow("Steve", "Offline · Unverified", is_active=False))

        root.addStretch()

        # Privacy note
        note = QLabel(
            "GenosLauncher stores account tokens locally on your device "
            "and never shares them with third parties."
        )
        note.setStyleSheet(f"""
            color: {C["text_tertiary"]};
            font-size: {FONT["xs"]};
            background: {C["bg_secondary"]};
            border: 1px solid {C["border"]};
            border-radius: 8px;
            padding: 10px 14px;
        """)
        note.setWordWrap(True)
        root.addWidget(note)
