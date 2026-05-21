"""
GenosLauncher entry point.

Run with:  python src/main.py
Build with: build.bat

Fix B-X-014: _resource_path() resolves correctly from both source tree
and PyInstaller onedir bundle (sys._MEIPASS).
"""

from __future__ import annotations

import os
import sys

# Ensure src/ is on sys.path when running directly (not needed in bundled build)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def _resource_path(relative: str) -> str:
    """
    Return the absolute path to a bundled resource.
    Works both when running from source and inside a PyInstaller onedir bundle
    (where sys._MEIPASS points to the extraction directory).
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def main() -> int:
    # High-DPI support
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("GenosLauncher")
    app.setApplicationDisplayName("GenosLauncher")
    app.setApplicationVersion("0.2.0")
    app.setOrganizationName("GenosLauncher")

    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)

    icon_path = _resource_path(os.path.join("resources", "icons", "app_icon.png"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
