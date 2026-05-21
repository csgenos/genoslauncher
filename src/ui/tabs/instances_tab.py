"""
Instances tab — browse, install, and manage Minecraft versions.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import OutlineButton
from ..components.version_card import VersionCard
from ...core.launcher import get_available_versions, get_installed_versions
from ...core.instances import list_instances, remove_instance

log = logging.getLogger(__name__)


class VersionsLoadWorker(QObject):
    loaded = Signal(list, set)

    def __init__(self, show_snapshots: bool, show_old: bool) -> None:
        super().__init__()
        self.show_snapshots = show_snapshots
        self.show_old = show_old

    def run(self) -> None:
        versions = get_available_versions(
            include_snapshots=self.show_snapshots,
            include_old=self.show_old,
        )
        try:
            installed = set(get_installed_versions())
        except Exception as exc:
            log.warning("Installed version load failed: %s", exc.__class__.__name__)
            installed = set()
        self.loaded.emit(versions, installed)


class InstancesTab(QWidget):
    """Browse all available Minecraft versions with filtering."""

    launch_requested = Signal(str)
    instance_launch_requested = Signal(str, str)
    install_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._all_versions: list[dict] = []
        self._installed: set[str] = set()
        self._show_snapshots = False
        self._show_old = False
        self._search_text = ""
        self._load_thread: QThread | None = None
        self._load_worker: VersionsLoadWorker | None = None
        self._build_ui()
        self._load_versions()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 32, 48, 32)
        root.setSpacing(24)

        # Header
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
        root.addLayout(header_row)

        # Filter bar
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

        # Filter bar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search versions…")
        self._search_box.setFixedHeight(38)
        self._search_box.textChanged.connect(self._on_search)
        filter_row.addWidget(self._search_box)

        self._snap_check = QCheckBox("Snapshots")
        self._snap_check.setChecked(False)
        self._snap_check.toggled.connect(self._on_filter_changed)
        filter_row.addWidget(self._snap_check)

        self._old_check = QCheckBox("Legacy")
        self._old_check.setChecked(False)
        self._old_check.toggled.connect(self._on_filter_changed)
        filter_row.addWidget(self._old_check)

        root.addLayout(filter_row)

        # Count label
        self._count_label = QLabel("Loading versions...")
        self._count_label.setStyleSheet(f"color: {C['text_secondary']}; font-size: {FONT['sm']};")
        root.addWidget(self._count_label)

        # Scrollable version grid
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

    def _load_versions(self) -> None:
        if self._load_thread is not None:
            return
        self._count_label.setText("Loading versions...")
        thread = QThread(self)
        worker = VersionsLoadWorker(self._show_snapshots, self._show_old)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.loaded.connect(self._on_versions_loaded)
        worker.loaded.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: setattr(self, "_load_thread", None))
        thread.finished.connect(lambda: setattr(self, "_load_worker", None))
        self._load_thread = thread
        self._load_worker = worker
        thread.start()

    def _on_versions_loaded(self, versions: list[dict], installed: set[str]) -> None:
        self._all_versions = versions
        self._installed = installed
        self._render_versions()
        self._render_instances()

    def _render_instances(self) -> None:
        while self._instances_layout.count():
            item = self._instances_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        instances = list_instances()
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
            name = QLabel(f"{instance.get('name', 'Instance')}  ·  {instance.get('mc_version', '?')}")
            name.setStyleSheet(f"color: {C['text_primary']}; font-size: {FONT['md']}; font-weight: 600;")
            layout.addWidget(name, 1)
            launch = QPushButton("Launch")
            launch.setFixedWidth(80)
            launch.clicked.connect(lambda _=False, i=instance: self.instance_launch_requested.emit(i.get("mc_version", ""), i.get("id", "")))
            layout.addWidget(launch)
            remove = OutlineButton("Remove")
            remove.setFixedWidth(84)
            remove.clicked.connect(lambda _=False, i=instance: self._remove_instance(i))
            layout.addWidget(remove)
            self._instances_layout.addWidget(row)

    def _remove_instance(self, instance: dict) -> None:
        reply = QMessageBox.question(
            self,
            "Remove Instance",
            f"Remove {instance.get('name', 'this instance')} from the launcher list?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            remove_instance(instance.get("id", ""))
            self._render_instances()

    def _on_search(self, text: str) -> None:
        self._search_text = text.lower()
        self._render_versions()

    def _on_filter_changed(self) -> None:
        self._show_snapshots = self._snap_check.isChecked()
        self._show_old = self._old_check.isChecked()
        self._load_versions()

    def _render_versions(self) -> None:
        # Clear existing cards
        while self._versions_layout.count() > 1:
            item = self._versions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        filtered = [
            v for v in self._all_versions
            if self._search_text in v["id"].lower()
        ]

        self._count_label.setText(f"{len(filtered)} versions found")

        for v in filtered[:60]:  # cap for performance
            vid = v["id"]
            card = VersionCard(
                version_id=vid,
                version_type=v.get("type", "release"),
                is_installed=vid in self._installed,
                parent=self._versions_container,
            )
            card.setFixedHeight(115)
            card.launch_requested.connect(self.launch_requested)
            card.install_requested.connect(self.install_requested)
            self._versions_layout.insertWidget(self._versions_layout.count() - 1, card)
