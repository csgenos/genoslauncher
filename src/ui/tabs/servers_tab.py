"""
Server Browser tab — save favorite Minecraft servers, ping them, and launch directly.

Servers stored in config as: {"servers": [{"name", "ip", "port"}]}
Launch: emits server_launch_requested(version_id, instance_id, server_ip, port_str)
"""

from __future__ import annotations

import socket
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import OutlineButton, PrimaryButton
from ..qt_dispatch import run_on_ui_thread
from ...core.config import config
from ...core.instances import list_instances, selected_instance


_DEFAULT_PORT = 25565


class ServerRow(QFrame):
    launch_requested = Signal(str, str)   # ip, port

    def __init__(self, server: dict, on_remove, parent=None) -> None:
        super().__init__(parent)
        self._server = server
        self.setObjectName("ServerRow")
        self.setFixedHeight(68)
        self.setStyleSheet(f"""
            #ServerRow {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        # Status dot
        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._dot.setStyleSheet(f"color: {C['text_disabled']}; font-size: 10px;")
        layout.addWidget(self._dot)

        # Name + address
        info = QVBoxLayout()
        info.setSpacing(2)
        name = QLabel(server.get("name", "Server"))
        name.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        info.addWidget(name)
        addr = QLabel(f"{server.get('ip', '?')}:{server.get('port', _DEFAULT_PORT)}")
        addr.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_secondary']};")
        info.addWidget(addr)
        layout.addLayout(info, 1)

        ping_btn = OutlineButton("Ping")
        ping_btn.setFixedSize(62, 30)
        ping_btn.clicked.connect(self._ping)
        layout.addWidget(ping_btn)

        play_btn = PrimaryButton("Play")
        play_btn.setFixedSize(66, 30)
        play_btn.clicked.connect(self._play)
        layout.addWidget(play_btn)

        remove_btn = OutlineButton("✕")
        remove_btn.setFixedSize(32, 30)
        remove_btn.clicked.connect(on_remove)
        layout.addWidget(remove_btn)

    def _ping(self) -> None:
        self._dot.setStyleSheet(f"color: {C['text_disabled']}; font-size: 10px;")
        ip   = self._server.get("ip", "")
        port = int(self._server.get("port", _DEFAULT_PORT))

        def _do():
            try:
                with socket.create_connection((ip, port), timeout=3):
                    ok = True
            except OSError:
                ok = False
            color = C["success"] if ok else C["danger"]
            run_on_ui_thread(lambda: self._dot.setStyleSheet(
                f"color: {color}; font-size: 10px;"
            ))

        threading.Thread(target=_do, daemon=True).start()

    def _play(self) -> None:
        self.launch_requested.emit(
            self._server.get("ip", ""),
            str(self._server.get("port", _DEFAULT_PORT)),
        )


class ServersTab(QWidget):
    """Browse and launch saved Minecraft servers."""

    server_launch_requested = Signal(str, str, str, str)  # version, instance_id, ip, port

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 28, 40, 28)
        root.setSpacing(20)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Server Browser")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        hdr.addWidget(title)
        hdr.addStretch()
        add_btn = OutlineButton("+ Add Server")
        add_btn.setFixedHeight(34)
        add_btn.clicked.connect(self._add_server)
        hdr.addWidget(add_btn)
        root.addLayout(hdr)

        sub = QLabel("Save favorite servers, check their status, and launch Minecraft directly into them.")
        sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']}; margin-top: -12px;")
        root.addWidget(sub)

        self._status = QLabel("")
        self._status.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        root.addWidget(self._status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setSpacing(10)
        self._layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._container)
        root.addWidget(scroll, 1)

        note = QLabel(
            "Tip: 'Play' launches the last-used Minecraft instance and connects to the server automatically."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"""
            color: {C["text_tertiary"]};
            font-size: {FONT["xs"]};
            background: {C["bg_secondary"]};
            border: 1px solid {C["border"]};
            border-radius: 8px;
            padding: 10px 14px;
        """)
        root.addWidget(note)

    def _refresh(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        servers = config.get("servers", [])
        if not servers:
            empty = QLabel("No servers saved yet. Click '+ Add Server' to add one.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color: {C['text_tertiary']}; font-size: {FONT['sm']};")
            self._layout.addWidget(empty)
            self._layout.addStretch()
            self._status.setText("")
            return

        self._status.setText(f"{len(servers)} saved server(s)")
        for srv in servers:
            row = ServerRow(srv, on_remove=lambda _=False, s=dict(srv): self._remove_server(s))
            row.launch_requested.connect(self._on_play)
            self._layout.addWidget(row)
        self._layout.addStretch()

    def _add_server(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Server", "Server name:")
        if not ok or not name.strip():
            return
        ip, ok = QInputDialog.getText(self, "Add Server", "Server IP address:")
        if not ok or not ip.strip():
            return
        port_str, ok = QInputDialog.getText(self, "Add Server", "Port:", text=str(_DEFAULT_PORT))
        if not ok:
            return
        try:
            port = int(port_str.strip()) if port_str.strip() else _DEFAULT_PORT
        except ValueError:
            port = _DEFAULT_PORT
        servers = list(config.get("servers", []))
        servers.append({"name": name.strip(), "ip": ip.strip(), "port": port})
        config.set("servers", servers)
        self._refresh()

    def _remove_server(self, server_ref: dict) -> None:
        servers = list(config.get("servers", []))
        match_index = -1
        for i, srv in enumerate(servers):
            if (
                srv.get("name", "") == server_ref.get("name", "")
                and str(srv.get("ip", "")) == str(server_ref.get("ip", ""))
                and int(srv.get("port", _DEFAULT_PORT)) == int(server_ref.get("port", _DEFAULT_PORT))
            ):
                match_index = i
                break
        if match_index < 0:
            self._status.setText("Server not found (list changed).")
            return
        name = servers[match_index].get("name", "server")
        reply = QMessageBox.question(
            self, "Remove Server", f"Remove {name}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            servers.pop(match_index)
            config.set("servers", servers)
            self._refresh()

    def _on_play(self, ip: str, port: str) -> None:
        instance = selected_instance()
        version_id  = (instance or {}).get("mc_version", config.get("selected_version", ""))
        instance_id = (instance or {}).get("id", "")
        if not version_id:
            instances = list_instances()
            if instances:
                version_id  = instances[0].get("mc_version", "")
                instance_id = instances[0].get("id", "")
        if not version_id:
            QMessageBox.warning(self, "No Instance", "No Minecraft instance is selected or installed.")
            return
        self.server_launch_requested.emit(version_id, instance_id, ip, port)
