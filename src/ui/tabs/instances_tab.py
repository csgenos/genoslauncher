"""
Instances tab - browse, install, and manage Minecraft versions.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..components.animated_button import OutlineButton
from ..components.version_card import VersionCard
from ..dialogs.backup_dialog import WorldBackupDialog
from ..dialogs.crash_dialog import CrashReportDialog
from ..dialogs.instance_health_dialog import InstanceHealthDialog
from ..dialogs.prism_migration_dialog import PrismMigrationDialog
from ..dialogs.screenshot_dialog import ScreenshotGalleryDialog
from ..components.themed_controls import GComboBox, GMenu
from ..styles import COLORS as C, FONT
from ...core.config import config
from ...core.instances import (
    clone_instance,
    create_custom_instance,
    import_prism_instances,
    list_instance_groups,
    list_instances,
    repair_instance_layout,
    remove_instance,
    set_instance_group,
    set_selected_instance,
    update_instance,
    validate_instance,
)
from ...core.modpack_archive import export_instance_mrpack, export_instance_zip, import_instance_archive
from ...core.launcher import InstallWorker, get_available_versions, get_installed_versions, install_minecraft_base
from ...core.modpack_update import update_modpack_instance
from ...core.validators import validate_version_id

log = logging.getLogger(__name__)


def _dir_size_mb(path: Path) -> float:
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
    except OSError:
        pass
    return total / (1024 * 1024)


class _DiskSizeWorker(QObject):
    done = Signal(str, float)  # instance_id, mb

    def __init__(self, instance_id: str, directory: str) -> None:
        super().__init__()
        self._id = instance_id
        self._dir = directory

    def run(self) -> None:
        mb = _dir_size_mb(Path(self._dir)) if self._dir else 0.0
        self.done.emit(self._id, mb)


class _VersionLoader(QObject):
    done = Signal(list, list)  # all_versions, installed_ids

    def __init__(self, include_snapshots: bool, include_old: bool, force_refresh: bool = False) -> None:
        super().__init__()
        self._snapshots = include_snapshots
        self._old = include_old
        self._force_refresh = force_refresh

    def run(self) -> None:
        versions = get_available_versions(
            include_snapshots=self._snapshots,
            include_old=self._old,
            force_refresh=self._force_refresh,
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
            ok, issues = validate_instance(self._instance)
            created = repair_instance_layout(self._instance)
            if created:
                self.progress.emit(0, 1, f"Created folders: {', '.join(created)}")
            version = self._instance.get("mc_version", "")
            directory = self._instance.get("directory", "")
            if not version or not directory:
                raise RuntimeError("Instance is missing version or directory.")
            install_minecraft_base(version, directory, self.progress.emit)
            if ok:
                self.finished.emit(True, f"Repaired {self._instance.get('name', 'instance')}.")
            else:
                self.finished.emit(
                    True,
                    f"Repaired with warnings ({len(issues)}): " + "; ".join(issues[:3]),
                )
        except Exception as exc:
            self.finished.emit(False, str(exc))


class _ModpackUpdateWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(bool, str)

    def __init__(self, instance: dict) -> None:
        super().__init__()
        self._instance = instance

    def run(self) -> None:
        try:
            ok, msg = update_modpack_instance(self._instance, self.progress.emit)
            self.finished.emit(ok, msg)
        except Exception as exc:
            self.finished.emit(False, str(exc))


class InstancesTab(QWidget):
    launch_requested = Signal(str)
    instance_launch_requested = Signal(str, str)
    install_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._show_snapshots = config.get("show_snapshots", False)
        self._show_old = config.get("show_old_versions", False)
        self._all_versions: list[dict] = []
        self._installed: set[str] = set()
        self._search_text = ""
        self._instance_search_text = ""
        self._group_filter = "All groups"
        self._instance_sort = "Name (A-Z)"
        self._load_threads: list[QThread] = []
        self._load_workers: list[QObject] = []
        self._install_workers: dict[str, InstallWorker] = {}
        self._repair_threads: list[QThread] = []
        self._repair_workers: list[_RepairWorker] = []
        self._selected_instances: set[str] = set()
        self._disk_size_threads: list[QThread] = []
        self._disk_labels: dict[str, QLabel] = {}
        self._modpack_update_threads: list[QThread] = []
        self._modpack_update_workers: list[_ModpackUpdateWorker] = []
        self._build_ui()
        QTimer.singleShot(100, lambda: self._load_versions(force_refresh=False))
        self._version_refresh_timer = QTimer(self)
        self._version_refresh_timer.setInterval(10 * 60 * 1000)
        self._version_refresh_timer.timeout.connect(lambda: self._load_versions(force_refresh=True))
        self._version_refresh_timer.start()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 32, 48, 32)
        root.setSpacing(24)

        header_row = QHBoxLayout()
        title = QLabel("Instances")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        header_row.addWidget(title)
        header_row.addStretch()

        refresh_btn = OutlineButton("Refresh")
        refresh_btn.setFixedHeight(34)
        refresh_btn.setFixedWidth(110)
        refresh_btn.clicked.connect(lambda _checked=False: self._load_versions(force_refresh=True))
        header_row.addWidget(refresh_btn)

        new_btn = OutlineButton("New Instance")
        new_btn.setFixedHeight(34)
        new_btn.setFixedWidth(132)
        new_btn.clicked.connect(self._create_instance)
        header_row.addWidget(new_btn)

        import_btn = OutlineButton("Import...")
        import_btn.setFixedHeight(34)
        import_btn.setFixedWidth(100)
        import_btn.clicked.connect(self._import_menu)
        header_row.addWidget(import_btn)

        prism_btn = OutlineButton("Import from Prism…")
        prism_btn.setFixedHeight(34)
        prism_btn.clicked.connect(self._open_prism_migration)
        header_row.addWidget(prism_btn)
        bulk_btn = OutlineButton("Bulk Actions")
        bulk_btn.setFixedHeight(34)
        bulk_btn.setFixedWidth(126)
        bulk_btn.clicked.connect(self._bulk_actions)
        header_row.addWidget(bulk_btn)

        root.addLayout(header_row)

        self._instances_title = QLabel("Installed Instances")
        self._instances_title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        root.addWidget(self._instances_title)

        instance_filter_row = QHBoxLayout()
        instance_filter_row.setSpacing(10)
        self._instance_search_box = QLineEdit()
        self._instance_search_box.setPlaceholderText("Search instances...")
        self._instance_search_box.setFixedHeight(34)
        self._instance_search_box.textChanged.connect(self._on_instance_search_changed)
        instance_filter_row.addWidget(self._instance_search_box, 1)
        self._group_filter_combo = GComboBox()
        self._group_filter_combo.setFixedHeight(34)
        self._group_filter_combo.setMinimumWidth(180)
        self._group_filter_combo.currentTextChanged.connect(self._on_group_filter_changed)
        instance_filter_row.addWidget(self._group_filter_combo)
        self._sort_combo = GComboBox()
        self._sort_combo.setFixedHeight(34)
        self._sort_combo.setMinimumWidth(180)
        self._sort_combo.addItems(["Name (A-Z)", "Recently Played", "Minecraft Version"])
        self._sort_combo.currentTextChanged.connect(self._on_sort_changed)
        instance_filter_row.addWidget(self._sort_combo)
        root.addLayout(instance_filter_row)

        bulk_row = QHBoxLayout()
        bulk_row.setSpacing(8)
        self._select_all_cb = QCheckBox("Select All")
        self._select_all_cb.toggled.connect(self._on_select_all)
        bulk_row.addWidget(self._select_all_cb)
        bulk_row.addStretch()
        validate_all_btn = OutlineButton("Validate All")
        validate_all_btn.setFixedHeight(30)
        validate_all_btn.clicked.connect(self._bulk_validate)
        bulk_row.addWidget(validate_all_btn)
        repair_all_btn = OutlineButton("Repair All")
        repair_all_btn.setFixedHeight(30)
        repair_all_btn.clicked.connect(self._bulk_repair)
        bulk_row.addWidget(repair_all_btn)
        export_all_btn = OutlineButton("Export All")
        export_all_btn.setFixedHeight(30)
        export_all_btn.clicked.connect(self._bulk_export)
        bulk_row.addWidget(export_all_btn)
        root.addLayout(bulk_row)

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
        self._search_box.setPlaceholderText("Search versions...")
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

    def _load_versions(self, force_refresh: bool = False) -> None:
        self._count_label.setText("Loading versions...")
        thread = QThread(self)
        worker = _VersionLoader(self._show_snapshots, self._show_old, force_refresh=force_refresh)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_versions_loaded)
        worker.done.connect(thread.quit)
        thread.finished.connect(lambda: self._load_threads.remove(thread) if thread in self._load_threads else None)
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

    def _refresh_group_filter_options(self) -> None:
        options = ["All groups", *list_instance_groups()]
        current = self._group_filter_combo.currentText() if self._group_filter_combo.count() else self._group_filter
        self._group_filter_combo.blockSignals(True)
        self._group_filter_combo.clear()
        self._group_filter_combo.addItems(options)
        if current in options:
            self._group_filter_combo.setCurrentText(current)
            self._group_filter = current
        else:
            self._group_filter_combo.setCurrentText("All groups")
            self._group_filter = "All groups"
        self._group_filter_combo.blockSignals(False)

    def _filter_instances(self, instances: list[dict]) -> list[dict]:
        text = self._instance_search_text.lower().strip()
        out: list[dict] = []
        for instance in instances:
            group = str(instance.get("group", "Other")).strip() or "Other"
            if self._group_filter != "All groups" and group != self._group_filter:
                continue
            if text:
                blob = " ".join(
                    [
                        str(instance.get("name", "")),
                        str(instance.get("mc_version", "")),
                        str(instance.get("type", "")),
                        group,
                        str(instance.get("notes", "")),
                        " ".join(instance.get("tags", [])),
                    ]
                ).lower()
                if text not in blob:
                    continue
            out.append(instance)
        return out

    def _instance_sort_key(self, instance: dict) -> tuple:
        if self._instance_sort == "Recently Played":
            last = str(instance.get("last_played_at", "")).strip()
            return (last == "", last, str(instance.get("name", "")).lower())
        if self._instance_sort == "Minecraft Version":
            return (str(instance.get("mc_version", "")).lower(), str(instance.get("name", "")).lower())
        return (str(instance.get("name", "")).lower(),)

    def _render_instances(self) -> None:
        while self._instances_layout.count():
            item = self._instances_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._disk_labels.clear()
        for t in self._disk_size_threads:
            if t.isRunning():
                t.quit()
        self._disk_size_threads.clear()

        all_instances = list_instances()
        self._refresh_group_filter_options()
        instances = self._filter_instances(all_instances)
        if not all_instances:
            empty = QLabel("No instances installed yet. Install a version below to create one.")
            empty.setStyleSheet(f"color: {C['text_tertiary']}; font-size: {FONT['sm']};")
            self._instances_layout.addWidget(empty)
            return
        if not instances:
            empty = QLabel("No instances match your filters.")
            empty.setStyleSheet(f"color: {C['text_tertiary']}; font-size: {FONT['sm']};")
            self._instances_layout.addWidget(empty)
            return

        active_id = config.get("selected_instance_id", "")
        grouped: dict[str, list[dict]] = {}
        for instance in instances:
            group = str(instance.get("group", "Other")).strip() or "Other"
            grouped.setdefault(group, []).append(instance)

        for group_name in sorted(grouped.keys(), key=str.lower):
            section = QLabel(f"{group_name} ({len(grouped[group_name])})")
            section.setStyleSheet(f"color: {C['text_secondary']}; font-size: {FONT['sm']}; font-weight: 700;")
            self._instances_layout.addWidget(section)
            rows = sorted(grouped[group_name], key=self._instance_sort_key, reverse=self._instance_sort == "Recently Played")
            for instance in rows:
                inst_id = instance.get("id", "")
                row = QWidget()
                row.setStyleSheet(f"background: {C['bg_primary']}; border: 1px solid {C['border']}; border-radius: 8px;")
                layout = QHBoxLayout(row)
                layout.setContentsMargins(14, 10, 14, 10)

                cb = QCheckBox()
                cb.setChecked(inst_id in self._selected_instances)
                cb.toggled.connect(lambda checked, iid=inst_id: self._on_instance_cb_toggled(iid, checked))
                layout.addWidget(cb)

                active = "Active - " if inst_id == active_id else ""
                detail = (
                    f"{active}{instance.get('name', 'Instance')} - {instance.get('mc_version', '?')} - "
                    f"{str(instance.get('type', 'custom')).title()}"
                )
                tags = instance.get("tags", [])
                if tags:
                    detail += f" - tags: {', '.join(tags[:3])}"
                name = QLabel(detail)
                name.setStyleSheet(f"color: {C['text_primary']}; font-size: {FONT['md']}; font-weight: 600;")
                layout.addWidget(name, 1)

                disk_lbl = QLabel("…MB")
                disk_lbl.setStyleSheet(f"color: {C['text_tertiary']}; font-size: {FONT['xs']}; min-width: 60px;")
                self._disk_labels[inst_id] = disk_lbl
                layout.addWidget(disk_lbl)
                self._start_disk_size_worker(inst_id, instance.get("directory", ""))

                select = QPushButton("Use")
                select.setFixedWidth(58)
                select.clicked.connect(lambda _=False, i=instance: self._select_instance(i))
                layout.addWidget(select)
                launch = QPushButton("Launch")
                launch.setFixedWidth(80)
                launch.clicked.connect(
                    lambda _=False, i=instance: self.instance_launch_requested.emit(i.get("mc_version", ""), i.get("id", ""))
                )
                layout.addWidget(launch)
                more_btn = OutlineButton("...")
                more_btn.setFixedWidth(38)
                more_btn.clicked.connect(lambda _=False, i=instance, b=more_btn: self._show_instance_menu(i, b))
                layout.addWidget(more_btn)
                self._instances_layout.addWidget(row)

    def _show_instance_menu(self, instance: dict, button: QPushButton) -> None:
        menu = GMenu(self)
        menu.addAction("Edit", lambda: self._edit_instance(instance))
        menu.addAction("Edit Metadata", lambda: self._edit_instance_metadata(instance))
        menu.addAction("Validate", lambda: self._validate_instance(instance))
        menu.addAction("Health Check / Optimize", lambda: self._open_health_dialog(instance))
        menu.addAction("Move to Group...", lambda: self._move_instance_group(instance))
        menu.addAction("Clone", lambda: self._clone_instance(instance))
        menu.addAction("Repair", lambda: self._repair_instance(instance))
        if instance.get("type") == "modpack":
            menu.addAction("Update Modpack", lambda: self._update_modpack(instance))
        menu.addAction("Export ZIP...", lambda: self._export_instance_zip(instance))
        menu.addAction("Export MRPACK...", lambda: self._export_instance_mrpack(instance))
        menu.addSeparator()
        menu.addAction("View Crash Reports", lambda: self._view_crashes(instance))
        menu.addAction("Screenshots", lambda: self._view_screenshots(instance))
        menu.addAction("Backup Worlds", lambda: self._backup_worlds(instance))
        menu.addSeparator()
        menu.addAction("Remove", lambda: self._remove_instance(instance))
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _import_menu(self) -> None:
        menu = GMenu(self)
        menu.addAction("Import Prism/MultiMC Folder...", self._import_instances)
        menu.addAction("Import ZIP/MRPACK Archive...", self._import_archive)
        menu.exec(QCursor.pos())

    def _on_instance_cb_toggled(self, instance_id: str, checked: bool) -> None:
        if checked:
            self._selected_instances.add(instance_id)
        else:
            self._selected_instances.discard(instance_id)

    def _on_select_all(self, checked: bool) -> None:
        instances = list_instances()
        if checked:
            self._selected_instances = {i.get("id", "") for i in instances}
        else:
            self._selected_instances.clear()
        self._render_instances()

    def _start_disk_size_worker(self, instance_id: str, directory: str) -> None:
        if not directory:
            if instance_id in self._disk_labels:
                self._disk_labels[instance_id].setText("—")
            return
        thread = QThread(self)
        worker = _DiskSizeWorker(instance_id, directory)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_disk_size_done)
        worker.done.connect(thread.quit)
        self._disk_size_threads.append(thread)
        thread.finished.connect(lambda: self._disk_size_threads.remove(thread) if thread in self._disk_size_threads else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_disk_size_done(self, instance_id: str, mb: float) -> None:
        lbl = self._disk_labels.get(instance_id)
        if lbl:
            if mb >= 1024:
                lbl.setText(f"{mb/1024:.1f} GB")
            else:
                lbl.setText(f"{mb:.0f} MB")

    def _get_selected_or_all(self) -> list[dict]:
        instances = list_instances()
        if self._selected_instances:
            return [i for i in instances if i.get("id") in self._selected_instances]
        return instances

    def _bulk_validate(self) -> None:
        targets = self._get_selected_or_all()
        if not targets:
            self._count_label.setText("No instances to validate.")
            return
        results = []
        for instance in targets:
            ok, issues = validate_instance(instance)
            if ok:
                results.append(f"{instance.get('name', '?')}: OK")
            else:
                results.append(f"{instance.get('name', '?')}: {'; '.join(issues[:2])}")
        self._count_label.setText(f"Validated {len(targets)}: " + " | ".join(results[:3]))

    def _bulk_repair(self) -> None:
        targets = self._get_selected_or_all()
        if not targets:
            self._count_label.setText("No instances to repair.")
            return
        self._count_label.setText(f"Repairing {len(targets)} instance(s)…")
        for instance in targets:
            self._repair_instance(instance)

    def _bulk_export(self) -> None:
        targets = self._get_selected_or_all()
        if not targets:
            self._count_label.setText("No instances to export.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose Export Folder")
        if not folder:
            return
        folder_path = Path(folder)
        success = 0
        for instance in targets:
            name = instance.get("name", "instance").replace(" ", "_")
            dest = folder_path / f"{name}.zip"
            try:
                export_instance_zip(instance, dest)
                success += 1
            except Exception as exc:
                log.warning("Export failed for %s: %s", instance.get("name"), exc)
        self._count_label.setText(f"Exported {success}/{len(targets)} instances to {folder}.")

    def _view_crashes(self, instance: dict) -> None:
        CrashReportDialog(instance, self).exec()

    def _open_health_dialog(self, instance: dict) -> None:
        InstanceHealthDialog(instance, self).exec()

    def _view_screenshots(self, instance: dict) -> None:
        ScreenshotGalleryDialog(instance, self).exec()

    def _backup_worlds(self, instance: dict) -> None:
        WorldBackupDialog(instance, self).exec()

    def _move_instance_group(self, instance: dict) -> None:
        current = str(instance.get("group", "Other")).strip() or "Other"
        group_name, ok = QInputDialog.getText(self, "Move Instance", "Group name:", text=current)
        if not ok:
            return
        set_instance_group(instance.get("id", ""), group_name.strip())
        self._render_instances()
        self._count_label.setText(f"Moved {instance.get('name', 'instance')} to group '{group_name.strip() or current}'.")

    def _validate_instance(self, instance: dict) -> None:
        ok, issues = validate_instance(instance)
        if ok:
            self._count_label.setText(f"{instance.get('name', 'Instance')}: validation OK.")
        else:
            self._count_label.setText(f"{instance.get('name', 'Instance')}: " + "; ".join(issues[:2]))

    def _export_instance_zip(self, instance: dict) -> None:
        default_name = f"{instance.get('name', 'instance')}.zip"
        path, _ = QFileDialog.getSaveFileName(self, "Export Instance ZIP", default_name, "ZIP Archives (*.zip)")
        if not path:
            return
        try:
            export_instance_zip(instance, Path(path))
            self._count_label.setText(f"Exported ZIP: {Path(path).name}")
        except Exception as exc:
            self._count_label.setText(f"Export failed: {exc}")

    def _export_instance_mrpack(self, instance: dict) -> None:
        default_name = f"{instance.get('name', 'instance')}.mrpack"
        path, _ = QFileDialog.getSaveFileName(self, "Export Instance MRPACK", default_name, "MRPACK Archives (*.mrpack)")
        if not path:
            return
        try:
            export_instance_mrpack(instance, Path(path))
            self._count_label.setText(f"Exported MRPACK: {Path(path).name}")
        except Exception as exc:
            self._count_label.setText(f"Export failed: {exc}")

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
        name, ok = QInputDialog.getText(self, "Edit Instance", "Instance name:", text=instance.get("name", "Instance"))
        if not ok or not name.strip():
            return
        jvm_args, ok = QInputDialog.getText(self, "Edit Instance", "Instance JVM args:", text=instance.get("jvm_args", ""))
        if ok:
            update_instance(instance.get("id", ""), name=name.strip(), jvm_args=jvm_args.strip())
            self._render_instances()

    def _edit_instance_metadata(self, instance: dict) -> None:
        current_java = str(instance.get("java_path", "")).strip()
        java_path, ok = QInputDialog.getText(
            self,
            "Instance Java Override",
            "Java executable path (leave blank for global default):",
            text=current_java,
        )
        if not ok:
            return
        ram_text, ok = QInputDialog.getText(
            self,
            "Instance RAM Override",
            "RAM (MB, leave blank for global default):",
            text=str(instance.get("ram_mb", "") or ""),
        )
        if not ok:
            return
        tags_text, ok = QInputDialog.getText(
            self,
            "Instance Tags",
            "Comma-separated tags:",
            text=", ".join(instance.get("tags", [])),
        )
        if not ok:
            return
        notes, ok = QInputDialog.getMultiLineText(
            self,
            "Instance Notes",
            "Notes:",
            text=str(instance.get("notes", "")),
        )
        if not ok:
            return
        tags = [t.strip() for t in tags_text.split(",") if t.strip()]
        try:
            ram_value = int(ram_text.strip()) if ram_text.strip() else 0
        except ValueError:
            ram_value = 0
        update_instance(
            instance.get("id", ""),
            java_path=java_path.strip(),
            ram_mb=max(0, min(ram_value, 32768)),
            tags=tags,
            notes=notes.strip(),
        )
        self._render_instances()
        self._count_label.setText(f"Updated metadata for {instance.get('name', 'instance')}.")

    def _bulk_actions(self) -> None:
        target = self._filter_instances(list_instances())
        if not target:
            self._count_label.setText("No instances match current filters.")
            return
        action, ok = QInputDialog.getItem(
            self,
            "Bulk Actions",
            f"Action for {len(target)} filtered instance(s):",
            ["Set Group", "Remove from List", "Delete Files and Remove"],
            0,
            False,
        )
        if not ok or not action:
            return
        if action == "Set Group":
            group_name, ok = QInputDialog.getText(self, "Set Group", "Group name:")
            if not ok:
                return
            for inst in target:
                set_instance_group(inst.get("id", ""), group_name.strip())
            self._render_instances()
            self._count_label.setText(f"Updated group for {len(target)} instance(s).")
            return
        delete_files = action == "Delete Files and Remove"
        for inst in target:
            remove_instance(inst.get("id", ""), delete_files=delete_files)
            if config.get("selected_instance_id", "") == inst.get("id", ""):
                config.set("selected_instance_id", "")
        self._render_instances()
        self._count_label.setText(f"Removed {len(target)} instance(s).")

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

    def _update_modpack(self, instance: dict) -> None:
        thread = QThread(self)
        worker = _ModpackUpdateWorker(instance)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(lambda _c, _t, status: self._count_label.setText(status or "Updating modpack..."))
        worker.finished.connect(lambda ok, msg: self._on_modpack_update_finished(thread, worker, ok, msg))
        worker.finished.connect(thread.quit)
        self._modpack_update_threads.append(thread)
        self._modpack_update_workers.append(worker)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_modpack_update_finished(
        self,
        thread: QThread,
        worker: _ModpackUpdateWorker,
        ok: bool,
        message: str,
    ) -> None:
        if thread in self._modpack_update_threads:
            self._modpack_update_threads.remove(thread)
        if worker in self._modpack_update_workers:
            self._modpack_update_workers.remove(worker)
        self._count_label.setText(message if ok else f"Modpack update failed: {message}")
        self._load_versions()

    def _open_prism_migration(self) -> None:
        dlg = PrismMigrationDialog(self)
        dlg.exec()
        self._render_instances()

    def _import_instances(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select MultiMC / Prism Launcher instances folder")
        if not folder:
            return
        imported = import_prism_instances(Path(folder))
        if imported:
            self._render_instances()
            self._count_label.setText(
                f"Imported {len(imported)} instance(s) from {folder}. Use Repair if game files are missing."
            )
        else:
            self._count_label.setText(
                "No importable instances found. Make sure you selected the folder that contains the instance subfolders."
            )

    def _import_archive(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import ZIP/MRPACK Archive",
            "",
            "Archives (*.zip *.mrpack)",
        )
        if not path:
            return
        name_hint = Path(path).stem
        try:
            instance = import_instance_archive(Path(path), instance_name=name_hint)
            set_selected_instance(instance.get("id", ""))
            self._render_instances()
            self._count_label.setText(f"Imported archive as instance: {instance.get('name', 'Instance')}")
        except Exception as exc:
            self._count_label.setText(f"Import failed: {exc}")

    def _remove_instance(self, instance: dict) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Remove Instance")
        box.setText(f"How do you want to remove {instance.get('name', 'this instance')}?")
        remove_only = box.addButton("Remove from List", QMessageBox.AcceptRole)
        remove_and_delete = box.addButton("Remove and Delete Files", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked not in {remove_only, remove_and_delete}:
            return
        delete_files = clicked is remove_and_delete
        remove_instance(instance.get("id", ""), delete_files=delete_files)
        if config.get("selected_instance_id", "") == instance.get("id", ""):
            config.set("selected_instance_id", "")
        self._render_instances()

    def _on_search(self, text: str) -> None:
        self._search_text = text.lower()
        self._render_versions()

    def _on_instance_search_changed(self, text: str) -> None:
        self._instance_search_text = text
        self._render_instances()

    def _on_group_filter_changed(self, group_name: str) -> None:
        self._group_filter = group_name or "All groups"
        self._render_instances()

    def _on_sort_changed(self, sort_name: str) -> None:
        self._instance_sort = sort_name or "Name (A-Z)"
        self._render_instances()

    def _on_filter_changed(self) -> None:
        self._show_snapshots = self._snap_check.isChecked()
        self._show_old = self._old_check.isChecked()
        config.update({"show_snapshots": self._show_snapshots, "show_old_versions": self._show_old})
        self._load_versions()

    def _render_versions(self) -> None:
        while self._versions_layout.count() > 1:
            item = self._versions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        filtered = [v for v in self._all_versions if self._search_text in v["id"].lower()]
        self._count_label.setText(f"{len(filtered)} versions found")

        for v in filtered:
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

    def _on_install_requested(self, version_id: str) -> None:
        if version_id in self._install_workers:
            return
        card = self._find_card(version_id)
        if card:
            card.set_installing("Preparing...")

        worker = InstallWorker(version_id)
        worker.progress_changed.connect(lambda cur, tot, status: self._on_install_progress(version_id, cur, tot, status))
        worker.finished.connect(lambda ok, msg: self._on_install_finished(version_id, ok, msg))
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
                widget = item.widget()
                if isinstance(widget, VersionCard) and widget._version_id == version_id:
                    return widget
        return None
