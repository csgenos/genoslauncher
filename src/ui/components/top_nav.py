"""Top navigation bar for the desktop-style GenosLauncher shell."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from ..styles import COLORS as C


class TopNavBar(QWidget):
    """Horizontal app navigation with compact account controls."""

    tab_changed = Signal(str)
    login_requested = Signal()
    logout_requested = Signal()

    NAV_ITEMS: list[tuple[str, str]] = [
        ("home", "Home"),
        ("instances", "Instances"),
        ("mods", "Mods"),
        ("modpacks", "Modpacks"),
        ("shaders", "Shaders"),
        ("servers", "Servers"),
        ("accounts", "Accounts"),
        ("settings", "Settings"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active_key = "home"
        self._logged_in = False
        self._buttons: dict[str, QPushButton] = {}
        self._button_order: list[str] = []
        self._build_ui()
        self.refresh_theme()
        self.set_active(self._active_key, emit=False)
        self.set_logged_out()

    def _build_ui(self) -> None:
        self.setObjectName("TopNavBar")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(10)

        outer.addStretch(1)

        self._tabs_frame = QFrame(self)
        self._tabs_frame.setObjectName("TopNavTabs")
        tabs_layout = QHBoxLayout(self._tabs_frame)
        tabs_layout.setContentsMargins(8, 6, 8, 6)
        tabs_layout.setSpacing(6)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_group.buttonClicked.connect(self._on_group_button_clicked)

        for idx, (key, label) in enumerate(self.NAV_ITEMS):
            btn = QPushButton(label, self._tabs_frame)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setMinimumWidth(86)
            self._buttons[key] = btn
            self._button_order.append(key)
            self._tab_group.addButton(btn, idx)
            tabs_layout.addWidget(btn)

        outer.addWidget(self._tabs_frame, 0, Qt.AlignCenter)
        outer.addStretch(1)

        self._account_frame = QFrame(self)
        self._account_frame.setObjectName("TopNavAccount")
        account_layout = QHBoxLayout(self._account_frame)
        account_layout.setContentsMargins(10, 4, 8, 4)
        account_layout.setSpacing(8)

        self._account_dot = QLabel(self._account_frame)
        self._account_dot.setFixedSize(10, 10)
        self._account_dot.setObjectName("TopNavAccountDot")
        account_layout.addWidget(self._account_dot)

        self._account_name = QLabel("Not signed in", self._account_frame)
        self._account_name.setObjectName("TopNavAccountName")
        account_layout.addWidget(self._account_name)

        self._account_hint = QLabel("Offline", self._account_frame)
        self._account_hint.setObjectName("TopNavAccountHint")
        account_layout.addWidget(self._account_hint)

        self._auth_btn = QPushButton("Sign In", self._account_frame)
        self._auth_btn.setObjectName("TopNavAuthButton")
        self._auth_btn.setCursor(Qt.PointingHandCursor)
        self._auth_btn.setFixedHeight(28)
        self._auth_btn.setMinimumWidth(74)
        self._auth_btn.clicked.connect(self._on_auth_clicked)
        account_layout.addWidget(self._auth_btn)

        outer.addWidget(self._account_frame, 0, Qt.AlignRight | Qt.AlignVCenter)

    def refresh_theme(self) -> None:
        self.setStyleSheet(
            f"""
            #TopNavBar {{
                background: {C["bg_primary"]};
                border-bottom: 1px solid {C["border"]};
            }}
            #TopNavTabs {{
                background: {C["bg_secondary"]};
                border: 1px solid {C["border"]};
                border-radius: 12px;
            }}
            #TopNavTabs QPushButton {{
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 0 12px;
                color: {C["text_secondary"]};
                background: transparent;
                font-size: 12px;
                font-weight: 600;
            }}
            #TopNavTabs QPushButton:hover {{
                background: {C["bg_hover"]};
                color: {C["text_primary"]};
            }}
            #TopNavTabs QPushButton:checked {{
                background: {C["accent_orange_soft"]};
                border-color: {C["border_focus"]};
                color: {C["text_primary"]};
            }}
            #TopNavTabs QPushButton:focus {{
                border-color: {C["border_focus"]};
            }}
            #TopNavAccount {{
                background: {C["bg_secondary"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
            }}
            #TopNavAccountName {{
                color: {C["text_primary"]};
                font-size: 12px;
                font-weight: 600;
            }}
            #TopNavAccountHint {{
                color: {C["text_tertiary"]};
                font-size: 11px;
            }}
            #TopNavAuthButton {{
                border: 1px solid {C["border_strong"]};
                border-radius: 8px;
                background: {C["bg_primary"]};
                color: {C["text_primary"]};
                padding: 0 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            #TopNavAuthButton:hover {{
                background: {C["bg_hover"]};
                border-color: {C["border_focus"]};
            }}
            #TopNavAuthButton:pressed {{
                background: {C["bg_pressed"]};
            }}
            #TopNavAuthButton:focus {{
                border-color: {C["border_focus"]};
            }}
            """
        )
        self._account_dot.setStyleSheet(
            f"background: {C['accent_green'] if self._logged_in else C['border_strong']}; border-radius: 5px;"
        )
        self.update()

    def _on_group_button_clicked(self, button: QPushButton) -> None:
        idx = self._tab_group.id(button)
        if idx < 0 or idx >= len(self._button_order):
            return
        key = self._button_order[idx]
        self.set_active(key, emit=True)

    def _on_auth_clicked(self) -> None:
        if self._logged_in:
            self.logout_requested.emit()
        else:
            self.login_requested.emit()

    def set_active(self, key: str, emit: bool = False) -> None:
        if key not in self._buttons:
            return
        old = self._active_key
        self._active_key = key
        for item_key, button in self._buttons.items():
            button.blockSignals(True)
            button.setChecked(item_key == key)
            button.blockSignals(False)
        if emit and old != key:
            self.tab_changed.emit(key)

    def set_logged_in(self, username: str, hint: str = "Microsoft", requires_sign_in: bool = False) -> None:
        self._logged_in = not requires_sign_in
        self._account_name.setText(username)
        self._account_hint.setText(hint)
        self._auth_btn.setText("Sign In" if requires_sign_in else "Sign Out")
        self.refresh_theme()

    def set_logged_out(self) -> None:
        self._logged_in = False
        self._account_name.setText("Not signed in")
        self._account_hint.setText("Required")
        self._auth_btn.setText("Sign In")
        self.refresh_theme()
