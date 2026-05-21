"""
GenosLauncher entry point.

Run with:  python src/main.py
Build with: build.bat
"""

from __future__ import annotations

import os
import sys

# Ensure the src/ directory is on the path when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def main() -> int:
    # Enable high-DPI scaling
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("GenosLauncher")
    app.setApplicationDisplayName("GenosLauncher")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("GenosLauncher")

    # Default font
    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)

    # App icon (will gracefully skip if file missing)
    icon_path = os.path.join(
        os.path.dirname(__file__), "resources", "icons", "app_icon.png"
    )
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
