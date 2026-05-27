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

    def test_modpacks_tab_constructs(self) -> None:
        from src.ui.tabs.modpacks_tab import ModpacksTab

        with patch.object(ModpacksTab, "_execute_search", lambda self: None), patch.object(ModpacksTab, "_load_discovery", lambda self: None), patch.object(ModpacksTab, "_load_version_choices", lambda self: None):
            tab = ModpacksTab()
            self.assertIsNotNone(tab)
            self.assertIsNotNone(tab._version_filter)
            tab.close()
            tab.deleteLater()
            self.app.processEvents()

    def test_shaders_tab_constructs(self) -> None:
        from src.ui.tabs.shaders_tab import ShadersTab

        with patch.object(ShadersTab, "_refresh_installed", lambda self: None), patch.object(ShadersTab, "_load_version_choices", lambda self: None):
            tab = ShadersTab()
            self.assertIsNotNone(tab)
            self.assertIsNotNone(tab._shader_ver)
            tab.close()
            tab.deleteLater()
            self.app.processEvents()

    def test_mods_tab_constructs(self) -> None:
        from src.ui.tabs.mods_tab import ModsTab

        with patch.object(ModsTab, "refresh_instances", lambda self: None):
            tab = ModsTab()
            self.assertIsNotNone(tab)
            self.assertIsNotNone(tab._source_combo)
            tab.close()
            tab.deleteLater()
            self.app.processEvents()

    def test_modpack_card_install_states(self) -> None:
        from PySide6.QtWidgets import QPushButton
        from src.ui.tabs.modpacks_tab import ModpackCard

        project = {
            "id": "sample",
            "title": "Sample Pack",
            "description": "Sample",
            "author": "Tester",
            "downloads": 1,
            "categories": [],
            "source": "modrinth",
        }
        card = ModpackCard(project)
        button = card.findChild(QPushButton)
        self.assertIsNotNone(button)

        card.set_installing("Fetching...")
        self.assertFalse(button.isEnabled())

        card.set_ready()
        self.assertTrue(button.isEnabled())
        self.assertEqual(button.text(), "Install")

        card.set_installed()
        self.assertFalse(button.isEnabled())
        self.assertEqual(button.text(), "Installed")

        card.close()
        card.deleteLater()
        self.app.processEvents()

    def test_modpacks_tab_state_updates_apply_to_discovery_and_results(self) -> None:
        from src.ui.tabs.modpacks_tab import ModpackCard, ModpacksTab

        project = {
            "id": "sample-pack",
            "title": "Sample Pack",
            "description": "Sample",
            "author": "Tester",
            "downloads": 1,
            "categories": [],
            "source": "modrinth",
        }
        with patch.object(ModpacksTab, "_execute_search", lambda self: None), patch.object(ModpacksTab, "_load_discovery", lambda self: None), patch.object(ModpacksTab, "_load_version_choices", lambda self: None):
            tab = ModpacksTab()
            results_card = ModpackCard(project)
            discovery_card = ModpackCard(project)
            tab._current_cards["sample-pack"] = results_card
            tab._discovery_cards["sample-pack"] = discovery_card

            tab._set_project_install_state("sample-pack", "installing", "50%")
            self.assertFalse(results_card._install_btn.isEnabled())
            self.assertFalse(discovery_card._install_btn.isEnabled())

            tab._set_project_install_state("sample-pack", "ready")
            self.assertTrue(results_card._install_btn.isEnabled())
            self.assertTrue(discovery_card._install_btn.isEnabled())

            tab._set_project_install_state("sample-pack", "installed")
            self.assertEqual(results_card._install_btn.text(), "Installed")
            self.assertEqual(discovery_card._install_btn.text(), "Installed")

            for widget in (results_card, discovery_card, tab):
                widget.close()
                widget.deleteLater()
            self.app.processEvents()

    def test_modpacks_results_skip_missing_id_and_disable_curseforge_installs(self) -> None:
        from src.ui.tabs.modpacks_tab import ModpacksTab

        hits = [
            {
                "title": "Missing Id",
                "description": "Bad entry",
                "author": "Tester",
                "downloads": 1,
                "categories": [],
            },
            {
                "id": 42,
                "title": "CF Pack",
                "description": "CurseForge source",
                "author": "Tester",
                "downloads": 1,
                "categories": [],
                "source": "curseforge",
            },
        ]
        with patch.object(ModpacksTab, "_execute_search", lambda self: None), patch.object(ModpacksTab, "_load_discovery", lambda self: None), patch.object(ModpacksTab, "_load_version_choices", lambda self: None):
            tab = ModpacksTab()
            tab._on_results(tab._search_generation, hits, 2)
            self.assertNotIn("", tab._current_cards)
            self.assertIn("42", tab._current_cards)
            self.assertEqual(tab._current_cards["42"]._install_btn.text(), "Unavailable")
            self.assertFalse(tab._current_cards["42"]._install_btn.isEnabled())

            tab._on_install_requested(hits[1])
            self.assertIn("not supported", tab._status_label.text().lower())
            self.assertNotIn("42", tab._active_installs)

            tab.close()
            tab.deleteLater()
            self.app.processEvents()

    def test_shader_card_install_states(self) -> None:
        from PySide6.QtWidgets import QPushButton
        from src.ui.tabs.shaders_tab import ShaderCard

        project = {"id": "shader-1", "title": "Example", "description": "Example", "author": "Tester", "downloads": 1}
        card = ShaderCard(project)
        button = card.findChild(QPushButton)
        self.assertIsNotNone(button)

        card.set_installing("Fetching...")
        self.assertFalse(button.isEnabled())

        card.set_ready()
        self.assertTrue(button.isEnabled())
        self.assertEqual(button.text(), "Install")

        card.set_installed()
        self.assertFalse(button.isEnabled())
        self.assertEqual(button.text(), "Installed")

        card.close()
        card.deleteLater()
        self.app.processEvents()

    def test_shaders_tab_version_fetch_error_resets_button_state(self) -> None:
        from src.ui.tabs.shaders_tab import ShaderCard, ShadersTab

        project = {"id": "shader-1", "title": "Example", "description": "Example", "author": "Tester", "downloads": 1}
        with patch.object(ShadersTab, "_refresh_installed", lambda self: None), patch.object(ShadersTab, "_load_version_choices", lambda self: None):
            tab = ShadersTab()
            card = ShaderCard(project)
            card.set_installing("Fetching...")
            tab._shader_cards["shader-1"] = card
            tab._active_shader_installs.add("shader-1")

            tab._on_shader_version_fetch_error("shader-1", "network failed")

            self.assertNotIn("shader-1", tab._active_shader_installs)
            self.assertEqual(card._install_btn.text(), "Install")
            self.assertTrue(card._install_btn.isEnabled())
            self.assertIn("network failed", tab._shader_status.text())

            for widget in (card, tab):
                widget.close()
                widget.deleteLater()
            self.app.processEvents()

    def test_main_window_constructs(self) -> None:
        from src.ui.main_window import MainWindow
        from src.ui.tabs.home_tab import HomeTab
        from src.ui.tabs.instances_tab import InstancesTab
        from src.ui.tabs.mods_tab import ModsTab
        from src.ui.tabs.modpacks_tab import ModpacksTab
        from src.ui.tabs.shaders_tab import ShadersTab
        from src.ui.tabs.accounts_tab import AccountsTab
        from src.ui.tabs.settings_tab import SettingsTab

        with patch.object(HomeTab, "_load_versions", lambda self, *args, **kwargs: None), patch.object(HomeTab, "_load_news", lambda self: None), patch.object(InstancesTab, "_load_versions", lambda self, *args, **kwargs: None), patch.object(ModsTab, "refresh_instances", lambda self: None), patch.object(ModpacksTab, "_execute_search", lambda self: None), patch.object(ModpacksTab, "_load_discovery", lambda self: None), patch.object(ModpacksTab, "_load_version_choices", lambda self: None), patch.object(ShadersTab, "_refresh_installed", lambda self: None), patch.object(ShadersTab, "_load_version_choices", lambda self: None), patch.object(AccountsTab, "_refresh_state", lambda self: None), patch.object(SettingsTab, "_load_java_installs_async", lambda self: None):
            win = MainWindow()
            self.assertIsNotNone(win)
            self.assertIsNotNone(win._tabs)
            expected_types = {
                "home": "HomeTab",
                "instances": "InstancesTab",
                "mods": "ModsTab",
                "modpacks": "ModpacksTab",
                "shaders": "ShadersTab",
                "servers": "ServersTab",
                "accounts": "AccountsTab",
                "settings": "SettingsTab",
            }
            for key in ("instances", "mods", "modpacks", "shaders", "servers", "accounts", "settings", "home"):
                win._top_nav._buttons[key].click()
                current = win._content.stack.currentWidget()
                self.assertEqual(type(current).__name__, expected_types[key])
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
        from src.ui.tabs.mods_tab import ModCard, _infer_instance_loader
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

        self.assertEqual(
            _infer_instance_loader({"mc_version": "fabric-loader-0.16.9-1.21.4"}),
            "fabric",
        )
        self.assertEqual(
            _infer_instance_loader({"launch_version_id": "quilt-loader-0.25.0-1.21.4"}),
            "quilt",
        )


if __name__ == "__main__":
    unittest.main()
