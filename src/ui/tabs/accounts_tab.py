"""
Accounts tab — Microsoft login + offline account management.
Integrated with auth_manager for real PKCE login flow.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import OutlineButton, PrimaryButton
from ..login_dialog import LoginDialog
from ...core.auth import auth_manager
from ...core.config import config


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
        painter.setBrush(QColor(C["bg_tertiary"]))
        painter.setPen(QColor(C["border_strong"]))
        painter.drawEllipse(1, 1, w - 2, h - 2)
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
        on_select=None,
        on_remove=None,
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
            if on_select:
                select_btn.clicked.connect(on_select)
            layout.addWidget(select_btn)

        remove_btn = OutlineButton("✕")
        remove_btn.setFixedSize(32, 30)
        if on_remove:
            remove_btn.clicked.connect(on_remove)
        layout.addWidget(remove_btn)


# ---------------------------------------------------------------------------
# Accounts Tab
# ---------------------------------------------------------------------------

class AccountsTab(QWidget):
    """Accounts management tab with live auth state."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._offline_accounts: list[str] = list(config.get("offline_accounts", []))
        self._build_ui()
        self._refresh_state()

    def _build_ui(self) -> None:
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(40, 28, 40, 28)
        self._root.setSpacing(20)

        # Page header
        title = QLabel("Accounts")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        self._root.addWidget(title)
        sub = QLabel("Sign in with Microsoft for online play, or add an offline account for solo play.")
        sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']}; margin-top: -12px;")
        self._root.addWidget(sub)

        # Microsoft login card
        self._ms_card = self._build_ms_card()
        self._root.addWidget(self._ms_card)

        # Offline account row
        offline_row = QHBoxLayout()
        offline_lbl = QLabel("Or add an offline account:")
        offline_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        offline_row.addWidget(offline_lbl)
        offline_row.addStretch()
        add_offline = OutlineButton("+ Add Offline Account")
        add_offline.setFixedHeight(34)
        add_offline.clicked.connect(self._add_offline)
        offline_row.addWidget(add_offline)
        self._root.addLayout(offline_row)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {C['border']}; border: none;")
        self._root.addWidget(div)

        # Accounts list title
        self._root.addWidget(_lbl("Your Accounts", FONT["lg"], C["text_primary"], bold=True))

        # Dynamic accounts area
        self._accounts_container = QWidget()
        self._accounts_layout = QVBoxLayout(self._accounts_container)
        self._accounts_layout.setContentsMargins(0, 0, 0, 0)
        self._accounts_layout.setSpacing(10)
        self._root.addWidget(self._accounts_container)

        self._root.addStretch()

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
        self._root.addWidget(note)

    def _build_ms_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("MsCard")
        card.setFixedHeight(96)
        card.setStyleSheet(f"""
            #MsCard {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 12px;
            }}
        """)
        ms_h = QHBoxLayout(card)
        ms_h.setContentsMargins(20, 0, 20, 0)
        ms_h.setSpacing(18)

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
        self._ms_title = QLabel("Sign in with Microsoft")
        self._ms_title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        text_col.addWidget(self._ms_title)
        self._ms_sub = QLabel("Required for online multiplayer. Links your Xbox / Minecraft account.")
        self._ms_sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        text_col.addWidget(self._ms_sub)
        ms_h.addLayout(text_col)
        ms_h.addStretch()

        self._ms_btn = PrimaryButton("Sign In")
        self._ms_btn.setFixedSize(110, 38)
        self._ms_btn.clicked.connect(self._on_ms_action)
        ms_h.addWidget(self._ms_btn)

        return card

    # ------------------------------------------------------------------
    # State refresh
    # ------------------------------------------------------------------

    def _refresh_state(self) -> None:
        # Update Microsoft card
        if auth_manager.is_logged_in:
            self._ms_title.setText(f"Signed in as {auth_manager.username}")
            self._ms_sub.setText("Microsoft account linked · Minecraft online play enabled")
            self._ms_btn.setText("Sign Out")
        else:
            self._ms_title.setText("Sign in with Microsoft")
            self._ms_sub.setText("Required for online multiplayer. Links your Xbox / Minecraft account.")
            self._ms_btn.setText("Sign In")

        # Rebuild accounts list
        while self._accounts_layout.count():
            item = self._accounts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        active = config.get("last_account", "")

        if auth_manager.is_logged_in:
            row = AccountRow(
                auth_manager.username,
                "Microsoft · Online",
                is_active=(active == auth_manager.username or not active),
                on_select=lambda: self._select_account(auth_manager.username),
                on_remove=self._logout_ms,
            )
            self._accounts_layout.addWidget(row)

        for name in self._offline_accounts:
            row = AccountRow(
                name,
                "Offline · Unverified",
                is_active=(name == active and not auth_manager.is_logged_in),
                on_select=lambda n=name: self._select_account(n),
                on_remove=lambda n=name: self._remove_offline(n),
            )
            self._accounts_layout.addWidget(row)

        if not auth_manager.is_logged_in and not self._offline_accounts:
            empty = _lbl("No accounts added yet.", FONT["sm"], C["text_tertiary"])
            empty.setAlignment(Qt.AlignCenter)
            self._accounts_layout.addWidget(empty)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_ms_action(self) -> None:
        if auth_manager.is_logged_in:
            self._logout_ms()
        else:
            self._open_login_dialog()

    def _open_login_dialog(self) -> None:
        dlg = LoginDialog(self)
        dlg.login_succeeded.connect(self._on_login_success)
        dlg.exec()

    def _on_login_success(self, account: dict) -> None:
        config.update({"last_account": account.get("name", "")})
        self._refresh_state()

    def _logout_ms(self) -> None:
        reply = QMessageBox.question(
            self,
            "Sign Out",
            f"Sign out of {auth_manager.username}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            auth_manager.logout()
            config.update({"last_account": ""})
            self._refresh_state()

    def _add_offline(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Offline Account", "Username:")
        name = name.strip()
        if ok and name and name not in self._offline_accounts:
            self._offline_accounts.append(name)
            config.update({"offline_accounts": self._offline_accounts})
            self._refresh_state()

    def _select_account(self, name: str) -> None:
        config.update({"last_account": name})
        self._refresh_state()

    def _remove_offline(self, name: str) -> None:
        if name in self._offline_accounts:
            self._offline_accounts.remove(name)
            config.update({"offline_accounts": self._offline_accounts})
            if config.get("last_account") == name:
                config.update({"last_account": ""})
            self._refresh_state()


def _lbl(text: str, size: str, color: str, bold: bool = False) -> QLabel:
    w = QLabel(text)
    weight = "700" if bold else "400"
    w.setStyleSheet(f"font-size: {size}; font-weight: {weight}; color: {color};")
    return w
