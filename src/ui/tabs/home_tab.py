"""
Home tab — launcher home screen.

Fixes applied:
  #1: Version picker populated from get_installed_versions() + get_available_versions()
      off a background thread; installed versions shown first.
  #1: Selected version persisted to config["selected_version"].
  #1: Quick Play cards show real installed versions (fallback to popular stable releases).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QObject, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QLinearGradient
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import LaunchButton, OutlineButton
from ..components.version_card import VersionCard
from ..components.progress_widget import LaunchProgressPanel
from ...core.launcher import get_available_versions, get_installed_versions
from ...core.config import config
import re as _re
import requests
from ..._version import __version__ as _VER

_FALLBACK_VERSIONS = ["1.21.4", "1.20.1", "1.8.9"]


# ---------------------------------------------------------------------------
# Background version loader
# ---------------------------------------------------------------------------

class _VersionLoader(QObject):
    done = Signal(list, list)   # available_versions, installed_ids

    def run(self) -> None:
        snapshots = config.get("show_snapshots", False)
        old = config.get("show_old_versions", False)
        try:
            available = get_available_versions(include_snapshots=snapshots, include_old=old)
        except Exception:
            available = [{"id": v, "type": "release"} for v in _FALLBACK_VERSIONS]
        try:
            installed = get_installed_versions()
        except Exception:
            installed = []
        self.done.emit(available, installed)


class _NewsLoader(QObject):
    done = Signal(list)   # list of (title, body, date) tuples

    def run(self) -> None:
        try:
            resp = requests.get(
                "https://api.github.com/repos/csgenos/genoslauncher/releases?per_page=3",
                headers={
                    "User-Agent": f"GenosLauncher/{_VER}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=5,
            )
            resp.raise_for_status()
            releases = resp.json()
            items = []
            for r in releases[:3]:
                title = r.get("name") or r.get("tag_name", "Release")
                body = (r.get("body") or "").strip()
                body = _re.sub(r"#{1,6}\s*", "", body)
                body = _re.sub(r"\*\*(.+?)\*\*", r"\1", body)
                body = body.split("\n")[0][:160]
                published = (r.get("published_at") or "")[:10]
                items.append((title, body or "New release available.", published))
            self.done.emit(items if items else _FALLBACK_NEWS)
        except Exception:
            self.done.emit(_FALLBACK_NEWS)


_FALLBACK_NEWS = [
    ("GenosLauncher v0.2 Released",
     "Modpack browser, shader management, and a complete premium UI redesign are now live.",
     "2025-05-01"),
    ("Modrinth Integration",
     "Browse and install thousands of modpacks and shaders directly from inside the launcher.",
     "2025-04-20"),
    ("Java Auto-Detection",
     "The launcher now automatically detects installed Java versions and picks the best one.",
     "2025-04-10"),
]


# ---------------------------------------------------------------------------
# Hero background
# ---------------------------------------------------------------------------

class HeroWidget(QWidget):
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(C["bg_primary"]))
        grad.setColorAt(1.0, QColor(C["bg_secondary"]))
        painter.fillRect(self.rect(), grad)
        painter.end()


# ---------------------------------------------------------------------------
# News card
# ---------------------------------------------------------------------------

class NewsItem(QFrame):
    def __init__(self, title: str, body: str, date: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NewsItem")
        self.setStyleSheet(f"""
            #NewsItem {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        header_row.addWidget(title_lbl)
        header_row.addStretch()
        date_lbl = QLabel(date)
        date_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        header_row.addWidget(date_lbl)
        layout.addLayout(header_row)

        body_lbl = QLabel(body)
        body_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        body_lbl.setWordWrap(True)
        layout.addWidget(body_lbl)


# ---------------------------------------------------------------------------
# Home Tab
# ---------------------------------------------------------------------------

class HomeTab(QWidget):
    """
    Home screen of GenosLauncher.

    Signals:
        launch_requested(str)  — version ID to launch
        install_requested(str) — version ID to install
    """

    launch_requested = Signal(str)
    install_requested = Signal(str)
    view_all_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._selected_version: str = config.get("selected_version", "1.21.4") or "1.21.4"
        self._installed: list[str] = []
        self._available: list[dict] = []
        self._load_thread: QThread | None = None
        self._threads: list[QThread] = []
        self._workers: list[QObject] = []
        self._quick_play_layout: QHBoxLayout | None = None
        self._news_layout: QVBoxLayout | None = None
        self._build_ui()
        QTimer.singleShot(0, self._load_versions)
        QTimer.singleShot(0, self._load_news)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet(f"background: {C['bg_secondary']};")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 40)
        cl.setSpacing(0)

        # ── Hero ──────────────────────────────────────────────────────
        hero = HeroWidget()
        hero.setMinimumHeight(300)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(48, 40, 48, 40)
        hero_layout.setSpacing(0)

        hero_layout.addStretch(1)

        headline = QLabel("GenosLauncher")
        headline.setStyleSheet(f"""
            font-size: {FONT["4xl"]};
            font-weight: 800;
            color: {C["text_primary"]};
            letter-spacing: -1.5px;
        """)
        hero_layout.addWidget(headline)

        subhead = QLabel("Open-source · Fast · Elegant")
        subhead.setStyleSheet(f"font-size: {FONT['lg']}; color: {C['text_secondary']}; margin-top: 4px;")
        hero_layout.addWidget(subhead)

        hero_layout.addSpacing(32)

        # Version picker + Play button
        launch_row = QHBoxLayout()
        launch_row.setSpacing(10)

        self._version_combo = QComboBox()
        self._version_combo.setFixedHeight(52)
        self._version_combo.setMinimumWidth(150)
        self._version_combo.setStyleSheet(f"""
            QComboBox {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
                padding: 0 14px;
                font-size: {FONT["md"]};
                font-weight: 600;
                color: {C["text_primary"]};
            }}
            QComboBox:hover {{ border-color: {C["border_strong"]}; }}
            QComboBox:focus {{ border-color: {C["border_focus"]}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
        """)
        # Seed with fallback while real list loads
        self._version_combo.addItems(_FALLBACK_VERSIONS)
        self._version_combo.setCurrentText(self._selected_version
                                           if self._selected_version in _FALLBACK_VERSIONS
                                           else _FALLBACK_VERSIONS[0])
        self._version_combo.currentTextChanged.connect(self._on_version_changed)
        launch_row.addWidget(self._version_combo)

        self._play_btn = LaunchButton("Play")
        self._play_btn.setMinimumWidth(160)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 35))
        self._play_btn.setGraphicsEffect(shadow)
        self._play_btn.clicked.connect(self._on_play_clicked)
        launch_row.addWidget(self._play_btn)
        launch_row.addStretch()
        hero_layout.addLayout(launch_row)

        self._progress = LaunchProgressPanel()
        hero_layout.addWidget(self._progress)

        hero_layout.addStretch(1)
        cl.addWidget(hero)

        # ── Below hero ────────────────────────────────────────────────
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(48, 28, 48, 0)
        inner_layout.setSpacing(24)

        # Quick Play
        qp_header = QHBoxLayout()
        qp_title = QLabel("Quick Play")
        qp_title.setStyleSheet(f"font-size: {FONT['xl']}; font-weight: 700; color: {C['text_primary']};")
        qp_header.addWidget(qp_title)
        qp_header.addStretch()
        view_all = OutlineButton("View all versions →")
        view_all.setFixedHeight(32)
        view_all.setMinimumWidth(160)
        view_all.clicked.connect(self.view_all_requested)
        qp_header.addWidget(view_all)
        inner_layout.addLayout(qp_header)

        # Placeholder quick play row — updated by _populate_quick_play()
        self._quick_play_layout = QHBoxLayout()
        self._quick_play_layout.setSpacing(12)
        self._qp_placeholder = QLabel("Loading installed versions…")
        self._qp_placeholder.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_tertiary']};")
        self._quick_play_layout.addWidget(self._qp_placeholder)
        self._quick_play_layout.addStretch()
        inner_layout.addLayout(self._quick_play_layout)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {C['border']}; border: none;")
        inner_layout.addWidget(divider)

        # News
        news_header = QHBoxLayout()
        news_title = QLabel("What's New")
        news_title.setStyleSheet(f"font-size: {FONT['xl']}; font-weight: 700; color: {C['text_primary']};")
        news_header.addWidget(news_title)
        news_header.addStretch()
        all_releases = OutlineButton("All releases →")
        all_releases.setFixedHeight(32)
        all_releases.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/csgenos/genoslauncher/releases")
        ))
        news_header.addWidget(all_releases)
        inner_layout.addLayout(news_header)

        self._news_layout = QVBoxLayout()
        self._news_layout.setSpacing(10)
        _loading = QLabel("Loading news…")
        _loading.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_tertiary']};")
        self._news_layout.addWidget(_loading)
        inner_layout.addLayout(self._news_layout)

        cl.addWidget(inner)
        scroll.setWidget(content)
        root.addWidget(scroll)

    # ------------------------------------------------------------------
    # Version loading (#1)
    # ------------------------------------------------------------------

    def _load_news(self) -> None:
        thread = QThread(self)
        worker = _NewsLoader()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_news_loaded)
        worker.done.connect(thread.quit)
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_news_loaded(self, items: list) -> None:
        while self._news_layout.count():
            item = self._news_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for title, body, date in items:
            self._news_layout.addWidget(NewsItem(title, body, date, self))

    def _load_versions(self) -> None:
        thread = QThread(self)
        worker = _VersionLoader()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_versions_loaded)
        worker.done.connect(thread.quit)
        self._load_thread = thread
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_versions_loaded(self, available: list[dict], installed: list[str]) -> None:
        self._available = available
        self._installed = installed
        self._populate_combo(available, installed)
        self._populate_quick_play(available, installed)

    def _populate_combo(self, available: list[dict], installed: list[str]) -> None:
        """Fill combo: installed versions first (marked), then rest."""
        self._version_combo.blockSignals(True)
        self._version_combo.clear()

        installed_set = set(installed)
        shown: list[str] = []

        # Installed first
        for v in available:
            if v["id"] in installed_set:
                self._version_combo.addItem(f"★ {v['id']}", v["id"])
                shown.append(v["id"])

        # Rest (releases only in home for brevity)
        for v in available:
            if v["id"] not in installed_set:
                self._version_combo.addItem(v["id"], v["id"])

        # Restore previous selection
        target = self._selected_version
        for i in range(self._version_combo.count()):
            if self._version_combo.itemData(i) == target:
                self._version_combo.setCurrentIndex(i)
                break
        else:
            self._version_combo.setCurrentIndex(0)
            self._selected_version = self._version_combo.currentData() or ""

        self._version_combo.blockSignals(False)

    def _populate_quick_play(self, available: list[dict], installed: list[str]) -> None:
        """Show up to 3 installed versions; fall back to popular stable releases."""
        # Remove placeholder
        while self._quick_play_layout.count():
            item = self._quick_play_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        installed_set = set(installed)
        # Prefer installed versions; if fewer than 3, fill with popular ones
        show_installed = [v for v in available if v["id"] in installed_set][:3]
        fallbacks = [
            {"id": "1.21.4", "type": "release"},
            {"id": "1.20.1", "type": "release"},
            {"id": "1.8.9",  "type": "release"},
        ]
        show = show_installed or fallbacks
        show = show[:3]

        available_ids = {v["id"] for v in available}
        for v in show:
            vid = v["id"]
            card = VersionCard(
                version_id=vid,
                version_type=v.get("type", "release"),
                is_installed=vid in installed_set,
                parent=self,
            )
            card.setMinimumHeight(115)
            card.launch_requested.connect(self.launch_requested)
            card.install_requested.connect(self.install_requested)
            self._quick_play_layout.addWidget(card)

        self._quick_play_layout.addStretch()

    # ------------------------------------------------------------------
    # Public API (called by main_window)
    # ------------------------------------------------------------------

    def set_launch_state(self, launching: bool) -> None:
        self._play_btn.set_launching(launching)
        if launching:
            self._progress.show_panel()
        else:
            self._progress.hide_panel()

    def update_progress(self, current: int, maximum: int, status: str) -> None:
        if status:
            self._progress.set_status(status)
        if maximum > 0:
            self._progress.set_progress(current, maximum)

    def refresh_versions(self) -> None:
        """Called by main_window after a successful install to refresh the picker."""
        self._load_versions()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_version_changed(self, _text: str) -> None:
        vid = self._version_combo.currentData() or self._version_combo.currentText()
        self._selected_version = vid
        config.set("selected_version", vid)

    def _on_play_clicked(self) -> None:
        vid = self._version_combo.currentData() or self._version_combo.currentText()
        if vid.startswith("★ "):
            vid = vid[2:]
        self.launch_requested.emit(vid)
