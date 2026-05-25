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

        with patch.object(HomeTab, "_load_versions", lambda self, *args, **kwargs: None), patch.object(HomeTab, "_load_news", lambda self: None):
            tab = HomeTab()
            self.assertIsNotNone(tab)
            self.assertIsNotNone(tab._version_combo)
            tab.close()
            tab.deleteLater()
            self.app.processEvents()

    def test_instances_tab_constructs(self) -> None:
        from src.ui.tabs.instances_tab import InstancesTab

        with patch.object(InstancesTab, "_load_versions", lambda self, *args, **kwargs: None):
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

        with patch.object(HomeTab, "_load_versions", lambda self, *args, **kwargs: None), patch.object(HomeTab, "_load_news", lambda self: None), patch.object(InstancesTab, "_load_versions", lambda self, *args, **kwargs: None):
            win = MainWindow()
            self.assertIsNotNone(win)
            self.assertIsNotNone(win._tabs)
            win.close()
            win.deleteLater()
            self.app.processEvents()

    def test_theme_modes_apply(self) -> None:
        from src.ui.styles import apply_theme, current_theme_mode

        for mode in ("light", "dark", "system"):
            apply_theme(mode)
            self.assertIn(current_theme_mode(), {"light", "dark"})

    def test_themed_combo_uses_custom_popup_view(self) -> None:
        from PySide6.QtWidgets import QListView
        from src.ui.components.themed_controls import GComboBox

        combo = GComboBox()
        combo.addItems(["Modrinth", "CurseForge"])
        self.assertIsInstance(combo.view(), QListView)
        self.assertIn("background", combo.view().styleSheet())
        combo.close()
        combo.deleteLater()
        self.app.processEvents()

    def test_install_buttons_emit_from_cards(self) -> None:
        from PySide6.QtWidgets import QPushButton
        from src.ui.components.version_card import VersionCard
        from src.ui.tabs.mods_tab import ModCard
        from src.ui.tabs.shaders_tab import ShaderCard

        version_hits: list[str] = []
        version = VersionCard("1.21.4", is_installed=False)
        version.install_requested.connect(version_hits.append)
        version.findChild(QPushButton).click()
        self.assertEqual(version_hits, ["1.21.4"])

        project = {"title": "Example", "description": "Example", "author": "Tester", "downloads": 1}
        mod_hits: list[dict] = []
        mod = ModCard(project)
        mod.install_requested.connect(mod_hits.append)
        mod.findChildren(QPushButton)[0].click()
        self.assertEqual(mod_hits, [project])

        shader_hits: list[dict] = []
        shader = ShaderCard(project)
        shader.install_requested.connect(shader_hits.append)
        shader.findChild(QPushButton).click()
        self.assertEqual(shader_hits, [project])

        for widget in (version, mod, shader):
            widget.close()
            widget.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
