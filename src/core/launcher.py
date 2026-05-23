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
import json
import logging
import subprocess
import threading
import uuid as _uuid
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from .config import config
from .config import APP_DIR, LOGS_DIR
from .auth import auth_manager
from .instances import create_vanilla_instance, find_instance, find_instance_for_version, list_instances
from .java_manager import find_best_java, get_preset_args, required_java_for_mc
from .validators import safe_path_segment, validate_version_id

log = logging.getLogger(__name__)

try:
    import minecraft_launcher_lib as mll
    MLL_AVAILABLE = True
except ImportError:
    MLL_AVAILABLE = False
    log.warning("minecraft-launcher-lib is not installed; launch features are disabled.")


# ---------------------------------------------------------------------------
# Installed-versions cache (OX-001)
# Avoids repeated filesystem scans when launching or checking multiple versions.
# ---------------------------------------------------------------------------

import time as _time

_INSTALLED_CACHE_TTL = 30.0  # seconds
_installed_cache: dict[str, tuple[float, frozenset]] = {}
_installed_cache_lock = threading.Lock()


def _get_installed_versions_cached(mc_dir: str) -> frozenset:
    now = _time.monotonic()
    with _installed_cache_lock:
        if mc_dir in _installed_cache:
            ts, versions = _installed_cache[mc_dir]
            if now - ts < _INSTALLED_CACHE_TTL:
                return versions
    versions = frozenset(v.get("id") for v in mll.utils.get_installed_versions(mc_dir))
    with _installed_cache_lock:
        _installed_cache[mc_dir] = (now, versions)
    return versions


def invalidate_installed_cache(mc_dir: str | None = None) -> None:
    with _installed_cache_lock:
        if mc_dir is None:
            _installed_cache.clear()
        else:
            _installed_cache.pop(mc_dir, None)


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def get_available_versions(
    include_snapshots: bool = False,
    include_old: bool = False,
) -> list[dict]:
    if not MLL_AVAILABLE:
        return _load_cached_versions(include_snapshots, include_old)
    try:
        all_versions = mll.utils.get_version_list()
        _save_versions_cache(all_versions)
    except Exception as exc:
        log.warning("Version list fetch failed: %s", exc)
        return _load_cached_versions(include_snapshots, include_old)

    return _filter_versions(all_versions, include_snapshots, include_old)


def _filter_versions(all_versions: list[dict], include_snapshots: bool, include_old: bool) -> list[dict]:
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


def _versions_cache_path() -> Path:
    return APP_DIR / "cache" / "versions.json"


def _save_versions_cache(versions: list[dict]) -> None:
    try:
        path = _versions_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(versions), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        log.warning("Version cache save failed: %s", exc.__class__.__name__)


def _load_cached_versions(include_snapshots: bool, include_old: bool) -> list[dict]:
    try:
        path = _versions_cache_path()
        if path.exists():
            versions = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(versions, list):
                return _filter_versions(versions, include_snapshots, include_old)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Version cache read failed: %s", exc.__class__.__name__)

    return _demo_versions()


def _demo_versions() -> list[dict]:
    releases = [
        "1.21.4", "1.21.3", "1.21.1", "1.20.6", "1.20.4",
        "1.20.2", "1.20.1", "1.19.4", "1.19.2", "1.18.2",
        "1.17.1", "1.16.5", "1.12.2", "1.8.9", "1.7.10",
    ]
    return [{"id": v, "type": "release", "url": ""} for v in releases]


def get_installed_versions() -> list[str]:
    installed = {i.get("mc_version", "") for i in list_instances()}
    mc_dir = config.get("minecraft_dir")
    if not MLL_AVAILABLE or not mc_dir:
        return sorted(v for v in installed if v)
    try:
        installed.update(v for v in _get_installed_versions_cached(mc_dir) if v)
    except Exception as exc:
        log.warning("Installed version scan failed: %s", exc)
    return sorted(v for v in installed if v)


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

_XMX_PREFIXES = ("-Xmx", "-Xms")


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
    version_id = validate_version_id(version_id)
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

    forge_ver = deps.get("forge")
    if forge_ver:
        full_ver = f"{mc_version}-{forge_ver}"
        _cb(0, 1, f"Installing Forge {forge_ver} for {mc_version}…")
        java_path = config.get("java_path") or None
        try:
            mll.forge.install_forge_version(full_ver, mc_dir, callbacks, java=java_path)
            return mll.forge.forge_to_installed_version(full_ver)
        except Exception as exc:
            log.warning("Forge install failed for %s: %s", full_ver, exc)

    neoforge_ver = deps.get("neoforge")
    if neoforge_ver:
        log.warning(
            "NeoForge %s detected in mrpack but is not yet supported by this MLL version; "
            "launching with base Minecraft %s.", neoforge_ver, mc_version
        )

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
        self.version_id = validate_version_id(version_id)
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        if not MLL_AVAILABLE:
            self.finished.emit(False, "minecraft-launcher-lib is not installed.")
            return
        instance = create_vanilla_instance(self.version_id)
        mc_dir = instance["directory"]
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
            invalidate_installed_cache(mc_dir)
            self.finished.emit(True, f"Version {self.version_id} installed successfully.")
        except Exception as exc:
            log.exception("Minecraft version install failed for %s", self.version_id)
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
        username:    str = "Player",
        parent:      Optional[QObject] = None,
        instance_id: str = "",
        server_ip:   str = "",
        server_port: str = "",
    ) -> None:
        super().__init__(parent)
        self.version_id  = validate_version_id(version_id)
        self.username    = username
        self.instance_id = instance_id
        self.server_ip   = server_ip
        self.server_port = server_port
        self._thread:  Optional[threading.Thread]  = None
        self._process: Optional[subprocess.Popen]  = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def terminate(self, timeout: float = 10.0) -> bool:
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=timeout)
                return True
            except subprocess.TimeoutExpired:
                self._process.kill()
                try:
                    self._process.wait(timeout=5)
                    return True
                except subprocess.TimeoutExpired:
                    return False
        return True

    def _run(self) -> None:
        if not MLL_AVAILABLE:
            self.error.emit("minecraft-launcher-lib is not installed.")
            return

        instance = find_instance(self.instance_id) if self.instance_id else find_instance_for_version(self.version_id)
        mc_dir = instance.get("directory") if instance else config.get("minecraft_dir")
        if not Path(mc_dir).exists():
            self.error.emit(f"Version {self.version_id} is not installed. Install it from Instances first.")
            return
        try:
            installed = _get_installed_versions_cached(mc_dir)
        except Exception as exc:
            log.warning("Installed-version scan failed for %s: %s", mc_dir, exc)
            self.error.emit(f"Could not verify installed versions in {mc_dir}.")
            return
        if self.version_id not in installed:
            self.error.emit(
                f"Version {self.version_id} is not installed in this instance. "
                "Install or repair the instance first."
            )
            return
        java = config.get("java_path") or find_best_java(required_java_for_mc(self.version_id))
        if not java:
            self.error.emit("No compatible Java installation was found. Set Java in Settings.")
            return
        ram    = config.get("ram_mb", 4096)
        width  = config.get("resolution_width", 1280)
        height = config.get("resolution_height", 720)
        fullscreen = config.get("fullscreen", False)

        # Online Minecraft requires passing the bearer token in the child process
        # arguments. Keep the privacy-safe offline token path as the default.
        online_token_allowed = config.get("allow_online_launch_token", False)
        if online_token_allowed and auth_manager.is_logged_in and auth_manager.username == self.username:
            if not auth_manager.ensure_token_fresh(force=True):
                self.error.emit(
                    "Microsoft session refresh failed. Please sign in again before launching online."
                )
                return
            token = auth_manager.access_token
            uid   = auth_manager.uuid or _offline_uuid(self.username)
        else:
            if auth_manager.is_logged_in and auth_manager.username == self.username:
                self.status_changed.emit("Launching without exposing the Microsoft access token...")
            token = "offline"
            uid   = _offline_uuid(self.username)

        # JVM args with deduplication (B-Y-007)
        preset_key  = config.get("jvm_preset", "performance")
        preset_args = get_preset_args(preset_key)
        custom_args = (instance or {}).get("jvm_args", "") or config.get("jvm_args", "")
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
            "fullscreen":       fullscreen,
        }

        try:
            log_fh = None
            self.status_changed.emit("Building launch command...")
            command = mll.command.get_minecraft_command(
                version=self.version_id,
                minecraft_directory=mc_dir,
                options=options,
            )
            if self.server_ip:
                command.extend(["--server", self.server_ip,
                                 "--port", self.server_port or "25565"])
            self.status_changed.emit("Starting Minecraft...")
            safe_version = safe_path_segment(self.version_id, "version")
            log_path = LOGS_DIR / f"minecraft-{safe_version}.log"
            log_fh = open(log_path, "a", encoding="utf-8", errors="replace")
            self._process = subprocess.Popen(
                command,
                stdout=log_fh,
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
        finally:
            if log_fh is not None:
                log_fh.close()
