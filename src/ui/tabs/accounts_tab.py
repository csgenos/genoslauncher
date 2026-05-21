"""
Accounts tab — Microsoft login + account management.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import GhostButton, AnimatedButton
from ..components.glass_card import GlassCard


class AccountAvatar(QWidget):
    """Circular avatar placeholder."""

    def __init__(self, initials: str, color: str = C["accent_cyan"], size: int = 52, parent=None) -> None:
        super().__init__(parent)
        self._initials = initials
        self._color = QColor(color)
        self.setFixedSize(size, size)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Background circle
        bg = QColor(self._color)
        bg.setAlpha(40)
        painter.setBrush(bg)
        border = QColor(self._color)
        border.setAlpha(120)
        painter.setPen(border)
        painter.drawEllipse(1, 1, w - 2, h - 2)

        # Initials
        painter.setPen(self._color)
        font = QFont("Segoe UI", w // 3, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self._initials)
        painter.end()


class AccountItem(GlassCard):
    """A card representing a single account."""

    def __init__(self, username: str, account_type: str = "Offline", is_active: bool = False, parent=None) -> None:
        color = C["accent_cyan"] if is_active else C["border"]
        super().__init__(border=color, hover_glow=True, glow_color=C["accent_cyan"], parent=parent)
        self.setFixedHeight(80)

        layout = QHBoxLayout()
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)

        initials = "".join(w[0].upper() for w in username.split()[:2]) or "?"
        avatar_color = C["accent_cyan"] if is_active else C["accent_purple"]
        avatar = AccountAvatar(initials, avatar_color, 44, self)
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
            active_badge = QLabel("● Active")
            active_badge.setStyleSheet(f"""
                color: {C["accent_green"]};
                background: {C["accent_green"]}22;
                border: 1px solid {C["accent_green"]}44;
                border-radius: 10px;
                padding: 3px 10px;
                font-size: {FONT["xs"]};
                font-weight: 700;
            """)
            layout.addWidget(active_badge)
        else:
            select_btn = GhostButton("Select", accent=C["accent_cyan"])
            select_btn.setFixedSize(80, 30)
            layout.addWidget(select_btn)

        remove_btn = GhostButton("✕", accent=C["danger"])
        remove_btn.setFixedSize(34, 34)
        layout.addWidget(remove_btn)

        inner = QWidget()
        inner.setLayout(layout)
        inner.setStyleSheet("background: transparent;")
        self.layout().addWidget(inner)


class AccountsTab(QWidget):
    """Accounts management tab."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 32, 48, 32)
        root.setSpacing(28)

        # Header
        title = QLabel("Accounts")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        root.addWidget(title)
        subtitle = QLabel("Manage your Minecraft accounts. Sign in with Microsoft for online play.")
        subtitle.setStyleSheet(f"font-size: {FONT['md']}; color: {C['text_secondary']}; margin-top: -16px;")
        root.addWidget(subtitle)

        # Microsoft login card
        ms_card = GlassCard(hover_glow=True, glow_color=C["accent_blue"])
        ms_layout = QHBoxLayout()
        ms_layout.setContentsMargins(24, 20, 24, 20)
        ms_layout.setSpacing(20)

        ms_icon_container = QWidget()
        ms_icon_container.setFixedSize(56, 56)
        ms_icon_container.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0078d4, stop:1 #00bcf2);
            border-radius: 14px;
        """)
        ms_icon_layout = QVBoxLayout(ms_icon_container)
        ms_icon_label = QLabel("M")
        ms_icon_label.setAlignment(Qt.AlignCenter)
        ms_icon_label.setStyleSheet("color: white; font-size: 24px; font-weight: 900; background: transparent;")
        ms_icon_layout.addWidget(ms_icon_label)
        ms_layout.addWidget(ms_icon_container)

        ms_text = QVBoxLayout()
        ms_text.setSpacing(3)
        ms_title = QLabel("Sign in with Microsoft")
        ms_title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        ms_text.addWidget(ms_title)
        ms_sub = QLabel("Required for online multiplayer. Links your Xbox / Minecraft account.")
        ms_sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        ms_text.addWidget(ms_sub)
        ms_layout.addLayout(ms_text)
        ms_layout.addStretch()

        ms_btn = AnimatedButton(
            "Sign In",
            color_start="#0078d4",
            color_end="#005a9e",
            accent="#4ec9f7",
            text_color=C["text_primary"],
        )
        ms_btn.setFixedSize(110, 40)
        ms_layout.addWidget(ms_btn)

        ms_inner = QWidget()
        ms_inner.setLayout(ms_layout)
        ms_inner.setStyleSheet("background: transparent;")
        ms_card.layout().addWidget(ms_inner)
        root.addWidget(ms_card)

        # Add offline account
        offline_row = QHBoxLayout()
        offline_label = QLabel("Or add an offline account:")
        offline_label.setStyleSheet(f"color: {C['text_secondary']}; font-size: {FONT['sm']};")
        offline_row.addWidget(offline_label)
        offline_row.addStretch()
        add_offline_btn = GhostButton("+ Add Offline Account", accent=C["accent_purple"])
        add_offline_btn.setFixedHeight(36)
        offline_row.addWidget(add_offline_btn)
        root.addLayout(offline_row)

        # Accounts list
        accounts_label = QLabel("Your Accounts")
        accounts_label.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        root.addWidget(accounts_label)

        # Demo accounts
        root.addWidget(AccountItem("Player", "Offline · Unverified", is_active=True))
        root.addWidget(AccountItem("Steve", "Offline · Unverified", is_active=False))

        root.addStretch()

        # Info note
        note = QLabel("ℹ  GenosLauncher stores account tokens locally and never shares them with third parties.")
        note.setStyleSheet(f"""
            color: {C["text_muted"]};
            font-size: {FONT["xs"]};
            background: {C["bg_card"]};
            border: 1px solid {C["border"]};
            border-radius: 8px;
            padding: 10px 14px;
        """)
        note.setWordWrap(True)
        root.addWidget(note)
