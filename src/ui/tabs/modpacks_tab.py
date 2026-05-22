"""
Modpacks tab — browse and install Modrinth modpacks.

Features:
  - Search bar with game-version filter
  - Card grid of modpack results (icon, title, author, downloads)
  - One-click install: downloads .mrpack, installs loader + mods
  - Progress feedback per install
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, QObject, Signal, QTimer, QSize
from PySide6.QtGui import QColor, QFont, QPixmap, QPainter, QImage
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ...core.config import APP_DIR, config
from ...core import modrinth as mr
from ...core import curseforge as cf
from ...core.instances import create_modpack_instance
from ...core.launcher import install_minecraft_base, install_loader


# ---------------------------------------------------------------------------
# Worker — search Modrinth off the UI thread
# ---------------------------------------------------------------------------

class SearchWorker(QObject):
    results_ready = Signal(list, int)   # hits, total
    error = Signal(str)

    def __init__(self, query: str, project_type: str, game_version: str, offset: int = 0,
                 source: str = "modrinth") -> None:
        super().__init__()
        self.query = query
        self.project_type = project_type
        self.game_version = game_version
        self.offset = offset
        self.source = source

    def run(self) -> None:
        try:
            if self.source == "curseforge":
                hits, total = cf.search_modpacks(self.query, self.game_version)
                self.results_ready.emit(hits, total)
            else:
                hits, total = mr.search_projects(
                    query=self.query,
                    project_type=self.project_type,
                    game_version=self.game_version,
                    limit=18,
                    offset=self.offset,
                )
                self.results_ready.emit(hits, total)
        except (mr.ModrinthError, cf.CurseForgeError) as exc:
            self.error.emit(str(exc))


class InstallWorker(QObject):
    progress = Signal(int, int, str)   # current, total, status text
    finished = Signal(bool, str)       # success, message

    def __init__(self, project: dict, version: dict, dest_dir: Path) -> None:
        super().__init__()
        self.project = project
        self.version = version
        self.dest_dir = dest_dir

    def run(self) -> None:
        try:
            failures = self._install()
        except Exception as exc:
            self.finished.emit(False, str(exc))
            return
        if failures:
            failed_str = ", ".join(failures[:3])
            if len(failures) > 3:
                failed_str += f" (+{len(failures) - 3} more)"
            msg = (
                f"'{self.project['title']}' installed — "
                f"{len(failures)} mod(s) could not be downloaded: {failed_str}"
            )
        else:
            msg = f"'{self.project['title']}' installed successfully."
        self.finished.emit(True, msg)

    def _install(self) -> list[str]:
        # 1. Find the primary file
        files = self.version.get("files", [])
        primary = next((f for f in files if f.get("primary")), files[0] if files else None)
        if not primary:
            raise RuntimeError("No downloadable file found in this version.")

        file_url = primary["url"]
        filename = primary["filename"]
        mrpack_path = self.dest_dir / filename

        # 2. Download .mrpack
        total_size = primary.get("size", 0)
        self.progress.emit(0, max(total_size, 1), f"Downloading {filename}...")

        def on_dl(done: int, total: int) -> None:
            self.progress.emit(done, max(total, 1), f"Downloading {filename}...")

        mr.download_file(file_url, mrpack_path, on_progress=on_dl)

        # 3. Parse
        self.progress.emit(0, 1, "Parsing modpack...")
        index = mr.parse_mrpack(mrpack_path)

        mc_version = index.get("dependencies", {}).get("minecraft", "")
        instance_name = self.project["title"]
        instance_dir = APP_DIR / "instances" / instance_name

        # 3b. Install base Minecraft version into the isolated modpack instance.
        mc_dir = str(instance_dir)
        self.progress.emit(0, 1, f"Installing Minecraft {mc_version}…")
        install_minecraft_base(
            mc_version, mc_dir,
            lambda c, t, s: self.progress.emit(c, t, s),
        )

        # 3c. Install mod loader (Fabric / Quilt)
        deps = index.get("dependencies", {})
        self.progress.emit(0, 1, "Detecting mod loader…")
        loader_version_id = install_loader(
            deps, mc_dir,
            lambda c, t, s: self.progress.emit(c, t, s),
        )

        # 4. Download mods
        def on_mod(current: int, total: int, fname: str) -> None:
            self.progress.emit(current, max(total, 1), f"Downloading mod {current}/{total}: {fname}")

        failures = mr.install_mrpack_mods(index, instance_dir, on_progress=on_mod)

        # 5. Extract overrides
        self.progress.emit(0, 1, "Extracting overrides...")
        mr.extract_mrpack_overrides(mrpack_path, instance_dir)

        # 6. Register instance in config
        create_modpack_instance(self.project, mc_version, instance_dir)

        return failures


# ---------------------------------------------------------------------------
# Icon loader (async, simple)
# ---------------------------------------------------------------------------

class IconLoader(QObject):
    loaded = Signal(str, QPixmap)   # project_id, pixmap

    def __init__(self, project_id: str, icon_url: str, cache_dir: Path) -> None:
        super().__init__()
        self.project_id = project_id
        self.icon_url = icon_url
        self.cache_dir = cache_dir

    def run(self) -> None:
        path = mr.download_icon(self.icon_url, self.cache_dir)
        if path:
            px = QPixmap(str(path)).scaled(
                56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.loaded.emit(self.project_id, px)


# ---------------------------------------------------------------------------
# Modpack card widget
# ---------------------------------------------------------------------------

def _format_downloads(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


class ModpackCard(QFrame):
    """Clean white card for a single modpack result."""

    install_requested = Signal(dict)   # emits project dict

    def __init__(self, project: dict, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._install_thread: Optional[QThread] = None

        self.setObjectName("ModpackCard")
        self.setStyleSheet(f"""
            #ModpackCard {{
                background: {C["bg_card"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
            }}
            #ModpackCard:hover {{
                border-color: {C["border_strong"]};
            }}
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(130)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Icon placeholder
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(56, 56)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setStyleSheet(f"""
            background: {C["bg_tertiary"]};
            border-radius: 10px;
            font-size: 22px;
        """)
        self._icon_label.setText("📦")
        layout.addWidget(self._icon_label)

        # Text content
        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        text_col.setContentsMargins(0, 0, 0, 0)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        title = QLabel(self._project["title"])
        title.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        title_row.addWidget(title)

        # Category pills
        for cat in self._project.get("categories", [])[:2]:
            pill = QLabel(cat)
            pill.setStyleSheet(f"""
                background: {C["bg_tertiary"]};
                color: {C["text_secondary"]};
                border-radius: 4px;
                padding: 2px 7px;
                font-size: {FONT["xs"]};
                font-weight: 600;
            """)
            title_row.addWidget(pill)

        title_row.addStretch()
        text_col.addLayout(title_row)

        desc = QLabel(self._project.get("description", "")[:120])
        desc.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        desc.setWordWrap(True)
        text_col.addWidget(desc)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(14)

        author_lbl = QLabel(f"by {self._project.get('author', 'Unknown')}")
        author_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        meta_row.addWidget(author_lbl)

        dl_lbl = QLabel(f"↓ {_format_downloads(self._project.get('downloads', 0))}")
        dl_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        meta_row.addWidget(dl_lbl)

        meta_row.addStretch()
        text_col.addLayout(meta_row)

        layout.addLayout(text_col, 1)

        # Install button
        self._install_btn = QPushButton("Install")
        self._install_btn.setFixedSize(80, 34)
        self._install_btn.setCursor(Qt.PointingHandCursor)
        self._install_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C["accent"]};
                color: {C["text_inverse"]};
                border: none;
                border-radius: 7px;
                font-size: {FONT["sm"]};
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #1F2937; }}
            QPushButton:pressed {{ background: #0F172A; }}
            QPushButton:disabled {{
                background: {C["bg_tertiary"]};
                color: {C["text_disabled"]};
            }}
        """)
        self._install_btn.clicked.connect(self._on_install)
        layout.addWidget(self._install_btn)

    def set_icon(self, pixmap: QPixmap) -> None:
        self._icon_label.setPixmap(pixmap)
        self._icon_label.setText("")

    def _on_install(self) -> None:
        self.install_requested.emit(self._project)

    def set_installed(self) -> None:
        self._install_btn.setText("Installed")
        self._install_btn.setEnabled(False)

    def set_installing(self, status: str = "Installing…") -> None:
        self._install_btn.setText(status[:12])
        self._install_btn.setEnabled(False)


# ---------------------------------------------------------------------------
# Modpacks tab
# ---------------------------------------------------------------------------

class ModpacksTab(QWidget):
    """Full modpacks browser tab."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._execute_search)
        self._current_cards: dict[str, ModpackCard] = {}
        self._icon_cache = APP_DIR / "cache" / "icons"
        self._icon_cache.mkdir(parents=True, exist_ok=True)
        self._search_threads: list[QThread] = []
        self._build_ui()
        # Load initial results
        QTimer.singleShot(200, self._execute_search)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 28, 40, 28)
        root.setSpacing(20)

        # ---- Header ----
        header_row = QHBoxLayout()
        title = QLabel("Modpacks")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        header_row.addWidget(title)
        header_row.addStretch()
        src_lbl = QLabel("Source:")
        src_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        header_row.addWidget(src_lbl)
        self._source_combo = QComboBox()
        self._source_combo.addItem("Modrinth", "modrinth")
        self._source_combo.addItem("CurseForge", "curseforge")
        self._source_combo.setFixedSize(140, 32)
        self._source_combo.currentIndexChanged.connect(self._on_search_changed)
        header_row.addWidget(self._source_combo)
        root.addLayout(header_row)

        sub = QLabel("Browse and install Minecraft modpacks in one click.")
        sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']}; margin-top: -12px;")
        root.addWidget(sub)

        # ---- Search bar ----
        search_row = QHBoxLayout()
        search_row.setSpacing(10)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search modpacks…")
        self._search_box.setFixedHeight(40)
        self._search_box.setStyleSheet(f"""
            QLineEdit {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 8px;
                padding: 0 14px;
                font-size: {FONT["md"]};
                color: {C["text_primary"]};
            }}
            QLineEdit:focus {{ border-color: {C["border_focus"]}; }}
        """)
        self._search_box.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self._search_box)

        self._version_filter = QComboBox()
        self._version_filter.setFixedSize(130, 40)
        self._version_filter.setStyleSheet(f"""
            QComboBox {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 8px;
                padding: 0 12px;
                font-size: {FONT["sm"]};
                color: {C["text_primary"]};
            }}
            QComboBox:focus {{ border-color: {C["border_focus"]}; }}
            QComboBox::drop-down {{ border: none; }}
        """)
        versions = ["Any version", "1.21.4", "1.21.1", "1.20.6", "1.20.1", "1.19.4", "1.18.2", "1.16.5", "1.12.2"]
        self._version_filter.addItems(versions)
        self._version_filter.currentTextChanged.connect(self._on_search_changed)
        search_row.addWidget(self._version_filter)

        root.addLayout(search_row)

        # ---- Status / count ----
        self._status_label = QLabel("Searching…")
        self._status_label.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        root.addWidget(self._status_label)

        # ---- Results scroll area ----
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._results_widget = QWidget()
        self._results_widget.setStyleSheet("background: transparent;")
        self._results_layout = QVBoxLayout(self._results_widget)
        self._results_layout.setSpacing(10)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.addStretch()

        self._scroll.setWidget(self._results_widget)
        root.addWidget(self._scroll)

    # ------------------------------------------------------------------
    # Search logic
    # ------------------------------------------------------------------

    def _on_search_changed(self, _=None) -> None:
        self._search_timer.start(400)

    def _execute_search(self) -> None:
        query = self._search_box.text().strip()
        ver_text = self._version_filter.currentText()
        game_version = "" if ver_text.startswith("Any") else ver_text
        source = self._source_combo.currentData() if hasattr(self, "_source_combo") else "modrinth"

        self._status_label.setText("Searching…")
        self._clear_results()

        thread = QThread(self)
        worker = SearchWorker(query, "modpack", game_version, source=source)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.results_ready.connect(self._on_results)
        worker.error.connect(self._on_search_error)
        worker.results_ready.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(lambda: self._search_threads.remove(thread) if thread in self._search_threads else None)
        self._search_threads.append(thread)
        thread.start()

    def _on_results(self, hits: list[dict], total: int) -> None:
        self._status_label.setText(f"{total:,} modpacks found")
        self._clear_results()
        self._current_cards.clear()

        installed = {i.get("source", "") for i in config.get("instances", [])}

        for project in hits:
            card = ModpackCard(project, self._results_widget)
            card.install_requested.connect(self._on_install_requested)
            if project["id"] in installed:
                card.set_installed()
            self._results_layout.insertWidget(self._results_layout.count() - 1, card)
            self._current_cards[project["id"]] = card

            # Load icon async
            if project.get("icon_url"):
                self._load_icon_async(project["id"], project["icon_url"])

    def _on_search_error(self, msg: str) -> None:
        self._status_label.setText(f"Error: {msg}")

    def _clear_results(self) -> None:
        while self._results_layout.count() > 1:
            item = self._results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ------------------------------------------------------------------
    # Icon loading
    # ------------------------------------------------------------------

    def _load_icon_async(self, project_id: str, icon_url: str) -> None:
        thread = QThread(self)
        loader = IconLoader(project_id, icon_url, self._icon_cache)
        loader.moveToThread(thread)
        thread.started.connect(loader.run)
        loader.loaded.connect(self._on_icon_loaded)
        loader.loaded.connect(lambda: thread.quit())
        thread.start()

    def _on_icon_loaded(self, project_id: str, pixmap: QPixmap) -> None:
        if project_id in self._current_cards:
            self._current_cards[project_id].set_icon(pixmap)

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def _on_install_requested(self, project: dict) -> None:
        # Fetch versions on background thread, then start install
        thread = QThread(self)

        class VersionFetcher(QObject):
            done = Signal(list)
            err = Signal(str)
            def __init__(self, pid): super().__init__(); self.pid = pid
            def run(self):
                try: self.done.emit(mr.get_project_versions(self.pid))
                except mr.ModrinthError as e: self.err.emit(str(e))

        fetcher = VersionFetcher(project["id"])
        fetcher.moveToThread(thread)
        thread.started.connect(fetcher.run)
        fetcher.done.connect(lambda versions: self._start_install(project, versions))
        fetcher.err.connect(lambda e: self._status_label.setText(f"Error: {e}"))
        fetcher.done.connect(thread.quit)
        fetcher.err.connect(thread.quit)
        thread.start()

        card = self._current_cards.get(project["id"])
        if card:
            card.set_installing("Fetching…")

    def _start_install(self, project: dict, versions: list[dict]) -> None:
        if not versions:
            self._status_label.setText("No versions available for this modpack.")
            return

        # Pick the latest version
        version = versions[0]
        dest_dir = APP_DIR / "downloads"

        thread = QThread(self)
        worker = InstallWorker(project, version, dest_dir)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        card = self._current_cards.get(project["id"])

        def on_progress(current, total, status):
            if card:
                pct = int(current / max(total, 1) * 100)
                card.set_installing(f"{pct}%")
            self._status_label.setText(status)

        def on_finish(success, msg):
            self._status_label.setText(msg)
            if success and card:
                card.set_installed()

        worker.progress.connect(on_progress)
        worker.finished.connect(on_finish)
        worker.finished.connect(thread.quit)
        thread.start()
