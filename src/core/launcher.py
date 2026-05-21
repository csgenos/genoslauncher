"""
Minecraft launch logic — wraps minecraft-launcher-lib.
Emits progress via Qt signals so the UI can animate the launch bar.

Fixes applied:
  B-Z-004: Proper offline UUID using UUID3 (mirrors Minecraft's own algorithm)
  B-Y-007: JVM arg deduplication — preset can't override -Xmx/-Xms set from RAM slider;
           user custom args are sanitized (each token must start with '-')
"""

from __future__ import annotations

import os
import subprocess
import threading
import uuid as _uuid
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from .config import config
from .auth import auth_manager

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
    releases = [
        "1.21.4", "1.21.3", "1.21.1", "1.20.6", "1.20.4",
        "1.20.2", "1.20.1", "1.19.4", "1.19.2", "1.18.2",
        "1.17.1", "1.16.5", "1.12.2", "1.8.9", "1.7.10",
    ]
    return [{"id": v, "type": "release", "url": ""} for v in releases]


def get_installed_versions() -> list[str]:
    mc_dir = config.get("minecraft_dir")
    if not MLL_AVAILABLE or not mc_dir:
        return []
    try:
        return [v["id"] for v in mll.utils.get_installed_versions(mc_dir)]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Offline UUID (B-Z-004)
# ---------------------------------------------------------------------------

def _offline_uuid(username: str) -> str:
    """
    Generate a consistent offline UUID for a username.
    Mirrors Minecraft's own offline-mode algorithm:
    UUID3(DNS_NAMESPACE, "OfflinePlayer:<username>").
    """
    return str(_uuid.uuid3(_uuid.NAMESPACE_DNS, f"OfflinePlayer:{username}"))


# ---------------------------------------------------------------------------
# JVM argument builder (B-Y-007)
# ---------------------------------------------------------------------------

_XMX_PREFIXES = ("-Xmx", "-Xms", "-Xss")


def _build_jvm_args(ram_mb: int, preset_args: str, custom_args: str) -> list[str]:
    """
    Build the final JVM argument list.

    - -Xmx and -Xms are set from ram_mb; any duplicates in preset/custom are dropped.
    - Each token from custom_args must start with '-' (basic sanitization).
    """
    # Memory flags always come first and are authoritative
    args = [f"-Xmx{ram_mb}M", f"-Xms{min(ram_mb, 512)}M"]

    for raw in (preset_args, custom_args):
        for token in raw.split():
            token = token.strip()
            if not token:
                continue
            # Skip any memory override from presets/custom — already set above
            if any(token.startswith(p) for p in _XMX_PREFIXES):
                continue
            # Only allow flags (must start with '-') to prevent argument injection
            if not token.startswith("-"):
                continue
            args.append(token)

    return args


# ---------------------------------------------------------------------------
# Loader install helpers (used by modpacks pipeline and shaders tab)
# ---------------------------------------------------------------------------

def install_minecraft_base(
    version_id: str,
    mc_dir: str,
    on_progress=None,
) -> None:
    """Install a base Minecraft version into mc_dir (no-op if already present)."""
    if not MLL_AVAILABLE:
        return

    def _cb(cur, tot, s):
        if on_progress:
            on_progress(cur, tot, s)

    callbacks = {
        "setStatus":   lambda t: _cb(0, 100, t),
        "setProgress": lambda v: _cb(v, 100, ""),
        "setMax":      lambda v: _cb(0, v, ""),
    }
    mll.install.install_minecraft_version(
        versionid=version_id,
        minecraft_directory=mc_dir,
        callback=callbacks,
    )


def install_loader(
    deps: dict,
    mc_dir: str,
    on_progress=None,
) -> str:
    """
    Install the Fabric or Quilt loader declared in mrpack dependencies.

    Returns the full version ID to pass to the launcher (e.g.
    "fabric-loader-0.14.21-1.20.1").  Falls back to the plain minecraft
    version string when no supported loader is declared.
    """
    mc_version = deps.get("minecraft", "")
    if not MLL_AVAILABLE or not mc_version:
        return mc_version

    def _cb(cur, tot, s):
        if on_progress:
            on_progress(cur, tot, s)

    callbacks = {
        "setStatus":   lambda t: _cb(0, 100, t),
        "setProgress": lambda v: _cb(v, 100, ""),
        "setMax":      lambda v: _cb(0, v, ""),
    }

    fabric_ver = deps.get("fabric-loader")
    if fabric_ver:
        _cb(0, 1, f"Installing Fabric {fabric_ver} for {mc_version}…")
        mll.fabric.install_fabric(
            minecraft_version=mc_version,
            minecraft_directory=mc_dir,
            loader_version=fabric_ver,
            callback=callbacks,
        )
        return f"fabric-loader-{fabric_ver}-{mc_version}"

    quilt_ver = deps.get("quilt-loader")
    if quilt_ver:
        _cb(0, 1, f"Installing Quilt {quilt_ver} for {mc_version}…")
        mll.quilt.install_quilt(
            minecraft_version=mc_version,
            minecraft_directory=mc_dir,
            loader_version=quilt_ver,
            callback=callbacks,
        )
        return f"quilt-loader-{quilt_ver}-{mc_version}"

    return mc_version


# ---------------------------------------------------------------------------
# Install worker
# ---------------------------------------------------------------------------

class InstallWorker(QObject):
    """Downloads and installs a Minecraft version on a background thread."""

    progress_changed = Signal(int, int, str)
    finished = Signal(bool, str)

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
            "setStatus":   lambda text: self.progress_changed.emit(0, 100, text),
            "setProgress": lambda val:  self.progress_changed.emit(val, 100, ""),
            "setMax":      lambda val:  self.progress_changed.emit(0, val, ""),
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

    status_changed  = Signal(str)
    process_started = Signal()
    process_ended   = Signal(int)
    error           = Signal(str)

    def __init__(
        self,
        version_id: str,
        username:   str = "Player",
        parent:     Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.version_id = version_id
        self.username   = username
        self._thread:  Optional[threading.Thread]  = None
        self._process: Optional[subprocess.Popen]  = None

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
        java   = config.get("java_path") or "java"
        ram    = config.get("ram_mb", 4096)
        width  = config.get("resolution_width", 1280)
        height = config.get("resolution_height", 720)

        # Real credentials when logged in with a matching Microsoft account (B-Z-004)
        if auth_manager.is_logged_in and auth_manager.username == self.username:
            token = auth_manager.access_token
            uid   = auth_manager.uuid or _offline_uuid(self.username)
        else:
            token = "offline"
            uid   = _offline_uuid(self.username)

        # JVM args with deduplication (B-Y-007)
        from .java_manager import get_preset_args
        preset_key  = config.get("jvm_preset", "performance")
        preset_args = get_preset_args(preset_key)
        custom_args = config.get("jvm_args", "")
        jvm_args    = _build_jvm_args(ram, preset_args, custom_args)

        options = {
            "username":         self.username,
            "uuid":             uid,
            "token":            token,
            "jvmArguments":     jvm_args,
            "gameDirectory":    mc_dir,
            "executablePath":   java,
            "customResolution": True,
            "resolutionWidth":  str(width),
            "resolutionHeight": str(height),
        }

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
