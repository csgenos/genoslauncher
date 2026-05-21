"""
Microsoft Login Dialog — device code flow.

States:
  idle        → "Sign In" button
  requesting  → fetching device code from Microsoft
  code_shown  → displays user_code + countdown + "Open Browser" button, polling in background
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
    Device-code sign-in dialog.

    Signals:
        login_succeeded(account_dict)
    """

    login_succeeded = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign in with Microsoft")
        self.setModal(True)
        self.setFixedSize(460, 400)
        self.setStyleSheet(f"""
            QDialog {{
                background: {C["bg_primary"]};
            }}
            QLabel {{ background: transparent; }}
        """)

        self._verification_uri = "https://microsoft.com/devicelogin"
        self._expires_in = 0
        self._remaining = 0
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick_countdown)

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

        # Large code display (only visible in code_shown state)
        self._code_box = QFrame()
        self._code_box.setObjectName("CodeBox")
        self._code_box.setStyleSheet(f"""
            #CodeBox {{
                background: {C["bg_primary"]};
                border: 2px solid {C["border_focus"]};
                border-radius: 10px;
            }}
        """)
        code_box_l = QVBoxLayout(self._code_box)
        code_box_l.setContentsMargins(0, 14, 0, 14)
        self._code_label = QLabel()
        self._code_label.setAlignment(Qt.AlignCenter)
        self._code_label.setStyleSheet(
            "font-family: 'Courier New', monospace; "
            "font-size: 32px; "
            "font-weight: 800; "
            "letter-spacing: 6px; "
            f"color: {C['text_primary']};"
        )
        code_box_l.addWidget(self._code_label)
        self._code_box.setVisible(False)
        card_l.addWidget(self._code_box)

        self._state_body = QLabel()
        self._state_body.setAlignment(Qt.AlignCenter)
        self._state_body.setWordWrap(True)
        self._state_body.setStyleSheet(
            f"font-size: {FONT['sm']}; color: {C['text_secondary']}; line-height: 1.5;"
        )
        card_l.addWidget(self._state_body)

        self._countdown_label = QLabel()
        self._countdown_label.setAlignment(Qt.AlignCenter)
        self._countdown_label.setStyleSheet(
            f"font-size: {FONT['xs']}; color: {C['text_tertiary']};"
        )
        self._countdown_label.setVisible(False)
        card_l.addWidget(self._countdown_label)

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
        self._countdown_timer.stop()
        self._code_box.setVisible(False)
        self._countdown_label.setVisible(False)
        self._cancel_btn.setVisible(True)

        if state == "idle":
            self._state_icon.setText("🔐")
            self._state_title.setText("Connect your Microsoft account")
            self._state_body.setText(
                "We'll show you a short code to enter at\n"
                "microsoft.com/devicelogin — no passwords typed here."
            )
            self._primary_btn.setText("Sign In")
            self._primary_btn.setEnabled(True)

        elif state == "requesting":
            self._state_icon.setText("⏳")
            self._state_title.setText("Connecting to Microsoft…")
            self._state_body.setText("Requesting sign-in code…")
            self._primary_btn.setText("Please wait…")
            self._primary_btn.setEnabled(False)

        elif state == "code_shown":
            self._state_icon.setText("")
            self._state_title.setText("Enter this code at:")
            self._state_body.setText("microsoft.com/devicelogin")
            self._state_body.setStyleSheet(
                f"font-size: {FONT['md']}; font-weight: 700; "
                f"color: {C['accent_blue']};"
            )
            self._code_box.setVisible(True)
            self._countdown_label.setVisible(True)
            self._countdown_label.setText(f"Code expires in {self._remaining // 60}:{self._remaining % 60:02d}")
            self._countdown_timer.start()
            self._primary_btn.setText("Open Browser")
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

    def _tick_countdown(self) -> None:
        self._remaining = max(0, self._remaining - 1)
        m, s = divmod(self._remaining, 60)
        self._countdown_label.setText(f"Code expires in {m}:{s:02d}")
        if self._remaining == 0:
            self._countdown_timer.stop()
            self._set_state("error", "Sign-in code expired. Please try again.")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_primary(self) -> None:
        if self._state in ("idle", "error"):
            self._start_login()
        elif self._state == "code_shown":
            webbrowser.open(self._verification_uri)
        elif self._state == "success":
            self.accept()

    def _on_cancel(self) -> None:
        self._countdown_timer.stop()
        auth_manager.cancel_login()
        self.reject()

    def _start_login(self) -> None:
        self._set_state("requesting")
        auth_manager.start_login(
            on_code_ready=self._on_code_ready,
            on_success=self._on_success,
            on_error=self._on_error,
        )

    # ------------------------------------------------------------------
    # Auth callbacks (called from background thread → hop to main thread)
    # ------------------------------------------------------------------

    def _on_code_ready(self, user_code: str, verification_uri: str, expires_in: int) -> None:
        self._verification_uri = verification_uri
        self._remaining = expires_in
        QTimer.singleShot(0, lambda: self._apply_code(user_code, verification_uri))

    def _apply_code(self, user_code: str, verification_uri: str) -> None:
        self._code_label.setText(user_code)
        self._set_state("code_shown")
        webbrowser.open(verification_uri)

    def _on_success(self, account: dict) -> None:
        name = account.get("name", "Unknown")
        QTimer.singleShot(0, lambda: self._apply_success(name, account))

    def _apply_success(self, name: str, account: dict) -> None:
        self._countdown_timer.stop()
        self._set_state("success", name)
        self.login_succeeded.emit(account)

    def _on_error(self, message: str) -> None:
        QTimer.singleShot(0, lambda: self._set_state("error", message))
