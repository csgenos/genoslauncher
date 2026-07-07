"""Microsoft account management."""

from __future__ import annotations

import base64
import ipaddress
import json
import socket
import time
import urllib.parse
from datetime import datetime, timezone

import requests
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ...core.auth import auth_manager, credential_storage_warning
from ...core.config import config
from ..components.animated_button import OutlineButton, PrimaryButton
from ..login_dialog import LoginDialog
from ..styles import COLORS as C, FONT


class _SkinFetchWorker(QObject):
    image_ready = Signal(int, str, QImage)
    finished = Signal()

    def __init__(self, username: str, generation: int, face_size: int) -> None:
        super().__init__()
        self._username = username
        self._generation = generation
        self._face_size = face_size

    def run(self) -> None:
        try:
            resp = requests.get(
                f"https://api.mojang.com/users/profiles/minecraft/{self._username}",
                timeout=5,
            )
            if not resp.ok:
                return
            uid = resp.json().get("id", "")
            if not uid:
                return
            prof_resp = requests.get(
                f"https://sessionserver.mojang.com/session/minecraft/profile/{uid}",
                timeout=5,
            )
            if not prof_resp.ok:
                return
            prof = prof_resp.json()
            props = prof.get("properties", [])
            if not props:
                return
            decoded = json.loads(base64.b64decode(props[0]["value"]).decode())
            skin_url = decoded.get("textures", {}).get("SKIN", {}).get("url", "")
            if not skin_url:
                return
            if _is_blocked_host(skin_url):
                return
            skin_resp = requests.get(skin_url, timeout=5, allow_redirects=False)
            if 300 <= skin_resp.status_code < 400:
                redir = skin_resp.headers.get("location", "")
                if not redir or _is_blocked_host(redir):
                    return
                skin_resp = requests.get(redir, timeout=5, allow_redirects=False)
            if int(skin_resp.headers.get("content-length", 0)) > 2 * 1024 * 1024:
                return
            img_data = skin_resp.content
            if len(img_data) > 2 * 1024 * 1024:
                return
            img = QImage.fromData(img_data)
            if img.isNull() or img.width() > 4096 or img.height() > 4096:
                return
            face = img.copy(8, 8, 8, 8).scaled(
                self._face_size,
                self._face_size,
                Qt.KeepAspectRatio,
                Qt.FastTransformation,
            )
            self.image_ready.emit(self._generation, self._username, face)
        except Exception:
            pass
        finally:
            self.finished.emit()


class SkinWidget(QLabel):
    _FACE_SIZE = 56
    _CACHE_TTL = 600.0
    _CACHE: dict[str, tuple[float, QImage]] = {}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(self._FACE_SIZE, self._FACE_SIZE)
        self.setAlignment(Qt.AlignCenter)
        self._skin_generation = 0
        self._skin_threads: list[QThread] = []
        self._skin_workers: list[_SkinFetchWorker] = []
        self._set_placeholder()

    def _set_placeholder(self) -> None:
        self.setStyleSheet(
            f"""
            background: {C["bg_tertiary"]};
            border: 1px solid {C["border"]};
            border-radius: 8px;
            font-size: 20px;
            """
        )
        self.setPixmap(QPixmap())
        self.setText("?")

    def load_for(self, username: str) -> None:
        self._set_placeholder()
        cached = self._CACHE.get(username.lower())
        if cached and (time.monotonic() - cached[0]) < self._CACHE_TTL:
            self._on_image_ready(self._skin_generation, username, cached[1])
            return
        self._skin_generation += 1
        generation = self._skin_generation
        worker = _SkinFetchWorker(username, generation, self._FACE_SIZE)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.image_ready.connect(self._on_image_ready)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_skin_worker(t, w))
        self._skin_threads.append(thread)
        self._skin_workers.append(worker)
        thread.start()

    def _on_image_ready(self, generation: int, username: str, image: QImage) -> None:
        if generation == self._skin_generation:
            self.setStyleSheet(
                f"""
                background: transparent;
                border: 1px solid {C["border"]};
                border-radius: 8px;
                """
            )
            self.setText("")
            self.setPixmap(QPixmap.fromImage(image))
            self._CACHE[username.lower()] = (time.monotonic(), image.copy())

    def _cleanup_skin_worker(self, thread: QThread, worker: _SkinFetchWorker) -> None:
        if thread in self._skin_threads:
            self._skin_threads.remove(thread)
        if worker in self._skin_workers:
            self._skin_workers.remove(worker)


def _is_blocked_host(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() != "https":
            return True
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return True
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return True
        try:
            ip = ipaddress.ip_address(host)
            return not ip.is_global
        except ValueError:
            pass
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError:
            return True
        for info in infos:
            try:
                if not ipaddress.ip_address(info[4][0]).is_global:
                    return True
            except ValueError:
                return True
        return False
    except Exception:
        return True

class AccountAvatar(QWidget):
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
        painter.setFont(QFont("Segoe UI", max(1, w // 3), QFont.Weight.DemiBold))
        painter.drawText(0, 0, w, h, Qt.AlignCenter, self._initials)
        painter.end()


class AccountRow(QFrame):
    def __init__(
        self,
        username: str,
        account_type: str = "Offline",
        is_active: bool = False,
        on_select=None,
        on_remove=None,
        last_used: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AccountRow")
        has_last_used = bool(last_used and _relative_time(last_used))
        self.setFixedHeight(86 if has_last_used else 72)
        border_color = C["accent_blue"] if is_active else C["border"]
        self.setStyleSheet(
            f"""
            #AccountRow {{
                background: {C["bg_primary"]};
                border: 1px solid {border_color};
                border-radius: 10px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)
        initials = "".join(w[0] for w in username.split()[:2]) or "?"
        layout.addWidget(AccountAvatar(initials, 40, self))

        info = QVBoxLayout()
        info.setSpacing(2)
        name_lbl = QLabel(username)
        name_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        info.addWidget(name_lbl)
        type_lbl = QLabel(account_type)
        type_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        info.addWidget(type_lbl)
        if last_used:
            rel = _relative_time(last_used)
            if rel:
                used_lbl = QLabel(f"Last used: {rel}")
                used_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
                info.addWidget(used_lbl)
        layout.addLayout(info)
        layout.addStretch()

        if is_active:
            badge = QLabel("Active")
            badge.setStyleSheet(
                f"""
                color: {C["success"]};
                background: {C["accent_green_soft"]};
                border: 1px solid #6EE7B7;
                border-radius: 8px;
                padding: 2px 10px;
                font-size: {FONT["xs"]};
                font-weight: 700;
                """
            )
            layout.addWidget(badge)
        else:
            select_btn = OutlineButton("Select")
            select_btn.setFixedSize(72, 30)
            if on_select:
                select_btn.clicked.connect(on_select)
            layout.addWidget(select_btn)

        remove_btn = OutlineButton("X")
        remove_btn.setFixedSize(32, 30)
        if on_remove:
            remove_btn.clicked.connect(on_remove)
        layout.addWidget(remove_btn)


class AccountsTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._refresh_state()

    def _build_ui(self) -> None:
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(40, 28, 40, 28)
        self._root.setSpacing(20)

        title = QLabel("Accounts")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        self._root.addWidget(title)
        sub = QLabel("A Microsoft account that owns Minecraft: Java Edition is required to play.")
        sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']}; margin-top: -12px;")
        self._root.addWidget(sub)

        self._ms_card = self._build_ms_card()
        self._root.addWidget(self._ms_card)

        add_ms_row = QHBoxLayout()
        self._add_ms_lbl = QLabel("Have multiple Minecraft accounts?")
        self._add_ms_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        add_ms_row.addWidget(self._add_ms_lbl)
        add_ms_row.addStretch()
        self._add_ms_btn = OutlineButton("+ Add Microsoft Account")
        self._add_ms_btn.setFixedHeight(34)
        self._add_ms_btn.clicked.connect(self._add_ms_account)
        add_ms_row.addWidget(self._add_ms_btn)
        self._root.addLayout(add_ms_row)

        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {C['border']}; border: none;")
        self._root.addWidget(div)

        self._root.addWidget(_lbl("Your Accounts", FONT["lg"], C["text_primary"], bold=True))
        self._accounts_container = QWidget()
        self._accounts_layout = QVBoxLayout(self._accounts_container)
        self._accounts_layout.setContentsMargins(0, 0, 0, 0)
        self._accounts_layout.setSpacing(10)
        self._root.addWidget(self._accounts_container)
        self._root.addStretch()

        note = QLabel(
            "Credentials are stored securely on this device. After successful verification, local play remains "
            "available for seven days if Microsoft services cannot be reached."
        )
        note.setStyleSheet(
            f"""
            color: {C["text_tertiary"]};
            font-size: {FONT["xs"]};
            background: {C["bg_secondary"]};
            border: 1px solid {C["border"]};
            border-radius: 8px;
            padding: 10px 14px;
            """
        )
        note.setWordWrap(True)
        self._root.addWidget(note)

        warning = credential_storage_warning()
        if warning:
            warn = QLabel(warning)
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color: {C['danger']}; font-size: {FONT['xs']};")
            self._root.addWidget(warn)

    def _build_ms_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("MsCard")
        card.setFixedHeight(96)
        card.setStyleSheet(
            f"""
            #MsCard {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 12px;
            }}
            """
        )
        ms_h = QHBoxLayout(card)
        ms_h.setContentsMargins(20, 0, 20, 0)
        ms_h.setSpacing(18)

        self._ms_icon = QLabel("M")
        self._ms_icon.setFixedSize(52, 52)
        self._ms_icon.setAlignment(Qt.AlignCenter)
        self._ms_icon.setStyleSheet(
            """
            background: #0078D4;
            color: white;
            border-radius: 10px;
            font-size: 22px;
            font-weight: 900;
            """
        )
        ms_h.addWidget(self._ms_icon)

        self._skin_widget = SkinWidget(card)
        self._skin_widget.setVisible(False)
        ms_h.addWidget(self._skin_widget)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        self._ms_title = QLabel("Sign in with Microsoft")
        self._ms_title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        text_col.addWidget(self._ms_title)
        self._ms_sub = QLabel("Required for all launches and checked against Minecraft ownership.")
        self._ms_sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        text_col.addWidget(self._ms_sub)
        ms_h.addLayout(text_col)
        ms_h.addStretch()

        self._ms_btn = PrimaryButton("Sign In")
        self._ms_btn.setFixedSize(110, 38)
        self._ms_btn.clicked.connect(self._on_ms_action)
        ms_h.addWidget(self._ms_btn)
        return card

    def _refresh_state(self) -> None:
        if auth_manager.is_logged_in:
            self._ms_title.setText(f"Active: {auth_manager.username}")
            state = auth_manager.verification_state
            if state == "online":
                self._ms_sub.setText("Verified online | Minecraft play enabled")
                self._ms_btn.setText("Sign Out")
            elif state == "offline_grace":
                expiry = auth_manager.grace_expires_at
                remaining = _grace_remaining(expiry)
                self._ms_sub.setText(f"Offline grace active | {remaining} remaining")
                self._ms_btn.setText("Sign Out")
            else:
                self._ms_sub.setText("Verification expired or invalid | Sign in again to play")
                self._ms_btn.setText("Sign In Again")
            self._ms_icon.setVisible(False)
            self._skin_widget.setVisible(True)
            self._skin_widget.load_for(auth_manager.username)
        else:
            self._ms_title.setText("Sign in with Microsoft")
            self._ms_sub.setText("Required for all launches and checked against Minecraft ownership.")
            self._ms_btn.setText("Sign In")
            self._ms_icon.setVisible(True)
            self._skin_widget.setVisible(False)
        self._add_ms_btn.setVisible(auth_manager.is_logged_in)
        self._add_ms_lbl.setVisible(auth_manager.is_logged_in)

        while self._accounts_layout.count():
            item = self._accounts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        active_ms = auth_manager.username if auth_manager.is_logged_in else ""
        for ms_name in auth_manager.list_ms_accounts():
            is_active = ms_name == active_ms
            last_used = get_account_last_used(ms_name)
            if is_active:
                state_labels = {
                    "online": "Microsoft | Verified online",
                    "offline_grace": "Microsoft | Offline grace",
                    "sign_in_required": "Microsoft | Sign-in required",
                }
                account_type = state_labels.get(auth_manager.verification_state, "Microsoft | Saved")
            else:
                account_type = "Microsoft | Saved"
            row = AccountRow(
                ms_name,
                account_type,
                is_active=is_active,
                on_select=lambda n=ms_name: self._switch_ms_account(n),
                on_remove=lambda n=ms_name: self._remove_ms_account(n),
                last_used=last_used,
            )
            self._accounts_layout.addWidget(row)

        if not auth_manager.list_ms_accounts():
            empty = _lbl("No Microsoft accounts added yet.", FONT["sm"], C["text_tertiary"])
            empty.setAlignment(Qt.AlignCenter)
            self._accounts_layout.addWidget(empty)

    def _on_ms_action(self) -> None:
        if auth_manager.is_logged_in and auth_manager.verification_state != "sign_in_required":
            self._logout_ms()
        else:
            self._open_login_dialog()

    def _open_login_dialog(self) -> None:
        dlg = LoginDialog(self)
        dlg.login_succeeded.connect(self._on_login_success)
        dlg.exec()

    def _on_login_success(self, account: dict) -> None:
        name = account.get("name", "")
        config.update({"last_account": name})
        if name:
            record_account_used(name)
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

    def _add_ms_account(self) -> None:
        dlg = LoginDialog(self, start_login_func=auth_manager.add_account)
        dlg.setWindowTitle("Add Microsoft Account")
        dlg.login_succeeded.connect(lambda _: self._refresh_state())
        dlg.exec()

    def _switch_ms_account(self, username: str) -> None:
        if auth_manager.switch_account(username):
            config.update({"last_account": username})
            record_account_used(username)
            self._refresh_state()
        else:
            QMessageBox.warning(
                self,
                "Switch Account",
                f"Could not load saved credentials for {username}.\nPlease sign in again.",
            )

    def _remove_ms_account(self, username: str) -> None:
        reply = QMessageBox.question(
            self,
            "Remove Account",
            f"Remove {username} from saved accounts?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            auth_manager.remove_ms_account(username)
            self._refresh_state()

def _lbl(text: str, size: str, color: str, bold: bool = False) -> QLabel:
    w = QLabel(text)
    weight = "700" if bold else "400"
    w.setStyleSheet(f"font-size: {size}; font-weight: {weight}; color: {color};")
    return w


def _account_last_used_key(username: str) -> str:
    return f"account_last_used_{username}"


def get_account_last_used(username: str) -> str:
    store = config.get("account_last_used", {})
    if isinstance(store, dict):
        value = str(store.get(username, "") or "").strip()
        if value:
            return value
    # Backward compatibility with legacy dynamic keys.
    return str(config.get(_account_last_used_key(username), "") or "").strip()


def record_account_used(username: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    store = config.get("account_last_used", {})
    if not isinstance(store, dict):
        store = {}
    store[username] = stamp
    config.set("account_last_used", store)


def _grace_remaining(expiry: datetime | None) -> str:
    if expiry is None:
        return "0 hours"
    seconds = max(0, int((expiry - datetime.now(timezone.utc)).total_seconds()))
    days, remainder = divmod(seconds, 86400)
    hours = remainder // 3600
    if days:
        return f"{days}d {hours}h"
    return f"{hours}h"


def _relative_time(iso_str: str) -> str:
    try:
        ts = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        delta = int((now - ts).total_seconds())
        if delta < 60:
            return "just now"
        if delta < 3600:
            m = delta // 60
            return f"{m} minute{'s' if m != 1 else ''} ago"
        if delta < 86400:
            h = delta // 3600
            return f"{h} hour{'s' if h != 1 else ''} ago"
        d = delta // 86400
        return f"{d} day{'s' if d != 1 else ''} ago"
    except Exception:
        return ""
