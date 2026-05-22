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
import traceback

# Ensure src/ is on sys.path when running directly (not needed in bundled build)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QCoreApplication, QDialog, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from src._version import __version__
from src.core.config import LOGS_DIR, config
from src.core.logging_setup import setup_logging


def _resource_path(relative: str) -> str:
    """
    Return the absolute path to a bundled resource.
    Works both when running from source and inside a PyInstaller onedir bundle
    (where sys._MEIPASS points to the extraction directory).
    """
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def _fallback_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#111827"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", 28, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "G")
    painter.end()
    return QIcon(pixmap)


def main() -> int:
    setup_logging()
    # High-DPI support
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("GenosLauncher")
    app.setApplicationDisplayName("GenosLauncher")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("GenosLauncher")

    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)

    icon_path = _resource_path(os.path.join("assets", "icons", "app_icon.png"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        app.setWindowIcon(_fallback_icon())

    # Apply saved theme before any windows open
    from src.ui.styles import apply_theme
    apply_theme(config.get("dark_mode", False))

    # ── Splash screen ────────────────────────────────────────────────────
    from src.ui.splash_screen import SplashScreen
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    first_run = config.get("first_run", True)

    def _open_main() -> None:
        try:
            from src.ui.main_window import MainWindow
            w = MainWindow()
            w.show()
        except Exception:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            crash_log = LOGS_DIR / "startup-crash.log"
            crash_log.write_text(traceback.format_exc(), encoding="utf-8")
            QMessageBox.critical(
                None,
                "GenosLauncher failed to start",
                f"Startup failed. Details were written to:\n{crash_log}",
            )

    if first_run:
        # Brief splash (600 ms) then wizard
        def _show_wizard() -> None:
            splash.close_animated(lambda: _run_wizard())

        def _run_wizard() -> None:
            from src.ui.setup_wizard import SetupWizard
            wizard = SetupWizard()
            if wizard.exec() == QDialog.Accepted:
                _open_main()
            else:
                app.quit()

        QTimer.singleShot(600, _show_wizard)
    else:
        # Normal launch — splash for 1400 ms then main window
        QTimer.singleShot(1400, lambda: splash.close_animated(_open_main))

    try:
        return app.exec()
    except Exception:
        crash_log = LOGS_DIR / "runtime-crash.log"
        crash_log.write_text(traceback.format_exc(), encoding="utf-8")
        QMessageBox.critical(
            None,
            "GenosLauncher crashed",
            f"The app crashed. Details were written to:\n{crash_log}",
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
