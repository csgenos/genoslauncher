"""
Persistent configuration management for GenosLauncher.
Reads and writes a JSON config file in the user's app-data directory.
Fixes: S-Y-003 (atomic writes), S-X-009 (APP_DIR permissions on Linux/Mac).
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from .._version import __version__
from .secure_store import delete_secret, get_secret, set_secret
from .validators import normalize_offline_username

log = logging.getLogger(__name__)


def _get_app_data_dir() -> Path:
    """Return a platform-appropriate directory for app data."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "GenosLauncher"


APP_DIR = _get_app_data_dir()
CONFIG_FILE = APP_DIR / "config.json"
INSTANCES_DIR = APP_DIR / "instances"
LOGS_DIR = APP_DIR / "logs"

# Keys that must never be persisted to config.json.
_SENSITIVE_KEYS: frozenset[str] = frozenset({"access_token", "refresh_token"})
_SECRET_CONFIG_KEYS: frozenset[str] = frozenset({"curseforge_api_key"})

DEFAULT_CONFIG: dict[str, Any] = {
    "version": __version__,
    "minecraft_dir": str(APP_DIR / "minecraft"),
    "java_path": "",
    "ram_mb": 4096,
    "resolution_width": 1280,
    "resolution_height": 720,
    "fullscreen": False,
    "close_on_launch": False,
    "selected_version": "",
    "selected_instance_id": "",
    "last_account": "",
    "offline_accounts": [],
    "instances": [],
    "show_snapshots": False,
    "show_old_versions": False,
    "first_run": True,
    "jvm_args": "",
    "jvm_preset": "performance",
    "window_width": 1280,
    "window_height": 760,
    "dark_mode": False,
    "azure_client_id": "",
    "servers": [],
    "ms_usernames": [],
    "active_ms_username": "",
    "auth_redirect_port": 0,
}

# Keys whose types are enforced (basic schema validation)
_SCHEMA: dict[str, type | tuple] = {
    "version":            str,
    "minecraft_dir":      str,
    "ram_mb":             int,
    "resolution_width":   int,
    "resolution_height":  int,
    "fullscreen":         bool,
    "close_on_launch":    bool,
    "show_snapshots":     bool,
    "show_old_versions":  bool,
    "dark_mode":          bool,
    "first_run":          bool,
    "auth_redirect_port": int,
    "window_width":       int,
    "window_height":      int,
    "jvm_args":           str,
    "jvm_preset":         str,
    "selected_version":   str,
    "selected_instance_id": str,
    "java_path":          str,
    "last_account":       str,
    "offline_accounts":   list,
    "instances":          list,
    "azure_client_id":    str,
    "servers":            list,
    "ms_usernames":       list,
    "active_ms_username": str,
}


class Config:
    """Thread-safe, auto-saving configuration store."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._ensure_dirs()
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        if key in _SECRET_CONFIG_KEYS:
            return get_secret(APP_DIR, key) or default or ""
        with self._lock:
            return self._data.get(key, DEFAULT_CONFIG.get(key, default))

    def set(self, key: str, value: Any) -> None:
        if key in _SENSITIVE_KEYS:
            return
        if key in _SECRET_CONFIG_KEYS:
            secret_value = str(value or "")
            if secret_value:
                set_secret(APP_DIR, key, secret_value)
            else:
                delete_secret(APP_DIR, key)
            return
        with self._lock:
            self._data[key] = self._validate_value(key, value)
            self._save_locked()

    def update(self, mapping: dict[str, Any]) -> None:
        with self._lock:
            for k, v in mapping.items():
                if k in _SECRET_CONFIG_KEYS:
                    secret_value = str(v or "")
                    if secret_value:
                        set_secret(APP_DIR, k, secret_value)
                    else:
                        delete_secret(APP_DIR, k)
                elif k not in _SENSITIVE_KEYS:
                    self._data[k] = self._validate_value(k, v)
            self._save_locked()

    def __getitem__(self, key: str) -> Any:
        with self._lock:
            return self._data.get(key, DEFAULT_CONFIG[key])

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        for d in (APP_DIR, INSTANCES_DIR, LOGS_DIR):
            d.mkdir(parents=True, exist_ok=True)
        # Restrict APP_DIR to owner-only on non-Windows (S-X-009)
        if platform.system() != "Windows":
            try:
                os.chmod(APP_DIR, 0o700)
            except OSError:
                pass

    def _validate_value(self, key: str, val: Any) -> Any:
        expected = _SCHEMA.get(key)
        if expected is bool and not isinstance(val, bool):
            if isinstance(val, str):
                return val.strip().lower() in {"1", "true", "yes", "on"}
            return bool(val)
        if expected is not None and not isinstance(val, expected):
            try:
                val = expected(val) if not isinstance(expected, tuple) else DEFAULT_CONFIG.get(key)
            except (TypeError, ValueError):
                return DEFAULT_CONFIG.get(key)

        if key in {"ram_mb"}:
            return max(512, min(int(val), 32768))
        if key in {"resolution_width", "window_width"}:
            return max(320, min(int(val), 7680))
        if key in {"resolution_height", "window_height"}:
            return max(240, min(int(val), 4320))
        if key == "auth_redirect_port":
            if not int(val):
                return 0
            return max(1024, min(int(val), 65535))
        if key in {"offline_accounts", "ms_usernames"} and isinstance(val, list):
            unique = []
            seen = set()
            for x in val:
                if not isinstance(x, str):
                    continue
                clean = normalize_offline_username(x) if key == "offline_accounts" else str(x).strip()[:32]
                if clean and clean not in seen:
                    unique.append(clean)
                    seen.add(clean)
            return unique[:50]
        if key == "instances" and isinstance(val, list):
            clean: list[dict] = []
            for item in val:
                if isinstance(item, dict) and item.get("name") and item.get("directory"):
                    clean.append(item)
            return clean[:200]
        if key == "servers" and isinstance(val, list):
            clean_servers: list[dict] = []
            for item in val:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()[:80]
                ip = str(item.get("ip", "")).strip()[:255]
                if not name or not ip:
                    continue
                try:
                    port = int(item.get("port", 25565))
                except (TypeError, ValueError):
                    port = 25565
                clean_servers.append({
                    "name": name,
                    "ip": ip,
                    "port": max(1, min(port, 65535)),
                })
            return clean_servers[:200]
        return val

    def _validate(self, data: dict) -> dict:
        """Apply a strict known-key schema; fall back to defaults on error."""
        out = dict(DEFAULT_CONFIG)
        for key, val in data.items():
            if key in _SENSITIVE_KEYS or key in _SECRET_CONFIG_KEYS:
                continue
            expected = _SCHEMA.get(key)
            if expected is None and key not in DEFAULT_CONFIG:
                continue
            out[key] = self._validate_value(key, val)
        return out

    def _load(self) -> None:
        with self._lock:
            if CONFIG_FILE.exists():
                try:
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        stored = json.load(f)
                    migrated_secret = False
                    legacy_cf_key = stored.pop("curseforge_api_key", "")
                    if isinstance(legacy_cf_key, str) and legacy_cf_key.strip():
                        set_secret(APP_DIR, "curseforge_api_key", legacy_cf_key.strip())
                        migrated_secret = True
                    self._data = self._validate(stored)
                    if migrated_secret:
                        self._save_locked()
                    return
                except (json.JSONDecodeError, OSError):
                    try:
                        backup = CONFIG_FILE.with_suffix(f".corrupt-{int(time.time())}.json")
                        shutil.copy2(CONFIG_FILE, backup)
                    except OSError:
                        pass
                    pass
            self._data = dict(DEFAULT_CONFIG)
            self._save_locked()

    def _save(self) -> None:
        with self._lock:
            self._save_locked()

    def _save_locked(self) -> None:
        """Atomic write: write to .tmp then os.replace() to avoid partial reads."""
        safe_data = {
            k: v for k, v in self._data.items()
            if k not in _SENSITIVE_KEYS and k not in _SECRET_CONFIG_KEYS
        }
        tmp = CONFIG_FILE.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(safe_data, f, indent=2, ensure_ascii=False)
            tmp.replace(CONFIG_FILE)
        except OSError as exc:
            log.error("Failed to save config: %s", exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


# Module-level singleton - import and use directly
config = Config()
