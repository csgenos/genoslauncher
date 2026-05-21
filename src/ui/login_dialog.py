"""
Microsoft Login Dialog — PKCE browser-based OAuth flow.

States:
  idle       → shows instructions + "Open Browser" button
  waiting    → shows spinner text + cancel button
  success    → shows username + "Done" button
  error      → shows error message + "Retry" button
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .styles import COLORS as C, FONT
from .components.animated_button import OutlineButton, PrimaryButton
from ..core.auth import auth_manager


class LoginDialog(QDialog):
    """
    Modal dialog for Microsoft account sign-in.

    Signals:
      login_succeeded(account_dict)  — emitted after successful login
    """

    login_succeeded = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign in with Microsoft")
        self.setModal(True)
        self.setFixedSize(480, 380)
        self.setStyleSheet(f"""
            QDialog {{
                background: {C["bg_primary"]};
                border-radius: 12px;
            }}
            QLabel {{ background: transparent; }}
        """)

        self._dot_count = 0
        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._tick_dots)

        self._build_ui()
        self._set_state("idle")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 36, 40, 32)
        root.setSpacing(0)

        # Header
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

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        t = QLabel("Sign in with Microsoft")
        t.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        title_col.addWidget(t)
        sub = QLabel("Required for online multiplayer")
        sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        title_col.addWidget(sub)
        header.addLayout(title_col)
        header.addStretch()
        root.addLayout(header)

        root.addSpacing(28)

        # State card
        self._card = QFrame()
        self._card.setObjectName("StateCard")
        self._card.setStyleSheet(f"""
            #StateCard {{
                background: {C["bg_secondary"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
            }}
        """)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(10)

        self._state_icon = QLabel("🔐")
        self._state_icon.setAlignment(Qt.AlignCenter)
        self._state_icon.setStyleSheet("font-size: 32px;")
        card_layout.addWidget(self._state_icon)

        self._state_title = QLabel()
        self._state_title.setAlignment(Qt.AlignCenter)
        self._state_title.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        card_layout.addWidget(self._state_title)

        self._state_body = QLabel()
        self._state_body.setAlignment(Qt.AlignCenter)
        self._state_body.setWordWrap(True)
        self._state_body.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']}; line-height: 1.5;")
        card_layout.addWidget(self._state_body)

        root.addWidget(self._card)

        root.addSpacing(24)

        # URL copy row (shown in waiting state)
        self._url_row = QWidget()
        url_h = QHBoxLayout(self._url_row)
        url_h.setContentsMargins(0, 0, 0, 0)
        url_h.setSpacing(8)
        url_lbl = QLabel("Browser didn't open?")
        url_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        url_h.addWidget(url_lbl)
        self._copy_btn = OutlineButton("Copy URL")
        self._copy_btn.setFixedHeight(28)
        self._copy_btn.clicked.connect(self._copy_url)
        url_h.addWidget(self._copy_btn)
        url_h.addStretch()
        self._url_row.setVisible(False)
        root.addWidget(self._url_row)

        root.addStretch()

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._cancel_btn = OutlineButton("Cancel")
        self._cancel_btn.setFixedHeight(40)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._cancel_btn)

        self._primary_btn = PrimaryButton("Open Browser")
        self._primary_btn.setFixedHeight(40)
        self._primary_btn.clicked.connect(self._on_primary)
        btn_row.addWidget(self._primary_btn, 1)

        root.addLayout(btn_row)

        self._login_url: str = ""

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _set_state(self, state: str, extra: str = "") -> None:
        self._state = state
        self._dot_timer.stop()

        if state == "idle":
            self._state_icon.setText("🔐")
            self._state_title.setText("Connect your Microsoft account")
            self._state_body.setText(
                'Clicking "Open Browser" will take you to the Microsoft login page. '
                "After signing in, return here automatically."
            )
            self._primary_btn.setText("Open Browser")
            self._primary_btn.setEnabled(True)
            self._cancel_btn.setText("Cancel")
            self._url_row.setVisible(False)

        elif state == "waiting":
            self._state_icon.setText("⏳")
            self._state_title.setText("Waiting for login")
            self._state_body.setText("Complete sign-in in your browser, then return here.")
            self._primary_btn.setText("Waiting…")
            self._primary_btn.setEnabled(False)
            self._cancel_btn.setText("Cancel")
            self._url_row.setVisible(True)
            self._dot_timer.start(500)

        elif state == "success":
            self._dot_timer.stop()
            self._state_icon.setText("✅")
            self._state_title.setText(f"Signed in as {extra}")
            self._state_body.setText("Your Microsoft account is now linked. You can close this window.")
            self._primary_btn.setText("Done")
            self._primary_btn.setEnabled(True)
            self._cancel_btn.setVisible(False)
            self._url_row.setVisible(False)

        elif state == "error":
            self._dot_timer.stop()
            self._state_icon.setText("⚠️")
            self._state_title.setText("Sign-in failed")
            self._state_body.setText(extra or "An unknown error occurred. Please try again.")
            self._primary_btn.setText("Try Again")
            self._primary_btn.setEnabled(True)
            self._cancel_btn.setText("Cancel")
            self._cancel_btn.setVisible(True)
            self._url_row.setVisible(False)

    def _tick_dots(self) -> None:
        self._dot_count = (self._dot_count + 1) % 4
        dots = "." * self._dot_count
        self._state_body.setText(
            f"Complete sign-in in your browser, then return here{dots}"
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_primary(self) -> None:
        if self._state == "idle" or self._state == "error":
            self._start_login()
        elif self._state == "success":
            self.accept()

    def _on_cancel(self) -> None:
        self._dot_timer.stop()
        self.reject()

    def _start_login(self) -> None:
        self._set_state("waiting")
        auth_manager.start_login(
            on_url_ready=self._on_url_ready,
            on_success=self._on_success,
            on_error=self._on_error,
            open_browser=True,
        )

    def _on_url_ready(self, url: str) -> None:
        self._login_url = url

    def _on_success(self, account: dict) -> None:
        # Called from background thread — use QTimer to hop to main thread
        name = account.get("name", "Unknown")
        QTimer.singleShot(0, lambda: self._apply_success(name, account))

    def _apply_success(self, name: str, account: dict) -> None:
        self._set_state("success", name)
        self.login_succeeded.emit(account)

    def _on_error(self, message: str) -> None:
        QTimer.singleShot(0, lambda: self._set_state("error", message))

    def _copy_url(self) -> None:
        if self._login_url:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self._login_url)
            self._copy_btn.setText("Copied!")
            QTimer.singleShot(2000, lambda: self._copy_btn.setText("Copy URL"))
