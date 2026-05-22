"""Central logging setup for GenosLauncher."""

from __future__ import annotations

import logging
import os
import platform
from logging.handlers import RotatingFileHandler

from .config import LOGS_DIR


def setup_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / "genoslauncher.log"
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    if platform.system() != "Windows":
        try:
            os.chmod(log_path, 0o600)
        except OSError:
            pass
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    ))
    root.addHandler(handler)
