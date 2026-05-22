"""
Instances tab — browse, install, and manage Minecraft versions.
Fixes:
  - Reads show_snapshots/show_old_versions from config on startup (#7)
  - Install button on VersionCard triggers real InstallWorker (#2)
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QObject, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QInputDialog,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtWidgets import QFileDialog, QMenu

from ..styles import COLORS as C, FONT
from ..components.animated_button import OutlineButton
from ..components.version_card import VersionCard
from ..dialogs.crash_dialog import CrashReportDialog
from ..dialogs.screenshot_dialog import ScreenshotGalleryDialog
from ..dialogs.backup_dialog import WorldBackupDialog
from ...core.launcher import InstallWorker, get_available_versions, get_installed_versions, install_minecraft_base
from ...core.config import config
from ...core.instances import (
    clone_instance,
    create_custom_instance,
    import_prism_instances,
    list_instances,
    remove_instance,
    set_selected_instance,
    update_instance,
)
from ...core.validators import validate_version_id

log = logging.getLogger(__name__)


class _VersionLoader(QObject):
    """Loads version list off the UI thread."""
    done = Signal(list, list)   # all_versions, installed_ids

    def __init__(self, include_snapshots: bool, include_old: bool) -> None:
        super().__init__()
        self._snapshots = include_snapshots
        self._old = include_old

    def run(self) -> None:
        versions = get_available_versions(
            include_snapshots=self._snapshots,
            include_old=self._old,
        )
        try:
            installed = get_installed_versions()
        except Exception as exc:
            log.warning("Installed version load failed: %s", exc.__class__.__name__)
            installed = []
        self.done.emit(versions, installed)


class _RepairWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(bool, str)

    def __init__(self, instance: dict) -> None:
        super().__init__()
        self._instance = instance

    def run(self) -> None:
        try:
            version = self._instance.get("mc_version", "")
            directory = self._instance.get("directory", "")
            if not version or not directory:
                raise RuntimeError("Instance is missing version or directory.")
            install_minecraft_base(version, directory, self.progress.emit)
            self.finished.emit(True, f"Repaired {self._instance.get('name', 'instance')}.")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class InstancesTab(QWidget):
    """Browse all available Minecraft versions with filtering."""

    launch_requested = Signal(str)
    instance_launch_requested = Signal(str, str)
    install_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Restore persisted filter state (#7)
        self._show_snapshots = config.get("show_snapshots", False)
        self._show_old       = config.get("show_old_versions", False)
        self._all_versions:   list[dict]  = []
        self._installed:      set[str]    = set()
        self._search_text     = ""
        self._load_threads:   list[QThread] = []
        self._load_workers:   list[QObject] = []
        self._install_workers: dict[str, InstallWorker] = {}
        self._repair_threads: list[QThread] = []
        self._repair_workers: list[_RepairWorker] = []
        self._build_ui()
        QTimer.singleShot(100, self._load_versions)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 32, 48, 32)
        root.setSpacing(24)

        header_row = QHBoxLayout()
        title = QLabel("Instances")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        header_row.addWidget(title)
        header_row.addStretch()

        refresh_btn = OutlineButton("↻  Refresh")
        refresh_btn.setFixedHeight(34)
        refresh_btn.setFixedWidth(110)
        refresh_btn.clicked.connect(self._load_versions)
        header_row.addWidget(refresh_btn)
        new_btn = OutlineButton("New Instance")
        new_btn.setFixedHeight(34)
        new_btn.setFixedWidth(132)
        new_btn.clicked.connect(self._create_instance)
        header_row.addWidget(new_btn)

        import_btn = OutlineButton("Import…")
        import_btn.setFixedHeight(34)
        import_btn.setFixedWidth(100)
        import_btn.clicked.connect(self._import_instances)
        header_row.addWidget(import_btn)

        root.addLayout(header_row)

        self._instances_title = QLabel("Installed Instances")
        self._instances_title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        root.addWidget(self._instances_title)

        self._instances_container = QWidget()
        self._instances_container.setStyleSheet("background: transparent;")
        self._instances_layout = QVBoxLayout(self._instances_container)
        self._instances_layout.setContentsMargins(0, 0, 0, 0)
        self._instances_layout.setSpacing(8)
        root.addWidget(self._instances_container)

        versions_title = QLabel("Available Versions")
        versions_title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        root.addWidget(versions_title)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search versions…")
        self._search_box.setFixedHeight(38)
        self._search_box.textChanged.connect(self._on_search)
        filter_row.addWidget(self._search_box)

        self._snap_check = QCheckBox("Snapshots")
        self._snap_check.setChecked(self._show_snapshots)
        self._snap_check.toggled.connect(self._on_filter_changed)
        filter_row.addWidget(self._snap_check)

        self._old_check = QCheckBox("Legacy")
        self._old_check.setChecked(self._show_old)
        self._old_check.toggled.connect(self._on_filter_changed)
        filter_row.addWidget(self._old_check)

        root.addLayout(filter_row)

        # Status doubles as install progress display
        self._count_label = QLabel("Loading versions...")
        self._count_label.setStyleSheet(f"color: {C['text_secondary']}; font-size: {FONT['sm']};")
        root.addWidget(self._count_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._versions_container = QWidget()
        self._versions_container.setStyleSheet("background: transparent;")
        self._versions_layout = QVBoxLayout(self._versions_container)
        self._versions_layout.setSpacing(10)
        self._versions_layout.setContentsMargins(0, 0, 8, 0)
        self._versions_layout.addStretch()

        self._scroll.setWidget(self._versions_container)
        root.addWidget(self._scroll)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_versions(self) -> None:
        self._count_label.setText("Loading versions…")
        thread = QThread(self)
        worker = _VersionLoader(self._show_snapshots, self._show_old)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_versions_loaded)
        worker.done.connect(thread.quit)
        thread.finished.connect(
            lambda: self._load_threads.remove(thread)
            if thread in self._load_threads else None
        )
        thread.finished.connect(lambda: self._load_workers.remove(worker) if worker in self._load_workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._load_threads.append(thread)
        self._load_workers.append(worker)
        thread.start()

    def _on_versions_loaded(self, versions: list[dict], installed: list[str]) -> None:
        self._all_versions = versions
        self._installed = set(installed)
        self._render_versions()
        self._render_instances()

    def _render_instances(self) -> None:
        while self._instances_layout.count():
            item = self._instances_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        instances = list_instances()
        active_id = config.get("selected_instance_id", "")
        if not instances:
            empty = QLabel("No instances installed yet. Install a version below to create one.")
            empty.setStyleSheet(f"color: {C['text_tertiary']}; font-size: {FONT['sm']};")
            self._instances_layout.addWidget(empty)
            return
        for instance in instances[:20]:
            row = QWidget()
            row.setStyleSheet(f"background: {C['bg_primary']}; border: 1px solid {C['border']}; border-radius: 8px;")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(14, 10, 14, 10)
            active = "Active  -  " if instance.get("id") == active_id else ""
            name = QLabel(f"{active}{instance.get('name', 'Instance')}  -  {instance.get('mc_version', '?')}")
            name.setStyleSheet(f"color: {C['text_primary']}; font-size: {FONT['md']}; font-weight: 600;")
            layout.addWidget(name, 1)
            select = QPushButton("Use")
            select.setFixedWidth(58)
            select.clicked.connect(lambda _=False, i=instance: self._select_instance(i))
            layout.addWidget(select)
            launch = QPushButton("Launch")
            launch.setFixedWidth(80)
            launch.clicked.connect(
                lambda _=False, i=instance: self.instance_launch_requested.emit(
                    i.get("mc_version", ""), i.get("id", "")
                )
            )
            layout.addWidget(launch)
            more_btn = OutlineButton("⋯")
            more_btn.setFixedWidth(38)
            more_btn.clicked.connect(lambda _=False, i=instance, b=more_btn: self._show_instance_menu(i, b))
            layout.addWidget(more_btn)
            self._instances_layout.addWidget(row)

    def _show_instance_menu(self, instance: dict, button: QPushButton) -> None:
        menu = QMenu(self)
        menu.addAction("Edit", lambda: self._edit_instance(instance))
        menu.addAction("Clone", lambda: self._clone_instance(instance))
        menu.addAction("Repair", lambda: self._repair_instance(instance))
        menu.addSeparator()
        menu.addAction("View Crash Reports", lambda: self._view_crashes(instance))
        menu.addAction("Screenshots", lambda: self._view_screenshots(instance))
        menu.addAction("Backup Worlds", lambda: self._backup_worlds(instance))
        menu.addSeparator()
        menu.addAction("Remove", lambda: self._remove_instance(instance))
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _view_crashes(self, instance: dict) -> None:
        dlg = CrashReportDialog(instance, self)
        dlg.exec()

    def _view_screenshots(self, instance: dict) -> None:
        dlg = ScreenshotGalleryDialog(instance, self)
        dlg.exec()

    def _backup_worlds(self, instance: dict) -> None:
        dlg = WorldBackupDialog(instance, self)
        dlg.exec()

    def _create_instance(self) -> None:
        default_version = config.get("selected_version", "1.21.4") or "1.21.4"
        version, ok = QInputDialog.getText(self, "New Instance", "Minecraft version:", text=default_version)
        if not ok or not version.strip():
            return
        try:
            version = validate_version_id(version.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Version", str(exc))
            return
        name, ok = QInputDialog.getText(self, "New Instance", "Instance name:", text=f"Minecraft {version.strip()}")
        if not ok or not name.strip():
            return
        instance = create_custom_instance(name.strip(), version)
        set_selected_instance(instance["id"])
        self._render_instances()
        self._count_label.setText(f"Created {instance['name']}. Use Repair to download game files.")

    def _select_instance(self, instance: dict) -> None:
        set_selected_instance(instance.get("id", ""))
        self._render_instances()
        self._count_label.setText(f"Active instance: {instance.get('name', 'Instance')}")

    def _edit_instance(self, instance: dict) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Edit Instance",
            "Instance name:",
            text=instance.get("name", "Instance"),
        )
        if not ok or not name.strip():
            return
        jvm_args, ok = QInputDialog.getText(
            self,
            "Edit Instance",
            "Instance JVM args:",
            text=instance.get("jvm_args", ""),
        )
        if ok:
            update_instance(instance.get("id", ""), name=name.strip(), jvm_args=jvm_args.strip())
            self._render_instances()

    def _clone_instance(self, instance: dict) -> None:
        cloned = clone_instance(instance.get("id", ""))
        if cloned:
            set_selected_instance(cloned["id"])
            self._render_instances()
            self._count_label.setText(f"Cloned {instance.get('name', 'instance')}.")

    def _repair_instance(self, instance: dict) -> None:
        thread = QThread(self)
        worker = _RepairWorker(instance)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(lambda _c, _t, status: self._count_label.setText(status or "Repairing instance..."))
        worker.finished.connect(lambda ok, msg: self._on_repair_finished(thread, worker, ok, msg))
        worker.finished.connect(thread.quit)
        self._repair_threads.append(thread)
        self._repair_workers.append(worker)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_repair_finished(self, thread: QThread, worker: _RepairWorker, ok: bool, message: str) -> None:
        if thread in self._repair_threads:
            self._repair_threads.remove(thread)
        if worker in self._repair_workers:
            self._repair_workers.remove(worker)
        self._count_label.setText(message if ok else f"Repair failed: {message}")
        self._load_versions()

    def _import_instances(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select MultiMC / Prism Launcher instances folder",
        )
        if not folder:
            return
        from pathlib import Path
        imported = import_prism_instances(Path(folder))
        if imported:
            self._render_instances()
            self._count_label.setText(
                f"Imported {len(imported)} instance(s) from {folder}. "
                "Use Repair if game files are missing."
            )
        else:
            self._count_label.setText(
                "No importable instances found. "
                "Make sure you selected the folder that contains the instance subfolders."
            )

    def _remove_instance(self, instance: dict) -> None:
        reply = QMessageBox.question(
            self,
            "Remove Instance",
            f"Remove {instance.get('name', 'this instance')} from the launcher list?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            remove_instance(instance.get("id", ""))
            if config.get("selected_instance_id", "") == instance.get("id", ""):
                config.set("selected_instance_id", "")
            self._render_instances()

    def _on_search(self, text: str) -> None:
        self._search_text = text.lower()
        self._render_versions()

    def _on_filter_changed(self) -> None:
        self._show_snapshots = self._snap_check.isChecked()
        self._show_old       = self._old_check.isChecked()
        config.update({
            "show_snapshots":    self._show_snapshots,
            "show_old_versions": self._show_old,
        })
        self._load_versions()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_versions(self) -> None:
        while self._versions_layout.count() > 1:
            item = self._versions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        filtered = [
            v for v in self._all_versions
            if self._search_text in v["id"].lower()
        ]
        self._count_label.setText(f"{len(filtered)} versions found")

        for v in filtered[:60]:
            vid = v["id"]
            card = VersionCard(
                version_id=vid,
                version_type=v.get("type", "release"),
                is_installed=vid in self._installed,
                parent=self._versions_container,
            )
            card.setFixedHeight(115)
            card.launch_requested.connect(self.launch_requested)
            card.install_requested.connect(self._on_install_requested)
            self._versions_layout.insertWidget(self._versions_layout.count() - 1, card)

    # ------------------------------------------------------------------
    # Install (#2)
    # ------------------------------------------------------------------

    def _on_install_requested(self, version_id: str) -> None:
        if version_id in self._install_workers:
            return  # already in progress

        card = self._find_card(version_id)
        if card:
            card.set_installing("Preparing…")

        worker = InstallWorker(version_id)
        worker.progress_changed.connect(
            lambda cur, tot, status: self._on_install_progress(version_id, cur, tot, status)
        )
        worker.finished.connect(
            lambda ok, msg: self._on_install_finished(version_id, ok, msg)
        )
        self._install_workers[version_id] = worker
        worker.start()

    def _on_install_progress(self, version_id: str, current: int, total: int, status: str) -> None:
        card = self._find_card(version_id)
        if status:
            self._count_label.setText(f"{version_id}: {status}")
        if total > 0 and card:
            pct = int(current / total * 100)
            card.set_installing(f"{pct}%")

    def _on_install_finished(self, version_id: str, success: bool, message: str) -> None:
        self._install_workers.pop(version_id, None)
        card = self._find_card(version_id)

        if success:
            self._installed.add(version_id)
            self._count_label.setText(f"Installed {version_id} successfully.")
            if card:
                card.set_installed()
            self._render_instances()
        else:
            self._count_label.setText(f"Install failed: {message}")
            if card:
                card._action_btn.setText("Install")
                card._action_btn.setEnabled(True)

    def _find_card(self, version_id: str) -> VersionCard | None:
        for i in range(self._versions_layout.count()):
            item = self._versions_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, VersionCard) and w._version_id == version_id:
                    return w
        return None
