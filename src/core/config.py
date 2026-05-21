"""
Persistent configuration management for GenosLauncher.
Reads and writes a JSON config file in the user's app-data directory.
"""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any


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

DEFAULT_CONFIG: dict[str, Any] = {
    "version": "0.1.0",
    "minecraft_dir": str(APP_DIR / "minecraft"),
    "java_path": "",
    "ram_mb": 4096,
    "resolution_width": 1280,
    "resolution_height": 720,
    "fullscreen": False,
    "close_on_launch": False,
    "selected_version": "",
    "last_account": "",
    "accounts": [],
    "instances": [],
    "theme": "dark",
    "accent_color": "#00E5FF",
    "show_snapshots": False,
    "show_old_versions": False,
    "jvm_args": "",
    "window_width": 1280,
    "window_height": 760,
}


class Config:
    """Thread-safe, auto-saving configuration store."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._ensure_dirs()
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULT_CONFIG.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def update(self, mapping: dict[str, Any]) -> None:
        self._data.update(mapping)
        self._save()

    def __getitem__(self, key: str) -> Any:
        return self._data.get(key, DEFAULT_CONFIG[key])

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        for d in (APP_DIR, INSTANCES_DIR, LOGS_DIR):
            d.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                # Merge defaults so new keys are always present
                self._data = {**DEFAULT_CONFIG, **stored}
                return
            except (json.JSONDecodeError, OSError):
                pass
        self._data = dict(DEFAULT_CONFIG)
        self._save()

    def _save(self) -> None:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            print(f"[Config] Failed to save: {exc}")


# Module-level singleton — import and use directly
config = Config()
