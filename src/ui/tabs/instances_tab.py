"""
Instances tab — browse, install, and manage Minecraft versions.
Fixes:
  - Reads show_snapshots/show_old_versions from config on startup (#7)
  - Install button on VersionCard triggers real InstallWorker (#2)
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QObject, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import OutlineButton
from ..components.version_card import VersionCard
from ...core.launcher import InstallWorker, get_available_versions, get_installed_versions
from ...core.config import config


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
        except Exception:
            installed = []
        self.done.emit(versions, installed)


class InstancesTab(QWidget):
    """Browse all available Minecraft versions with filtering."""

    launch_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Restore persisted filter state (#7)
        self._show_snapshots = config.get("show_snapshots", False)
        self._show_old       = config.get("show_old_versions", False)
        self._all_versions:   list[dict]  = []
        self._installed:      set[str]    = set()
        self._search_text     = ""
        self._load_threads:   list[QThread] = []
        self._install_workers: dict[str, InstallWorker] = {}
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
        root.addLayout(header_row)

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
        self._load_threads.append(thread)
        thread.start()

    def _on_versions_loaded(self, versions: list[dict], installed: list[str]) -> None:
        self._all_versions = versions
        self._installed = set(installed)
        self._render_versions()

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
