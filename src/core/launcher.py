"""
Minecraft launch logic — wraps minecraft-launcher-lib.
Emits progress via Qt signals so the UI can animate the launch bar.
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from .config import config

try:
    import minecraft_launcher_lib as mll
    MLL_AVAILABLE = True
except ImportError:
    MLL_AVAILABLE = False
    print("[Launcher] minecraft-launcher-lib not installed — launch disabled.")


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def get_available_versions(
    include_snapshots: bool = False,
    include_old: bool = False,
) -> list[dict]:
    """Return a filtered list of available Minecraft versions."""
    if not MLL_AVAILABLE:
        return _demo_versions()

    try:
        all_versions = mll.utils.get_version_list()
    except Exception:
        return _demo_versions()

    keep = []
    for v in all_versions:
        vtype = v.get("type", "")
        if vtype == "release":
            keep.append(v)
        elif vtype == "snapshot" and include_snapshots:
            keep.append(v)
        elif vtype in ("old_alpha", "old_beta") and include_old:
            keep.append(v)
    return keep


def _demo_versions() -> list[dict]:
    """Fallback version list when offline or lib missing."""
    releases = [
        "1.21.4", "1.21.3", "1.21.1", "1.20.6", "1.20.4",
        "1.20.2", "1.20.1", "1.19.4", "1.19.2", "1.18.2",
        "1.17.1", "1.16.5", "1.12.2", "1.8.9", "1.7.10",
    ]
    return [{"id": v, "type": "release", "url": ""} for v in releases]


def get_installed_versions() -> list[str]:
    """Return Minecraft version IDs that are already installed locally."""
    mc_dir = config.get("minecraft_dir")
    if not MLL_AVAILABLE or not mc_dir:
        return []
    try:
        return [v["id"] for v in mll.utils.get_installed_versions(mc_dir)]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Install worker
# ---------------------------------------------------------------------------

class InstallWorker(QObject):
    """Downloads and installs a Minecraft version on a background thread."""

    progress_changed = Signal(int, int, str)   # current, maximum, status text
    finished = Signal(bool, str)               # success, message

    def __init__(self, version_id: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.version_id = version_id
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        if not MLL_AVAILABLE:
            self.finished.emit(False, "minecraft-launcher-lib is not installed.")
            return

        mc_dir = config.get("minecraft_dir")
        Path(mc_dir).mkdir(parents=True, exist_ok=True)

        callbacks = {
            "setStatus": lambda text: self.progress_changed.emit(0, 100, text),
            "setProgress": lambda val: self.progress_changed.emit(val, 100, ""),
            "setMax": lambda val: self.progress_changed.emit(0, val, ""),
        }

        try:
            mll.install.install_minecraft_version(
                versionid=self.version_id,
                minecraft_directory=mc_dir,
                callback=callbacks,
            )
            self.finished.emit(True, f"Version {self.version_id} installed successfully.")
        except Exception as exc:
            self.finished.emit(False, str(exc))


# ---------------------------------------------------------------------------
# Launch worker
# ---------------------------------------------------------------------------

class LaunchWorker(QObject):
    """Launches Minecraft on a background thread and reports status."""

    status_changed = Signal(str)   # status text
    process_started = Signal()
    process_ended = Signal(int)    # exit code
    error = Signal(str)

    def __init__(
        self,
        version_id: str,
        username: str = "Player",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.version_id = version_id
        self.username = username
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def terminate(self) -> None:
        if self._process:
            self._process.terminate()

    def _run(self) -> None:
        if not MLL_AVAILABLE:
            self.error.emit("minecraft-launcher-lib is not installed.")
            return

        mc_dir = config.get("minecraft_dir")
        java = config.get("java_path") or "java"
        ram = config.get("ram_mb", 4096)
        width = config.get("resolution_width", 1280)
        height = config.get("resolution_height", 720)
        jvm_extra = config.get("jvm_args", "")

        options = {
            "username": self.username,
            "uuid": "00000000-0000-0000-0000-000000000000",
            "token": "offline",
            "jvmArguments": [
                f"-Xmx{ram}M",
                f"-Xms{min(ram, 512)}M",
            ],
            "gameDirectory": mc_dir,
            "executablePath": java,
            "customResolution": True,
            "resolutionWidth": str(width),
            "resolutionHeight": str(height),
        }
        if jvm_extra:
            options["jvmArguments"] += jvm_extra.split()

        try:
            self.status_changed.emit("Building launch command...")
            command = mll.command.get_minecraft_command(
                version=self.version_id,
                minecraft_directory=mc_dir,
                options=options,
            )
            self.status_changed.emit("Starting Minecraft...")
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.process_started.emit()
            self.status_changed.emit("Minecraft is running!")
            self._process.wait()
            self.process_ended.emit(self._process.returncode)
        except FileNotFoundError:
            self.error.emit(
                f"Java not found at '{java}'.\n"
                "Please set a valid Java path in Settings."
            )
        except Exception as exc:
            self.error.emit(str(exc))
