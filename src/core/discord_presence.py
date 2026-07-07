"""Discord Rich Presence integration for GenosLauncher.

Uses Discord's local IPC/RPC transport directly so the launcher does not need
an extra runtime dependency. Presence is best-effort: if Discord is closed,
busy, or rejects the configured application id, launcher/game flow continues.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import struct
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, BinaryIO

from .config import config

log = logging.getLogger(__name__)

DISCORD_APPLICATION_ID = "1524019146030055444"
DEFAULT_LARGE_IMAGE_KEY = "glauncherlogo"

_OP_HANDSHAKE = 0
_OP_FRAME = 1
_MAX_TEXT = 128


def _clean_text(value: object, fallback: str) -> str:
    text = " ".join(str(value or "").split()) or fallback
    if len(text) <= _MAX_TEXT:
        return text
    return text[: _MAX_TEXT - 3].rstrip() + "..."


def _base_activity(
    details: str,
    state: str,
    *,
    start_time: int | None = None,
    large_image: str | None = None,
) -> dict[str, Any]:
    activity: dict[str, Any] = {
        "details": _clean_text(details, "Using GenosLauncher"),
        "state": _clean_text(state, "In the launcher"),
    }
    if start_time:
        activity["timestamps"] = {"start": int(start_time)}

    image_key = _clean_text(large_image, "").strip()
    if image_key:
        activity["assets"] = {
            "large_image": image_key,
            "large_text": "GenosLauncher",
        }
    return activity


def _play_state(version_id: str, instance_name: str = "", multiplayer: bool = False) -> str:
    label = _clean_text(instance_name or version_id, "Minecraft")
    if multiplayer:
        return _clean_text(f"{label} - multiplayer", label)
    return label


def build_launcher_activity(
    tab_label: str = "Home",
    *,
    start_time: int | None = None,
    large_image: str = DEFAULT_LARGE_IMAGE_KEY,
) -> dict[str, Any]:
    return _base_activity(
        "Using GenosLauncher",
        f"Browsing {tab_label or 'Home'}",
        start_time=start_time,
        large_image=large_image,
    )


def build_launching_activity(
    version_id: str,
    instance_name: str = "",
    *,
    multiplayer: bool = False,
    start_time: int | None = None,
    large_image: str = DEFAULT_LARGE_IMAGE_KEY,
) -> dict[str, Any]:
    return _base_activity(
        "Launching Minecraft",
        _play_state(version_id, instance_name, multiplayer),
        start_time=start_time,
        large_image=large_image,
    )


def build_playing_activity(
    version_id: str,
    instance_name: str = "",
    *,
    multiplayer: bool = False,
    start_time: int | None = None,
    large_image: str = DEFAULT_LARGE_IMAGE_KEY,
) -> dict[str, Any]:
    return _base_activity(
        "Playing Minecraft",
        _play_state(version_id, instance_name, multiplayer),
        start_time=start_time,
        large_image=large_image,
    )


def _candidate_ipc_paths() -> list[str]:
    if platform.system() == "Windows":
        return [rf"\\?\pipe\discord-ipc-{index}" for index in range(10)]

    bases = [
        os.environ.get("XDG_RUNTIME_DIR", ""),
        tempfile.gettempdir(),
        "/tmp",
        "/var/tmp",
        "/usr/tmp",
    ]
    seen: set[str] = set()
    paths: list[str] = []
    for base in bases:
        if not base:
            continue
        for index in range(10):
            path = str(Path(base) / f"discord-ipc-{index}")
            if path not in seen:
                paths.append(path)
                seen.add(path)
    return paths


class DiscordPresence:
    """Small best-effort Discord RPC client."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pipe: BinaryIO | None = None
        self._client_id = ""
        self._launcher_started_at = int(time.time())
        self._game_started_at = 0

    def set_launcher(self, tab_label: str = "Home") -> None:
        """Show the launcher/browsing presence."""
        if not self._is_enabled():
            return
        activity = build_launcher_activity(
            tab_label,
            start_time=self._launcher_started_at,
            large_image=self._large_image_key(),
        )
        self._update_async(activity)

    def set_launching(self, version_id: str, instance_name: str = "", *, multiplayer: bool = False) -> None:
        """Show a short launch-in-progress presence."""
        if not self._is_enabled():
            return
        self._game_started_at = int(time.time())
        activity = build_launching_activity(
            version_id,
            instance_name,
            multiplayer=multiplayer,
            start_time=self._game_started_at,
            large_image=self._large_image_key(),
        )
        self._update_async(activity)

    def set_playing(self, version_id: str, instance_name: str = "", *, multiplayer: bool = False) -> None:
        """Show Minecraft as running."""
        if not self._is_enabled():
            return
        if not self._game_started_at:
            self._game_started_at = int(time.time())
        activity = build_playing_activity(
            version_id,
            instance_name,
            multiplayer=multiplayer,
            start_time=self._game_started_at,
            large_image=self._large_image_key(),
        )
        self._update_async(activity)

    def clear(self) -> None:
        """Clear the Discord activity if this process has one set."""
        self._update_async(None, force=True)

    def close(self) -> None:
        """Best-effort clear and close of the IPC handle."""
        thread = threading.Thread(target=self._close_blocking, daemon=True)
        thread.start()

    def _is_enabled(self) -> bool:
        return bool(config.get("discord_presence_enabled", True)) and bool(self._configured_client_id())

    def _configured_client_id(self) -> str:
        return str(config.get("discord_presence_client_id", DISCORD_APPLICATION_ID) or "").strip()

    def _large_image_key(self) -> str:
        return str(config.get("discord_presence_large_image", DEFAULT_LARGE_IMAGE_KEY) or "").strip()

    def _update_async(self, activity: dict[str, Any] | None, *, force: bool = False) -> None:
        thread = threading.Thread(target=self._update_blocking, args=(activity, force), daemon=True)
        thread.start()

    def _update_blocking(self, activity: dict[str, Any] | None, force: bool = False) -> None:
        with self._lock:
            if not force and not self._is_enabled():
                return
            client_id = self._configured_client_id()
            if not client_id:
                self._disconnect_locked()
                return
            if activity is None and self._pipe is None:
                return
            try:
                if self._pipe is None or self._client_id != client_id:
                    self._connect_locked(client_id)
                self._send_activity_locked(activity)
            except OSError as exc:
                log.debug("Discord Rich Presence update skipped: %s", exc)
                self._disconnect_locked()

    def _close_blocking(self) -> None:
        with self._lock:
            try:
                if self._pipe is not None:
                    self._send_activity_locked(None)
            except OSError:
                pass
            self._disconnect_locked()

    def _connect_locked(self, client_id: str) -> None:
        self._disconnect_locked()
        self._pipe = self._open_pipe()
        self._client_id = client_id
        self._send_packet_locked(_OP_HANDSHAKE, {"v": 1, "client_id": client_id})

    def _open_pipe(self) -> BinaryIO:
        last_error: OSError | None = None
        for path in _candidate_ipc_paths():
            try:
                if platform.system() == "Windows":
                    return open(path, "r+b", buffering=0)

                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    sock.connect(path)
                    return sock.makefile("rwb", buffering=0)
                except OSError:
                    sock.close()
                    raise
            except OSError as exc:
                last_error = exc
                continue
        raise OSError("Discord desktop IPC pipe was not found.") from last_error

    def _send_activity_locked(self, activity: dict[str, Any] | None) -> None:
        self._send_packet_locked(
            _OP_FRAME,
            {
                "cmd": "SET_ACTIVITY",
                "args": {
                    "pid": os.getpid(),
                    "activity": activity,
                },
                "nonce": str(uuid.uuid4()),
            },
        )

    def _send_packet_locked(self, opcode: int, payload: dict[str, Any]) -> None:
        if self._pipe is None:
            raise OSError("Discord IPC pipe is not connected.")
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._pipe.write(struct.pack("<II", opcode, len(encoded)))
        self._pipe.write(encoded)
        self._pipe.flush()

    def _disconnect_locked(self) -> None:
        if self._pipe is not None:
            try:
                self._pipe.close()
            except OSError:
                pass
        self._pipe = None
        self._client_id = ""


discord_presence = DiscordPresence()
