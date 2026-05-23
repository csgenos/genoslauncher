from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - environment dependent
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 is not available in this test environment.")
class UISmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_home_tab_constructs(self) -> None:
        from src.ui.tabs.home_tab import HomeTab

        with patch.object(HomeTab, "_load_versions", lambda self: None), patch.object(HomeTab, "_load_news", lambda self: None):
            tab = HomeTab()
            self.assertIsNotNone(tab)
            self.assertIsNotNone(tab._version_combo)
            tab.close()
            tab.deleteLater()
            self.app.processEvents()

    def test_instances_tab_constructs(self) -> None:
        from src.ui.tabs.instances_tab import InstancesTab

        with patch.object(InstancesTab, "_load_versions", lambda self: None):
            tab = InstancesTab()
            self.assertIsNotNone(tab)
            self.assertIsNotNone(tab._instances_layout)
            tab.close()
            tab.deleteLater()
            self.app.processEvents()

    def test_accounts_tab_constructs(self) -> None:
        from src.ui.tabs.accounts_tab import AccountsTab

        tab = AccountsTab()
        self.assertIsNotNone(tab)
        self.assertIsNotNone(tab._accounts_layout)
        tab.close()
        tab.deleteLater()
        self.app.processEvents()

    def test_main_window_constructs(self) -> None:
        from src.ui.main_window import MainWindow
        from src.ui.tabs.home_tab import HomeTab
        from src.ui.tabs.instances_tab import InstancesTab

        with patch.object(HomeTab, "_load_versions", lambda self: None), patch.object(HomeTab, "_load_news", lambda self: None), patch.object(InstancesTab, "_load_versions", lambda self: None):
            win = MainWindow()
            self.assertIsNotNone(win)
            self.assertIsNotNone(win._tabs)
            win.close()
            win.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
