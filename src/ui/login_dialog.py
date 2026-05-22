"""
Microsoft Login Dialog — PKCE browser flow.

States:
  idle        → "Sign In" button
  requesting  → finding a free port, building the auth URL
  waiting     → browser is open, waiting for the user to complete sign-in
  success     → welcome message
  error       → error message + retry
"""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .styles import COLORS as C, FONT
from .components.animated_button import OutlineButton, PrimaryButton
from ..core.auth import auth_manager


class LoginDialog(QDialog):
    """
    PKCE browser sign-in dialog.

    Signals:
        login_succeeded(account_dict)
    """

    login_succeeded = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign in with Microsoft")
        self.setModal(True)
        self.setFixedSize(460, 340)
        self.setStyleSheet(f"""
            QDialog {{
                background: {C["bg_primary"]};
            }}
            QLabel {{ background: transparent; }}
        """)

        self._auth_url: str = ""

        self._build_ui()
        self._set_state("idle")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 28)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────
        header = QHBoxLayout()
        m_icon = QLabel("M")
        m_icon.setFixedSize(44, 44)
        m_icon.setAlignment(Qt.AlignCenter)
        m_icon.setStyleSheet("""
            background: #0078D4;
            color: white;
            border-radius: 8px;
            font-size: 20px;
            font-weight: 900;
        """)
        header.addWidget(m_icon)
        header.addSpacing(14)

        hdr_col = QVBoxLayout()
        hdr_col.setSpacing(2)
        t = QLabel("Sign in with Microsoft")
        t.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        hdr_col.addWidget(t)
        sub = QLabel("Required for online multiplayer")
        sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        hdr_col.addWidget(sub)
        header.addLayout(hdr_col)
        header.addStretch()
        root.addLayout(header)
        root.addSpacing(24)

        # ── State card ────────────────────────────────────────────────
        self._card = QFrame()
        self._card.setObjectName("LoginCard")
        self._card.setStyleSheet(f"""
            #LoginCard {{
                background: {C["bg_secondary"]};
                border: 1px solid {C["border"]};
                border-radius: 12px;
            }}
        """)
        card_l = QVBoxLayout(self._card)
        card_l.setContentsMargins(24, 22, 24, 22)
        card_l.setSpacing(10)

        self._state_icon = QLabel()
        self._state_icon.setAlignment(Qt.AlignCenter)
        self._state_icon.setStyleSheet("font-size: 30px;")
        card_l.addWidget(self._state_icon)

        self._state_title = QLabel()
        self._state_title.setAlignment(Qt.AlignCenter)
        self._state_title.setStyleSheet(
            f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};"
        )
        card_l.addWidget(self._state_title)

        self._state_body = QLabel()
        self._state_body.setAlignment(Qt.AlignCenter)
        self._state_body.setWordWrap(True)
        self._state_body.setStyleSheet(
            f"font-size: {FONT['sm']}; color: {C['text_secondary']}; line-height: 1.5;"
        )
        card_l.addWidget(self._state_body)

        root.addWidget(self._card)
        root.addSpacing(20)
        root.addStretch()

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._cancel_btn = OutlineButton("Cancel")
        self._cancel_btn.setFixedHeight(40)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._cancel_btn)

        self._primary_btn = PrimaryButton("Sign In")
        self._primary_btn.setFixedHeight(40)
        self._primary_btn.clicked.connect(self._on_primary)
        btn_row.addWidget(self._primary_btn, 1)

        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _set_state(self, state: str, extra: str = "") -> None:
        self._state = state
        self._cancel_btn.setVisible(True)

        if state == "idle":
            self._state_icon.setText("🔐")
            self._state_title.setText("Connect your Microsoft account")
            self._state_body.setText(
                "Click Sign In to open Microsoft's login page in your browser.\n"
                "No passwords are entered here."
            )
            self._state_body.setStyleSheet(
                f"font-size: {FONT['sm']}; color: {C['text_secondary']};"
            )
            self._primary_btn.setText("Sign In")
            self._primary_btn.setEnabled(True)

        elif state == "requesting":
            self._state_icon.setText("⏳")
            self._state_title.setText("Opening your browser…")
            self._state_body.setText("Preparing sign-in…")
            self._state_body.setStyleSheet(
                f"font-size: {FONT['sm']}; color: {C['text_secondary']};"
            )
            self._primary_btn.setText("Please wait…")
            self._primary_btn.setEnabled(False)

        elif state == "waiting":
            self._state_icon.setText("🌐")
            self._state_title.setText("Complete sign-in in your browser")
            self._state_body.setText(
                "Your browser should have opened automatically.\n"
                "Once you finish signing in, this dialog will update."
            )
            self._state_body.setStyleSheet(
                f"font-size: {FONT['sm']}; color: {C['text_secondary']};"
            )
            self._primary_btn.setText("Reopen Browser")
            self._primary_btn.setEnabled(True)

        elif state == "success":
            self._state_icon.setText("✅")
            self._state_title.setText(f"Welcome, {extra}!")
            self._state_body.setText("Your Microsoft account is linked.")
            self._state_body.setStyleSheet(
                f"font-size: {FONT['sm']}; color: {C['text_secondary']};"
            )
            self._primary_btn.setText("Done")
            self._primary_btn.setEnabled(True)
            self._cancel_btn.setVisible(False)

        elif state == "error":
            self._state_icon.setText("⚠️")
            self._state_title.setText("Sign-in failed")
            self._state_body.setText(extra or "An unknown error occurred.")
            self._state_body.setStyleSheet(
                f"font-size: {FONT['sm']}; color: {C['text_secondary']};"
            )
            self._primary_btn.setText("Try Again")
            self._primary_btn.setEnabled(True)
            self._cancel_btn.setVisible(True)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_primary(self) -> None:
        if self._state in ("idle", "error"):
            self._start_login()
        elif self._state == "waiting" and self._auth_url:
            webbrowser.open(self._auth_url)
        elif self._state == "success":
            self.accept()

    def _on_cancel(self) -> None:
        auth_manager.cancel_login()
        self.reject()

    def _start_login(self) -> None:
        self._auth_url = ""
        self._set_state("requesting")
        auth_manager.start_login(
            on_browser_opened=self._on_browser_opened,
            on_success=self._on_success,
            on_error=self._on_error,
        )

    # ------------------------------------------------------------------
    # Auth callbacks (called from background thread → hop to main thread)
    # ------------------------------------------------------------------

    def _on_browser_opened(self, auth_url: str) -> None:
        self._auth_url = auth_url
        QTimer.singleShot(0, lambda: self._set_state("waiting"))

    def _on_success(self, account: dict) -> None:
        name = account.get("name", "Unknown")
        QTimer.singleShot(0, lambda: self._apply_success(name, account))

    def _apply_success(self, name: str, account: dict) -> None:
        self._set_state("success", name)
        self.login_succeeded.emit(account)

    def _on_error(self, message: str) -> None:
        QTimer.singleShot(0, lambda: self._set_state("error", message))
