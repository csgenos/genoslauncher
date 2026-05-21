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

# Keys that must never be persisted to config.json (tokens live in keyring only)
_SENSITIVE_KEYS: frozenset[str] = frozenset({"access_token", "refresh_token"})

DEFAULT_CONFIG: dict[str, Any] = {
    "version": "0.2.0",
    "minecraft_dir": str(APP_DIR / "minecraft"),
    "java_path": "",
    "ram_mb": 4096,
    "resolution_width": 1280,
    "resolution_height": 720,
    "fullscreen": False,
    "close_on_launch": False,
    "selected_version": "",
    "last_account": "",
    "offline_accounts": [],
    "instances": [],
    "show_snapshots": False,
    "show_old_versions": False,
    "jvm_args": "",
    "jvm_preset": "performance",
    "azure_client_id": "",
    "auth_redirect_port": 8090,
    "window_width": 1280,
    "window_height": 760,
}

# Keys whose types are enforced (basic schema validation)
_SCHEMA: dict[str, type | tuple] = {
    "ram_mb":             int,
    "resolution_width":   int,
    "resolution_height":  int,
    "fullscreen":         bool,
    "close_on_launch":    bool,
    "show_snapshots":     bool,
    "show_old_versions":  bool,
    "auth_redirect_port": int,
    "window_width":       int,
    "window_height":      int,
    "jvm_args":           str,
    "jvm_preset":         str,
    "azure_client_id":    str,
    "java_path":          str,
    "last_account":       str,
    "offline_accounts":   list,
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
        with self._lock:
            return self._data.get(key, DEFAULT_CONFIG.get(key, default))

    def set(self, key: str, value: Any) -> None:
        if key in _SENSITIVE_KEYS:
            return
        with self._lock:
            self._data[key] = self._validate_value(key, value)
            self._save_locked()

    def update(self, mapping: dict[str, Any]) -> None:
        with self._lock:
            for k, v in mapping.items():
                if k not in _SENSITIVE_KEYS:
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
            return max(1024, min(int(val), 65535))
        if key == "offline_accounts" and isinstance(val, list):
            unique = []
            seen = set()
            for x in val:
                if isinstance(x, str) and x.strip() and x not in seen:
                    unique.append(str(x)[:32])
                    seen.add(x)
            return unique[:50]
        if key == "instances" and isinstance(val, list):
            clean: list[dict] = []
            for item in val:
                if isinstance(item, dict) and item.get("name") and item.get("directory"):
                    clean.append(item)
            return clean[:200]
        return val

    def _validate(self, data: dict) -> dict:
        """Apply a strict known-key schema; fall back to defaults on error."""
        out = dict(DEFAULT_CONFIG)
        for key, val in data.items():
            if key in _SENSITIVE_KEYS:
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
                    self._data = self._validate(stored)
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
        safe_data = {k: v for k, v in self._data.items() if k not in _SENSITIVE_KEYS}
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


# Module-level singleton — import and use directly
config = Config()
