"""
GenosLauncher — First-run setup wizard.

580×500 frameless QDialog, three steps:
  1. Welcome
  2. Account setup  (Microsoft PKCE browser flow OR offline username)
  3. Ready summary  (auto-detected RAM + Java, applies config on accept)

Thread safety: all callbacks from auth_manager arrive on a background thread.
  → Always re-dispatch to the Qt main thread via run_on_ui_thread(...).
"""

from __future__ import annotations

import ctypes
import os
import platform
import re
import sys
import webbrowser
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.auth import auth_manager
from src.core.config import config
from src.core.java_manager import find_java_installations
from src.core.validators import normalize_offline_username
from src.ui.styles import C, FONT
from src.ui.qt_dispatch import run_on_ui_thread


def _asset(name: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_icon_box(size: int, bg: str = C["accent"], letter: str = "G") -> QLabel:
    """Return a QLabel rendered as a rounded-square icon."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(bg))
    painter.setPen(Qt.NoPen)
    radius = max(6, size // 5)
    painter.drawRoundedRect(0, 0, size, size, radius, radius)
    painter.setPen(QColor(C["text_inverse"]))
    font = QFont("Segoe UI", max(1, int(size * 0.52)), QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignCenter, letter)
    painter.end()

    label = QLabel()
    label.setPixmap(pix)
    label.setFixedSize(size, size)
    label.setStyleSheet("background: transparent;")
    return label


def _detect_total_ram_mb() -> int:
    """Return total system RAM in MB, cross-platform, no extra deps."""
    system = platform.system()
    try:
        if system == "Windows":
            class _MEMSTATUS(ctypes.Structure):
                _fields_ = [
                    ("dwLength",                ctypes.c_ulong),
                    ("dwMemoryLoad",            ctypes.c_ulong),
                    ("ullTotalPhys",            ctypes.c_ulonglong),
                    ("ullAvailPhys",            ctypes.c_ulonglong),
                    ("ullTotalPageFile",        ctypes.c_ulonglong),
                    ("ullAvailPageFile",        ctypes.c_ulonglong),
                    ("ullTotalVirtual",         ctypes.c_ulonglong),
                    ("ullAvailVirtual",         ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            status = _MEMSTATUS()
            status.dwLength = ctypes.sizeof(_MEMSTATUS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))  # type: ignore[attr-defined]
            return int(status.ullTotalPhys // (1024 * 1024))
        elif system == "Linux":
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb // 1024
        elif system == "Darwin":
            import subprocess
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"], text=True, timeout=3
            )
            return int(out.strip()) // (1024 * 1024)
    except Exception:
        pass
    return 8192  # fallback


def _recommended_ram(total_mb: int) -> int:
    """Return recommended RAM allocation in MB."""
    raw = min(total_mb // 2, 8192)
    return max(2048, min(raw, 8192))


# ---------------------------------------------------------------------------
# Step dot indicator
# ---------------------------------------------------------------------------

class _StepDots(QWidget):
    """Three dots showing which wizard step is active."""

    def __init__(self, count: int = 3, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._count = count
        self._active = 0
        self.setFixedHeight(16)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.setAlignment(Qt.AlignCenter)

        self._dots: list[QLabel] = []
        for _ in range(count):
            dot = QLabel()
            dot.setFixedSize(8, 8)
            self._dots.append(dot)
            self._layout.addWidget(dot)

        self._refresh()

    def set_step(self, index: int) -> None:
        self._active = index
        self._refresh()

    def _refresh(self) -> None:
        for i, dot in enumerate(self._dots):
            if i == self._active:
                dot.setStyleSheet(
                    f"background-color: {C['accent']}; border-radius: 4px;"
                )
            else:
                dot.setStyleSheet(
                    f"background-color: {C['border_strong']}; border-radius: 4px;"
                )


# ---------------------------------------------------------------------------
# Step 1 — Welcome
# ---------------------------------------------------------------------------

class _WelcomePage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(56, 32, 56, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        # Logo
        logo_path = _asset("glauncherlogo.png")
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent;")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(pix)
            icon_label.setFixedSize(72, 72)
        else:
            icon_label = _make_icon_box(56)
        icon_row = QHBoxLayout()
        icon_row.setAlignment(Qt.AlignCenter)
        icon_row.addWidget(icon_label)
        layout.addLayout(icon_row)
        layout.addSpacing(24)

        # Heading
        heading = QLabel("Welcome to GenosLauncher")
        heading.setAlignment(Qt.AlignCenter)
        heading.setWordWrap(True)
        heading.setStyleSheet(
            f"color: {C['text_primary']};"
            f"font-size: {FONT['2xl']};"
            "font-weight: 700;"
            "letter-spacing: -0.3px;"
        )
        layout.addWidget(heading)
        layout.addSpacing(12)

        # Subtitle
        subtitle = QLabel("The open-source Minecraft launcher built for everyone.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color: {C['text_secondary']};"
            f"font-size: {FONT['sm']};"
        )
        layout.addWidget(subtitle)
        layout.addStretch()


# ---------------------------------------------------------------------------
# Step 2 — Account
# ---------------------------------------------------------------------------

class _AccountPage(QWidget):
    """
    Manages the account setup sub-states:
      "choose"         → two clickable option cards
      "ms_requesting"  → connecting spinner text
      "ms_code"        → device code display + countdown
      "ms_success"     → green tick + name
      "offline"        → username input
    """

    account_ready = Signal()   # emitted when account is configured

    # Internal sub-state names
    _STATE_CHOOSE       = "choose"
    _STATE_MS_REQ       = "ms_requesting"
    _STATE_MS_WAITING   = "ms_waiting"
    _STATE_MS_SUCCESS   = "ms_success"
    _STATE_OFFLINE      = "offline"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        self._account_info: dict = {}
        self._auth_url: str = ""

        self._stack = QStackedWidget(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._stack)

        # Build all sub-pages
        self._page_choose      = self._build_choose_page()
        self._page_ms_req      = self._build_ms_requesting_page()
        self._page_ms_waiting  = self._build_ms_waiting_page()
        self._page_ms_success  = self._build_ms_success_page()
        self._page_offline     = self._build_offline_page()

        for page in (
            self._page_choose,
            self._page_ms_req,
            self._page_ms_waiting,
            self._page_ms_success,
            self._page_offline,
        ):
            self._stack.addWidget(page)

        self._show_state(self._STATE_CHOOSE)

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _show_state(self, state: str) -> None:
        mapping = {
            self._STATE_CHOOSE:     self._page_choose,
            self._STATE_MS_REQ:     self._page_ms_req,
            self._STATE_MS_WAITING: self._page_ms_waiting,
            self._STATE_MS_SUCCESS: self._page_ms_success,
            self._STATE_OFFLINE:    self._page_offline,
        }
        page = mapping.get(state)
        if page is not None:
            self._stack.setCurrentWidget(page)

    def reset_to_choose(self) -> None:
        """Cancel any in-progress login and return to the choose screen."""
        auth_manager.cancel_login()
        self._auth_url = ""
        self._account_info = {}
        self._choose_error.setText("")
        self._show_state(self._STATE_CHOOSE)

    @property
    def account_info(self) -> dict:
        return self._account_info

    # ------------------------------------------------------------------
    # Sub-page builders
    # ------------------------------------------------------------------

    def _build_choose_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 24, 48, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignTop)

        title = QLabel("How do you want to play?")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {C['text_primary']};"
            f"font-size: {FONT['xl']};"
            "font-weight: 700;"
        )
        layout.addWidget(title)
        layout.addSpacing(8)

        sub = QLabel("You can always change this later in Settings.")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(
            f"color: {C['text_secondary']};"
            f"font-size: {FONT['sm']};"
        )
        layout.addWidget(sub)
        self._choose_error = QLabel("")
        self._choose_error.setAlignment(Qt.AlignCenter)
        self._choose_error.setWordWrap(True)
        self._choose_error.setStyleSheet(f"color: {C['danger']}; font-size: {FONT['sm']};")
        layout.addWidget(self._choose_error)
        layout.addSpacing(20)

        # Microsoft card
        ms_card = self._option_card(
            bg_letter="#0078D4",
            letter="M",
            title="Sign in with Microsoft",
            description="Recommended for online play",
        )
        ms_card.mousePressEvent = lambda _e: self._on_ms_clicked()
        layout.addWidget(ms_card)
        layout.addSpacing(10)

        # Offline card
        offline_card = self._option_card(
            bg_letter=C["text_secondary"],
            letter="?",
            title="Play Offline",
            description="Pick a username to get started",
        )
        offline_card.mousePressEvent = lambda _e: self._on_offline_clicked()
        layout.addWidget(offline_card)
        layout.addStretch()
        return page

    @staticmethod
    def _option_card(
        bg_letter: str,
        letter: str,
        title: str,
        description: str,
    ) -> QFrame:
        card = QFrame()
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {C['bg_primary']};
                border: 1.5px solid {C['border']};
                border-radius: 10px;
                padding: 2px;
            }}
            QFrame:hover {{
                border-color: {C['accent_blue']};
                background-color: {C['accent_blue_soft']};
            }}
            """
        )

        row = QHBoxLayout(card)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(14)

        # Icon box
        icon = _make_icon_box(36, bg=bg_letter, letter=letter)
        row.addWidget(icon)

        # Text block
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        t_label = QLabel(title)
        t_label.setStyleSheet(
            f"color: {C['text_primary']};"
            "font-size: 13px;"
            "font-weight: 600;"
            "background: transparent;"
        )
        d_label = QLabel(description)
        d_label.setStyleSheet(
            f"color: {C['text_secondary']};"
            f"font-size: {FONT['sm']};"
            "background: transparent;"
        )
        text_col.addWidget(t_label)
        text_col.addWidget(d_label)
        row.addLayout(text_col)
        row.addStretch()

        # Chevron
        arrow = QLabel("›")
        arrow.setStyleSheet(
            f"color: {C['text_tertiary']};"
            "font-size: 20px;"
            "background: transparent;"
        )
        row.addWidget(arrow)
        return card

    def _build_ms_requesting_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setAlignment(Qt.AlignCenter)

        lbl = QLabel("Connecting to Microsoft…")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f"color: {C['text_secondary']};"
            f"font-size: {FONT['md']};"
        )
        layout.addWidget(lbl)
        return page

    def _build_ms_waiting_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 30, 48, 30)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        instr = QLabel("Complete sign-in in your browser")
        instr.setAlignment(Qt.AlignCenter)
        instr.setStyleSheet(
            f"color: {C['text_primary']};"
            f"font-size: {FONT['md']};"
            "font-weight: 600;"
        )
        layout.addWidget(instr)
        layout.addSpacing(8)

        sub = QLabel("Once you finish, this screen will update automatically.")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"color: {C['text_secondary']};"
            f"font-size: {FONT['sm']};"
        )
        layout.addWidget(sub)
        layout.addSpacing(20)

        # Reopen Browser button
        reopen_btn = QPushButton("Reopen Browser")
        reopen_btn.setCursor(Qt.PointingHandCursor)
        reopen_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {C['text_primary']};
                border: 1px solid {C['border_strong']};
                border-radius: 8px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 500;
                min-height: 36px;
            }}
            QPushButton:hover {{
                background-color: {C['bg_hover']};
            }}
            QPushButton:pressed {{
                background-color: {C['bg_pressed']};
            }}
            """
        )
        reopen_btn.clicked.connect(self._reopen_browser)
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)
        btn_row.addWidget(reopen_btn)
        layout.addLayout(btn_row)
        layout.addSpacing(16)

        # Back link
        back_link = QLabel('<a href="#" style="color: {c}; text-decoration: none;">← Use a different account</a>'.format(c=C["text_secondary"]))
        back_link.setAlignment(Qt.AlignCenter)
        back_link.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        back_link.linkActivated.connect(lambda _: self.reset_to_choose())
        layout.addWidget(back_link)
        layout.addStretch()
        return page

    def _build_ms_success_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        self._success_name_lbl = QLabel("")
        self._success_name_lbl.setAlignment(Qt.AlignCenter)
        self._success_name_lbl.setStyleSheet(
            f"color: {C['text_primary']};"
            f"font-size: {FONT['lg']};"
            "font-weight: 600;"
        )
        layout.addWidget(self._success_name_lbl)
        layout.addSpacing(6)

        badge = QLabel("Microsoft Account")
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            "color: #0078D4;"
            f"font-size: {FONT['sm']};"
            "font-weight: 600;"
            "background-color: #E8F4FE;"
            "border-radius: 6px;"
            "padding: 3px 10px;"
        )
        layout.addWidget(badge)
        return page

    def _build_offline_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 24, 48, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignTop)

        title = QLabel("Choose a username")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {C['text_primary']};"
            f"font-size: {FONT['xl']};"
            "font-weight: 700;"
        )
        layout.addWidget(title)
        layout.addSpacing(6)

        sub = QLabel("Use letters, numbers and underscores. Max 16 characters.")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"color: {C['text_secondary']};"
            f"font-size: {FONT['sm']};"
        )
        layout.addWidget(sub)
        layout.addSpacing(20)

        self._username_input = QLineEdit()
        self._username_input.setPlaceholderText("Username")
        self._username_input.setMaxLength(16)
        self._username_input.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: {C['bg_input']};
                color: {C['text_primary']};
                border: 1.5px solid {C['border']};
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 14px;
                min-height: 38px;
            }}
            QLineEdit:focus {{
                border-color: {C['border_focus']};
                background-color: {C['bg_primary']};
            }}
            """
        )
        self._username_input.textChanged.connect(self._on_username_changed)
        layout.addWidget(self._username_input)
        layout.addSpacing(8)

        self._username_hint = QLabel("")
        self._username_hint.setStyleSheet(
            f"color: {C['text_tertiary']};"
            f"font-size: {FONT['sm']};"
        )
        layout.addWidget(self._username_hint)

        layout.addSpacing(12)
        back_link = QLabel('<a href="#" style="color: {c}; text-decoration: none;">← Back to options</a>'.format(c=C["text_secondary"]))
        back_link.setAlignment(Qt.AlignLeft)
        back_link.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        back_link.linkActivated.connect(lambda _: self.reset_to_choose())
        layout.addWidget(back_link)
        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_ms_clicked(self) -> None:
        self._account_info = {}
        self._auth_url = ""
        self._choose_error.setText("")
        self._show_state(self._STATE_MS_REQ)
        auth_manager.start_login(
            on_browser_opened=self._cb_browser_opened,
            on_success=self._cb_success,
            on_error=self._cb_error,
        )

    def _on_offline_clicked(self) -> None:
        self._account_info = {}
        self._choose_error.setText("")
        self._username_input.clear()
        self._username_hint.setText("")
        self._show_state(self._STATE_OFFLINE)

    def _on_username_changed(self, text: str) -> None:
        # Validate: alphanumeric + underscore only
        clean = re.sub(r"[^a-zA-Z0-9_]", "", text)
        if clean != text:
            self._username_input.setText(clean)
            return

        if clean and normalize_offline_username(clean):
            self._account_info = {"name": clean, "type": "offline"}
            self._username_hint.setText(f"Playing as: {clean}")
            self.account_ready.emit()
        elif clean:
            self._account_info = {}
            self._username_hint.setText("Use 3-16 letters, numbers, or underscores.")
        else:
            self._account_info = {}
            self._username_hint.setText("")

    def _reopen_browser(self) -> None:
        if self._auth_url:
            webbrowser.open(self._auth_url)

    # ------------------------------------------------------------------
    # Auth callbacks (called from background thread — hop to main thread)
    # ------------------------------------------------------------------

    def _cb_browser_opened(self, auth_url: str) -> None:
        run_on_ui_thread(lambda: self._apply_browser_opened(auth_url))

    def _apply_browser_opened(self, auth_url: str) -> None:
        self._auth_url = auth_url
        self._show_state(self._STATE_MS_WAITING)

    def _cb_success(self, account: dict) -> None:
        run_on_ui_thread(lambda: self._on_success(account))

    def _cb_error(self, message: str) -> None:
        run_on_ui_thread(lambda: self._on_error(message))

    def _on_success(self, account: dict) -> None:
        name = account.get("name", "Unknown")
        self._account_info = {
            "name": name,
            "type": "microsoft",
            "uuid": account.get("id", ""),
        }
        self._success_name_lbl.setText(f"✓  Signed in as {name}")
        self._show_state(self._STATE_MS_SUCCESS)
        self.account_ready.emit()

    def _on_error(self, message: str) -> None:
        self._auth_url = ""
        self._account_info = {}
        self._choose_error.setText(message or "Microsoft sign-in failed.")
        self._show_state(self._STATE_CHOOSE)


# ---------------------------------------------------------------------------
# Step 3 — Ready
# ---------------------------------------------------------------------------

class _ReadyPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(48, 24, 48, 24)
        self._layout.setSpacing(0)
        self._layout.setAlignment(Qt.AlignTop)

        # Heading
        heading = QLabel("You're all set.")
        heading.setAlignment(Qt.AlignCenter)
        heading.setStyleSheet(
            f"color: {C['success']};"
            f"font-size: {FONT['2xl']};"
            "font-weight: 700;"
        )
        self._layout.addWidget(heading)
        self._layout.addSpacing(6)

        sub = QLabel("Everything is ready. Let's play.")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(
            f"color: {C['text_secondary']};"
            f"font-size: {FONT['sm']};"
        )
        self._layout.addWidget(sub)
        self._layout.addSpacing(20)

        # Summary card
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {C['bg_secondary']};"
            f"border: 1px solid {C['border']};"
            "border-radius: 10px;"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(10)

        self._account_row = self._info_row("Account", "Not configured")
        self._perf_row    = self._info_row("Performance", "Detecting…")
        card_layout.addLayout(self._account_row[0])
        card_layout.addLayout(self._perf_row[0])

        self._layout.addWidget(card)
        self._layout.addStretch()

        # Store references to value labels
        self._account_val: QLabel = self._account_row[1]
        self._perf_val: QLabel    = self._perf_row[1]

        # Detected values (set by refresh())
        self._ram_mb: int = 4096
        self._java_str: str = "auto-detect"

    @staticmethod
    def _info_row(label_text: str, value_text: str):
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(label_text)
        lbl.setStyleSheet(
            f"color: {C['text_tertiary']};"
            "font-size: 12px;"
            "font-weight: 600;"
            "text-transform: uppercase;"
            "letter-spacing: 0.5px;"
            "min-width: 110px;"
        )
        val = QLabel(value_text)
        val.setStyleSheet(
            f"color: {C['text_primary']};"
            "font-size: 13px;"
            "font-weight: 500;"
        )
        val.setWordWrap(True)
        row.addWidget(lbl, 0)
        row.addWidget(val, 1)
        return row, val

    def refresh(self, account_info: dict) -> None:
        """Populate the summary with current account info and auto-detected system data."""
        # Account row
        if account_info.get("name"):
            a_type = account_info.get("type", "offline")
            badge = "Microsoft" if a_type == "microsoft" else "Offline"
            self._account_val.setText(f"{account_info['name']}  [{badge}]")
        else:
            self._account_val.setText("Not configured")

        # Performance row — detect RAM + Java
        total_mb = _detect_total_ram_mb()
        self._ram_mb = _recommended_ram(total_mb)
        ram_gb = self._ram_mb / 1024

        try:
            installs = find_java_installations()
            if installs:
                best = max(installs, key=lambda j: j["major"])
                self._java_str = f"Java {best['major']}"
            else:
                self._java_str = "auto-detect"
        except Exception:
            self._java_str = "auto-detect"

        self._perf_val.setText(
            f"{ram_gb:.1f} GB RAM · {self._java_str} detected"
            if self._java_str != "auto-detect"
            else f"{ram_gb:.1f} GB RAM · Java: auto-detect"
        )

    @property
    def recommended_ram_mb(self) -> int:
        return self._ram_mb


# ---------------------------------------------------------------------------
# Main Wizard dialog
# ---------------------------------------------------------------------------

class SetupWizard(QDialog):
    """
    580×500 frameless three-step first-run wizard.

    Emits accepted() on successful completion; rejected() if the user
    closes the dialog without finishing.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(580, 500)
        self.setStyleSheet(
            f"QDialog {{ background-color: {C['bg_primary']}; border-radius: 14px; }}"
        )
        self._current_step = 0
        self._build_ui()
        self._center_on_screen()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar: close button + step dots ───────────────────────────
        top_bar = QWidget()
        top_bar.setStyleSheet("background: transparent;")
        top_bar.setFixedHeight(48)
        top_row = QHBoxLayout(top_bar)
        top_row.setContentsMargins(20, 12, 20, 8)
        top_row.setSpacing(0)

        # Logo mark in top-left to balance the X button
        logo_path = _asset("glauncherlogo.png")
        logo_lbl = QLabel()
        logo_lbl.setFixedSize(28, 28)
        logo_lbl.setStyleSheet("background: transparent;")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_lbl.setPixmap(pix)
        top_row.addWidget(logo_lbl)

        top_row.addStretch()

        self._dots = _StepDots(3)
        top_row.addWidget(self._dots)

        top_row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {C['text_tertiary']};
                border: none;
                border-radius: 14px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {C['bg_hover']};
                color: {C['text_secondary']};
            }}
            """
        )
        close_btn.clicked.connect(self.reject)
        top_row.addWidget(close_btn)

        root.addWidget(top_bar)

        # ── Thin separator ───────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background-color: {C['border']}; border: none; max-height: 1px;")
        root.addWidget(sep)

        # ── Stacked pages ────────────────────────────────────────────────
        self._pages = QStackedWidget()
        self._pages.setStyleSheet("background: transparent;")

        self._welcome_page = _WelcomePage()
        self._account_page = _AccountPage()
        self._ready_page   = _ReadyPage()

        self._pages.addWidget(self._welcome_page)
        self._pages.addWidget(self._account_page)
        self._pages.addWidget(self._ready_page)

        self._account_page.account_ready.connect(self._on_account_ready)

        root.addWidget(self._pages, stretch=1)

        # ── Bottom navigation bar ────────────────────────────────────────
        nav_bar = QWidget()
        nav_bar.setStyleSheet(
            f"background-color: {C['bg_secondary']};"
            f"border-top: 1px solid {C['border']};"
        )
        nav_bar.setFixedHeight(68)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(24, 14, 24, 14)
        nav_layout.setSpacing(10)

        self._back_btn = QPushButton("← Back")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.setFixedHeight(40)
        self._back_btn.setMinimumWidth(100)
        self._back_btn.setStyleSheet(self._outline_btn_style())
        self._back_btn.clicked.connect(self._go_back)

        self._next_btn = QPushButton("Get Started →")
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setFixedHeight(40)
        self._next_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._next_btn.setStyleSheet(self._primary_btn_style())
        self._next_btn.clicked.connect(self._go_next)

        nav_layout.addWidget(self._back_btn)
        nav_layout.addWidget(self._next_btn, stretch=1)
        root.addWidget(nav_bar)

        self._update_nav()

    @staticmethod
    def _primary_btn_style() -> str:
        return f"""
            QPushButton {{
                background-color: {C['accent']};
                color: {C['text_inverse']};
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #1F2937;
            }}
            QPushButton:pressed {{
                background-color: #0F172A;
            }}
            QPushButton:disabled {{
                background-color: {C['text_disabled']};
                color: {C['text_inverse']};
            }}
        """

    @staticmethod
    def _outline_btn_style() -> str:
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {C['text_primary']};
                border: 1px solid {C['border_strong']};
                border-radius: 8px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {C['bg_hover']};
            }}
            QPushButton:pressed {{
                background-color: {C['bg_pressed']};
            }}
        """

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _update_nav(self) -> None:
        step = self._current_step
        self._dots.set_step(step)
        self._pages.setCurrentIndex(step)

        if step == 0:
            # Welcome — no Back, full-width primary
            self._back_btn.hide()
            self._next_btn.setText("Get Started  →")
            self._next_btn.setEnabled(True)

        elif step == 1:
            # Account — show Back; Continue enabled only when account ready
            self._back_btn.show()
            self._next_btn.setText("Continue  →")
            has_account = bool(self._account_page.account_info.get("name"))
            self._next_btn.setEnabled(has_account)

        else:
            # Ready — no Back, full-width launch button
            self._back_btn.hide()
            self._next_btn.setText("Launch GenosLauncher  →")
            self._next_btn.setEnabled(True)
            # Populate the summary
            self._ready_page.refresh(self._account_page.account_info)

    def _go_next(self) -> None:
        if self._current_step == 2:
            self._apply_and_accept()
            return
        self._current_step = min(self._current_step + 1, 2)
        self._update_nav()

    def _go_back(self) -> None:
        self._current_step = max(self._current_step - 1, 0)
        self._update_nav()

    def _on_account_ready(self) -> None:
        if self._current_step == 1:
            self._next_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Accept / apply config
    # ------------------------------------------------------------------

    def _apply_and_accept(self) -> None:
        ram = self._ready_page.recommended_ram_mb
        updates: dict = {"ram_mb": ram, "first_run": False}

        account = self._account_page.account_info
        if account.get("type") == "offline" and account.get("name"):
            name = account["name"]
            existing: list = config.get("offline_accounts", [])
            if name not in existing:
                existing.insert(0, name)
            updates["offline_accounts"] = existing
            updates["last_account"] = name
        elif account.get("type") == "microsoft" and account.get("name"):
            updates["last_account"] = account["name"]
        # Microsoft account is already stored in the keyring by auth_manager.

        config.update(updates)
        self.accept()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
