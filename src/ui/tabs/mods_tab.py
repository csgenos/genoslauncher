"""Modrinth mods browser and per-instance mod installer."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ...core import modrinth as mr
from ...core.config import APP_DIR, config
from ...core.instances import list_instances, selected_instance, selected_instance_dir, set_selected_instance


class ModSearchWorker(QObject):
    results_ready = Signal(list, int)
    error = Signal(str)

    def __init__(self, query: str, game_version: str) -> None:
        super().__init__()
        self.query = query
        self.game_version = game_version

    def run(self) -> None:
        try:
            hits, total = mr.search_projects(
                query=self.query,
                project_type="mod",
                game_version=self.game_version,
                limit=18,
            )
            self.results_ready.emit(hits, total)
        except mr.ModrinthError as exc:
            self.error.emit(str(exc))


class ModInstallWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, project: dict, instance: dict | None, fallback_dir: Path) -> None:
        super().__init__()
        self.project = project
        self.instance = instance
        self.fallback_dir = fallback_dir

    def run(self) -> None:
        try:
            mc_version = (self.instance or {}).get("mc_version", "")
            versions = mr.get_project_versions(
                self.project["id"],
                game_versions=[mc_version] if mc_version else None,
            )
            if not versions:
                raise mr.ModrinthError("No compatible versions found for the active instance.")
            files = versions[0].get("files", [])
            primary = next((f for f in files if f.get("primary")), files[0] if files else None)
            if not primary:
                raise mr.ModrinthError("No downloadable mod file found.")

            mods_dir = (Path((self.instance or {}).get("directory", self.fallback_dir)) / "mods")
            mods_dir.mkdir(parents=True, exist_ok=True)
            hashes = primary.get("hashes", {})
            dest = mods_dir / primary["filename"]
            mr.download_file(
                primary["url"],
                dest,
                expected_sha1=hashes.get("sha1", ""),
                expected_sha512=hashes.get("sha512", ""),
            )
            name = self.project.get("title", primary["filename"])
            self.finished.emit(True, f"Installed {name} to {mods_dir}.")
        except Exception as exc:
            self.finished.emit(False, str(exc))


def _fmt_dl(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


class ModCard(QFrame):
    install_requested = Signal(dict)

    def __init__(self, project: dict, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self.setObjectName("ModCard")
        self.setFixedHeight(92)
        self.setStyleSheet(f"""
            #ModCard {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 8px;
            }}
            #ModCard:hover {{ border-color: {C["border_strong"]}; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        icon = QLabel("MOD")
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"""
            background: {C["bg_secondary"]};
            border: 1px solid {C["border"]};
            border-radius: 8px;
            font-size: {FONT["xs"]};
            font-weight: 800;
            color: {C["text_secondary"]};
        """)
        layout.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        title = QLabel(project.get("title", "Unknown Mod"))
        title.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        text_col.addWidget(title)

        desc = QLabel(project.get("description", "")[:120])
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_secondary']};")
        text_col.addWidget(desc)

        meta = QLabel(f"by {project.get('author', '?')}  -  downloads {_fmt_dl(project.get('downloads', 0))}")
        meta.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        text_col.addWidget(meta)
        layout.addLayout(text_col, 1)

        install = QPushButton("Install")
        install.setFixedSize(78, 32)
        install.setCursor(Qt.PointingHandCursor)
        install.setStyleSheet(f"""
            QPushButton {{
                background: {C["accent"]};
                color: {C["text_inverse"]};
                border: none;
                border-radius: 6px;
                font-size: {FONT["xs"]};
                font-weight: 700;
            }}
            QPushButton:hover {{ background: #1F2937; }}
        """)
        install.clicked.connect(lambda: self.install_requested.emit(self._project))
        layout.addWidget(install)


class ModsTab(QWidget):
    """Search Modrinth mods and install them into the active instance."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._execute_search)
        self._threads: list[QThread] = []
        self._workers: list[QObject] = []
        self._build_ui()
        QTimer.singleShot(250, self.refresh_instances)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 28, 40, 28)
        root.setSpacing(18)

        header = QHBoxLayout()
        title = QLabel("Mods")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        header.addWidget(title)
        header.addStretch()
        self._instance_combo = QComboBox()
        self._instance_combo.setFixedSize(260, 36)
        self._instance_combo.currentIndexChanged.connect(self._on_instance_changed)
        header.addWidget(self._instance_combo)
        root.addLayout(header)

        search_row = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search mods on Modrinth...")
        self._search_box.setFixedHeight(38)
        self._search_box.textChanged.connect(lambda _: self._search_timer.start(400))
        search_row.addWidget(self._search_box)

        self._version_filter = QComboBox()
        self._version_filter.setFixedSize(140, 38)
        self._version_filter.currentIndexChanged.connect(lambda _: self._search_timer.start(400))
        search_row.addWidget(self._version_filter)
        root.addLayout(search_row)

        self._status = QLabel("Select an instance to install mods.")
        self._status.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        root.addWidget(self._status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._results = QVBoxLayout(content)
        self._results.setContentsMargins(0, 0, 8, 0)
        self._results.setSpacing(8)
        self._results.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def refresh_instances(self) -> None:
        self._instance_combo.blockSignals(True)
        self._instance_combo.clear()
        instances = list_instances()
        active_id = config.get("selected_instance_id", "")
        if instances:
            for instance in instances:
                self._instance_combo.addItem(instance.get("name", "Instance"), instance.get("id", ""))
            index = max(0, self._instance_combo.findData(active_id))
            self._instance_combo.setCurrentIndex(index)
        else:
            self._instance_combo.addItem("Default Minecraft folder", "")
        self._instance_combo.blockSignals(False)
        self._populate_versions()
        self._execute_search()

    def _populate_versions(self) -> None:
        current = selected_instance()
        version = (current or {}).get("mc_version", config.get("selected_version", ""))
        self._version_filter.blockSignals(True)
        self._version_filter.clear()
        self._version_filter.addItem("Instance version", version)
        self._version_filter.addItem("Any version", "")
        if version:
            self._version_filter.setCurrentIndex(0)
        else:
            self._version_filter.setCurrentIndex(1)
        self._version_filter.blockSignals(False)

    def _on_instance_changed(self, index: int) -> None:
        set_selected_instance(self._instance_combo.itemData(index) or "")
        self._populate_versions()
        self._execute_search()

    def _execute_search(self) -> None:
        query = self._search_box.text().strip() if hasattr(self, "_search_box") else ""
        game_version = self._version_filter.currentData() if hasattr(self, "_version_filter") else ""
        self._status.setText("Searching mods...")
        while self._results.count() > 1:
            item = self._results.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        thread = QThread(self)
        worker = ModSearchWorker(query, game_version)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.results_ready.connect(self._on_results)
        worker.error.connect(lambda e: self._status.setText(f"Error: {e}"))
        worker.results_ready.connect(thread.quit)
        worker.error.connect(thread.quit)
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_results(self, hits: list[dict], total: int) -> None:
        self._status.setText(f"{total:,} compatible mods found.")
        for project in hits:
            card = ModCard(project, self)
            card.install_requested.connect(self._install_mod)
            self._results.insertWidget(self._results.count() - 1, card)

    def _install_mod(self, project: dict) -> None:
        instance = selected_instance()
        fallback_dir = selected_instance_dir() if instance else Path(config.get("minecraft_dir", str(APP_DIR / "minecraft")))
        self._status.setText(f"Installing {project.get('title', 'mod')}...")
        thread = QThread(self)
        worker = ModInstallWorker(project, instance, fallback_dir)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda ok, msg: self._status.setText(msg if ok else f"Install failed: {msg}"))
        worker.finished.connect(thread.quit)
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()
