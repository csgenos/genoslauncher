"""
Home tab - launcher home screen.
"""

from __future__ import annotations

import json
import os
import re as _re
import sys

import requests
from PySide6.QtCore import QObject, QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QMovie
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..._version import __version__ as _VER
from ...core.config import APP_DIR, config
from ...core.instances import list_instances
from ...core.launcher import get_available_versions, get_installed_versions
from ..components.animated_button import LaunchButton, OutlineButton, PrimaryButton
from ..components.progress_widget import LaunchProgressPanel
from ..components.themed_controls import GComboBox
from ..components.version_card import VersionCard
from ..styles import COLORS as C, FONT

_STATIC_FALLBACK_VERSIONS = ["1.21.4", "1.20.1", "1.8.9"]
_STATIC_FALLBACK_NEWS = [
    (
        "GenosLauncher v0.2 Released",
        "Modpack browser, shader management, and a complete premium UI redesign are now live.",
        "2025-05-01",
    ),
    (
        "Modrinth Integration",
        "Browse and install thousands of modpacks and shaders directly from inside the launcher.",
        "2025-04-20",
    ),
    (
        "Java Auto-Detection",
        "The launcher now automatically detects installed Java versions and picks the best one.",
        "2025-04-10",
    ),
]
_HOME_CACHE_FILE = APP_DIR / "cache" / "home_cache.json"


def _asset(name: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(base, "assets", name)


def _read_home_cache() -> tuple[list[str], list[tuple[str, str, str]]]:
    try:
        data = json.loads(_HOME_CACHE_FILE.read_text(encoding="utf-8"))
        versions = data.get("fallback_versions", [])
        news = data.get("fallback_news", [])
        clean_versions = [str(v) for v in versions if isinstance(v, str)][:6]
        clean_news: list[tuple[str, str, str]] = []
        for item in news:
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                continue
            clean_news.append((str(item[0]), str(item[1]), str(item[2])))
        return clean_versions, clean_news
    except (OSError, ValueError, TypeError):
        return [], []


def _write_home_cache(*, versions: list[str] | None = None, news: list[tuple[str, str, str]] | None = None) -> None:
    _HOME_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    current = {"fallback_versions": [], "fallback_news": []}
    try:
        current = json.loads(_HOME_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        pass
    if versions is not None:
        current["fallback_versions"] = versions[:6]
    if news is not None:
        current["fallback_news"] = [[t, b, d] for (t, b, d) in news[:6]]
    tmp = _HOME_CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_HOME_CACHE_FILE)


_CACHED_VERSIONS, _CACHED_NEWS = _read_home_cache()
_FALLBACK_VERSIONS = _CACHED_VERSIONS or _STATIC_FALLBACK_VERSIONS
_FALLBACK_NEWS = _CACHED_NEWS or _STATIC_FALLBACK_NEWS


class _VersionLoader(QObject):
    done = Signal(list, list)

    def __init__(self, force_refresh: bool = False) -> None:
        super().__init__()
        self._force_refresh = force_refresh

    def run(self) -> None:
        snapshots = config.get("show_snapshots", False)
        old = config.get("show_old_versions", False)
        try:
            available = get_available_versions(
                include_snapshots=snapshots,
                include_old=old,
                force_refresh=self._force_refresh,
            )
            release_ids = [
                v.get("id", "")
                for v in available
                if isinstance(v, dict) and v.get("type") == "release"
            ]
            release_ids = [v for v in release_ids if v][:6]
            if release_ids:
                _write_home_cache(versions=release_ids)
        except Exception:
            available = [{"id": v, "type": "release"} for v in _FALLBACK_VERSIONS]
        try:
            installed = get_installed_versions()
        except Exception:
            installed = []
        self.done.emit(available, installed)


class _NewsLoader(QObject):
    done = Signal(list)

    def run(self) -> None:
        try:
            resp = requests.get(
                "https://api.github.com/repos/csgenos/genoslauncher/releases?per_page=3",
                headers={"User-Agent": f"GenosLauncher/{_VER}", "Accept": "application/vnd.github+json"},
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
            if items:
                _write_home_cache(news=items)
            self.done.emit(items if items else _FALLBACK_NEWS)
        except Exception:
            self.done.emit(_FALLBACK_NEWS)


class HeroWidget(QWidget):
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(C["bg_secondary"]))
        painter.end()


class NewsItem(QFrame):
    def __init__(self, title: str, body: str, date: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NewsItem")
        self.setStyleSheet(
            f"""
            #NewsItem {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
            }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

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


class FeatureTile(QFrame):
    clicked = Signal(str)

    def __init__(self, title: str, body: str, target: str = "", accent: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._target = target
        self.setObjectName("FeatureTile")
        self.setCursor(Qt.PointingHandCursor if target else Qt.ArrowCursor)
        border = C["border_focus"] if accent else C["border"]
        bg = C["accent_orange_soft"] if accent else C["bg_primary"]
        self.setStyleSheet(f"""
            #FeatureTile {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
        """)
        self.setMinimumHeight(86)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 800; color: {C['text_primary']};")
        layout.addWidget(title_lbl)
        body_lbl = QLabel(body)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_secondary']};")
        layout.addWidget(body_lbl)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._target:
            self.clicked.emit(self._target)
        super().mousePressEvent(event)


def _card_style(name: str, accent: bool = False) -> str:
    bg = C["accent_orange_soft"] if accent else C["bg_primary"]
    border = C["border_focus"] if accent else C["border"]
    return f"""
        #{name} {{
            background: {bg};
            border: 1px solid {border};
            border-radius: 12px;
        }}
    """


class HomeTab(QWidget):
    launch_requested = Signal(str)
    install_requested = Signal(str)
    view_all_requested = Signal()
    navigate_requested = Signal(str)
    continue_requested = Signal(str, str)  # version_id, instance_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._selected_version: str = config.get("selected_version", "1.21.4") or "1.21.4"
        self._installed: list[str] = []
        self._available: list[dict] = []
        self._threads: list[QThread] = []
        self._workers: list[QObject] = []
        self._quick_play_layout: QHBoxLayout | None = None
        self._news_layout: QVBoxLayout | None = None
        self._versions_loading_row: QWidget | None = None
        self._news_loading_row: QWidget | None = None
        self._loading_movies: list[QMovie] = []
        self._continue_btn: PrimaryButton | None = None
        self._build_ui()
        QTimer.singleShot(0, lambda: self._load_versions(force_refresh=False))
        QTimer.singleShot(0, self._load_news)
        QTimer.singleShot(0, self._refresh_continue_btn)
        self._version_refresh_timer = QTimer(self)
        self._version_refresh_timer.setInterval(10 * 60 * 1000)
        self._version_refresh_timer.timeout.connect(lambda: self._load_versions(force_refresh=True))
        self._version_refresh_timer.start()

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
        cl.setContentsMargins(24, 18, 24, 20)
        cl.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        launch_card = QFrame()
        launch_card.setObjectName("SetupPanel")
        launch_card.setMinimumHeight(188)
        launch_card.setStyleSheet(_card_style("SetupPanel"))
        launch_layout = QVBoxLayout(launch_card)
        launch_layout.setContentsMargins(18, 16, 18, 16)
        launch_layout.setSpacing(10)

        eyebrow = QLabel("CURRENT SETUP")
        eyebrow.setStyleSheet(f"font-size: {FONT['xs']}; font-weight: 800; color: {C['accent_orange']};")
        launch_layout.addWidget(eyebrow)

        headline = QLabel("Ready when you are.")
        headline.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 850; color: {C['text_primary']};")
        launch_layout.addWidget(headline)

        subhead = QLabel("Select the active Minecraft version. Install, launch, and repair work is reported in the status bar below.")
        subhead.setWordWrap(True)
        subhead.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        launch_layout.addWidget(subhead)

        launch_row = QHBoxLayout()
        launch_row.setSpacing(12)
        self._version_combo = GComboBox()
        self._version_combo.setFixedHeight(42)
        self._version_combo.setMinimumWidth(164)
        self._version_combo.setStyleSheet(
            f"""
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
            """
        )
        self._version_combo.addItems(_FALLBACK_VERSIONS)
        self._version_combo.setCurrentText(
            self._selected_version if self._selected_version in _FALLBACK_VERSIONS else _FALLBACK_VERSIONS[0]
        )
        self._version_combo.currentTextChanged.connect(self._on_version_changed)
        launch_row.addWidget(self._version_combo)

        self._play_btn = LaunchButton("Play")
        self._play_btn.setMinimumWidth(124)
        self._play_btn.setFixedHeight(42)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 26))
        self._play_btn.setGraphicsEffect(shadow)
        self._play_btn.clicked.connect(self._on_play_clicked)
        launch_row.addWidget(self._play_btn)

        self._continue_btn = PrimaryButton("Continue")
        self._continue_btn.setMinimumWidth(148)
        self._continue_btn.setFixedHeight(42)
        self._continue_btn.clicked.connect(self._on_continue_clicked)
        self._continue_btn.setVisible(False)
        launch_row.addWidget(self._continue_btn)

        launch_layout.addLayout(launch_row)

        self._progress = LaunchProgressPanel()
        launch_layout.addWidget(self._progress)
        launch_layout.addStretch()
        top_row.addWidget(launch_card, 3)

        guide_card = QFrame()
        guide_card.setObjectName("GuideCard")
        guide_card.setMinimumWidth(290)
        guide_card.setStyleSheet(_card_style("GuideCard"))
        guide_layout = QVBoxLayout(guide_card)
        guide_layout.setContentsMargins(16, 14, 16, 14)
        guide_layout.setSpacing(8)

        guide_title = QLabel("Session status")
        guide_title.setStyleSheet(f"font-size: {FONT['xl']}; font-weight: 850; color: {C['text_primary']};")
        guide_layout.addWidget(guide_title)
        for title, body in [
            ("Account", "Sign in from the sidebar for online play."),
            ("Instances", "Use the tools below when you need mods, packs, shaders, or repairs."),
            ("Feedback", "Every install and launch now reports progress in the bottom status strip."),
        ]:
            item = QLabel(f"{title}\n{body}")
            item.setWordWrap(True)
            item.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']}; padding: 6px 0;")
            guide_layout.addWidget(item)
        guide_layout.addStretch()
        top_row.addWidget(guide_card, 1)
        cl.addLayout(top_row)

        actions_header = QLabel("Core Tools")
        actions_header.setStyleSheet(f"font-size: {FONT['xl']}; font-weight: 850; color: {C['text_primary']};")
        cl.addWidget(actions_header)

        action_grid = QGridLayout()
        action_grid.setHorizontalSpacing(12)
        action_grid.setVerticalSpacing(12)
        actions = [
            ("Instances", "Create, repair, import, and launch isolated profiles.", "instances", True),
            ("Mods", "Install and update mods for the selected instance.", "mods", False),
            ("Modpacks", "Install packs and manage pack updates.", "modpacks", False),
            ("Shaders", "Add Iris, shaders, and resource packs.", "shaders", False),
            ("Servers", "Save servers and join with the right instance.", "servers", False),
            ("Settings", "Tune RAM, Java, sync, auth, and app behavior.", "settings", False),
        ]
        for idx, (title, body, target, accent) in enumerate(actions):
            tile = FeatureTile(title, body, target, accent, self)
            tile.clicked.connect(self.navigate_requested)
            action_grid.addWidget(tile, idx // 3, idx % 3)
        cl.addLayout(action_grid)

        qp_card = QFrame()
        qp_card.setObjectName("QuickPlayCard")
        qp_card.setStyleSheet(_card_style("QuickPlayCard"))
        qp_layout = QVBoxLayout(qp_card)
        qp_layout.setContentsMargins(16, 14, 16, 14)
        qp_layout.setSpacing(10)
        qp_header = QHBoxLayout()
        qp_title = QLabel("Version library")
        qp_title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 800; color: {C['text_primary']};")
        qp_header.addWidget(qp_title)
        qp_header.addStretch()
        view_all = OutlineButton("View all")
        view_all.setFixedHeight(32)
        view_all.setMinimumWidth(96)
        view_all.clicked.connect(self.view_all_requested)
        qp_header.addWidget(view_all)
        qp_layout.addLayout(qp_header)

        self._quick_play_layout = QHBoxLayout()
        self._quick_play_layout.setSpacing(12)
        self._versions_loading_row = self._build_loading_row("Loading installed versions...")
        self._quick_play_layout.addWidget(self._versions_loading_row)
        self._quick_play_layout.addStretch()
        qp_layout.addLayout(self._quick_play_layout)
        cl.addWidget(qp_card)

        news_header = QHBoxLayout()
        news_title = QLabel("Latest update")
        news_title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 800; color: {C['text_primary']};")
        news_header.addWidget(news_title)
        news_header.addStretch()
        all_releases = OutlineButton("Releases")
        all_releases.setFixedHeight(32)
        all_releases.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/csgenos/genoslauncher/releases"))
        )
        news_header.addWidget(all_releases)
        cl.addLayout(news_header)

        self._news_layout = QVBoxLayout()
        self._news_layout.setSpacing(8)
        self._news_loading_row = self._build_loading_row("Loading release notes...")
        self._news_layout.addWidget(self._news_loading_row)
        cl.addLayout(self._news_layout)

        cl.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_loading_row(self, text: str) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        icon = QLabel(row)
        icon.setFixedSize(16, 16)
        movie = None
        gif_path = _asset("animationlauncher.gif")
        if os.path.exists(gif_path):
            movie = QMovie(gif_path)
            movie.setScaledSize(icon.size())
            icon.setMovie(movie)
            movie.start()
            self._loading_movies.append(movie)
        else:
            icon.setText("...")
            icon.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        layout.addWidget(icon)
        label = QLabel(text, row)
        label.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_tertiary']};")
        layout.addWidget(label)
        layout.addStretch()
        return row

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

    def _load_versions(self, force_refresh: bool = False) -> None:
        thread = QThread(self)
        worker = _VersionLoader(force_refresh=force_refresh)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_versions_loaded)
        worker.done.connect(thread.quit)
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
        self._version_combo.blockSignals(True)
        self._version_combo.clear()

        installed_set = set(installed)
        normalized = [v for v in available if isinstance(v, dict) and isinstance(v.get("id"), str) and v.get("id")]
        if not normalized:
            normalized = [{"id": v, "type": "release"} for v in _FALLBACK_VERSIONS]

        for v in normalized:
            vid = v.get("id", "")
            if vid in installed_set:
                self._version_combo.addItem(f"* {vid}", vid)
        for v in normalized:
            vid = v.get("id", "")
            if vid and vid not in installed_set:
                self._version_combo.addItem(vid, vid)
        if self._version_combo.count() == 0:
            for fallback in _FALLBACK_VERSIONS:
                self._version_combo.addItem(fallback, fallback)

        target = self._selected_version
        for i in range(self._version_combo.count()):
            if self._version_combo.itemData(i) == target:
                self._version_combo.setCurrentIndex(i)
                break
        else:
            self._version_combo.setCurrentIndex(0)
            self._selected_version = self._version_combo.currentData() or self._version_combo.currentText() or ""
        self._version_combo.blockSignals(False)

    def _populate_quick_play(self, available: list[dict], installed: list[str]) -> None:
        while self._quick_play_layout.count():
            item = self._quick_play_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        installed_set = set(installed)
        show_installed = [
            v for v in available
            if isinstance(v, dict) and isinstance(v.get("id"), str) and v.get("id") in installed_set
        ][:3]
        fallbacks = [
            {"id": "1.21.4", "type": "release"},
            {"id": "1.20.1", "type": "release"},
            {"id": "1.8.9", "type": "release"},
        ]
        show = (show_installed or fallbacks)[:3]

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
        self._load_versions()

    def _on_version_changed(self, _text: str) -> None:
        vid = self._version_combo.currentData() or self._version_combo.currentText()
        self._selected_version = vid
        config.set("selected_version", vid)

    def _on_play_clicked(self) -> None:
        vid = self._version_combo.currentData() or self._version_combo.currentText()
        if not vid:
            return
        self.launch_requested.emit(vid)

    def _refresh_continue_btn(self) -> None:
        if self._continue_btn is None:
            return
        instance_id = config.get("selected_instance_id", "")
        last_account = config.get("last_account", "")
        if not instance_id or not last_account:
            self._continue_btn.setVisible(False)
            return
        instances = list_instances()
        instance = next((i for i in instances if i.get("id") == instance_id), None)
        if instance is None:
            self._continue_btn.setVisible(False)
            return
        name = instance.get("name", "Instance")
        self._continue_btn.setText(f"Continue - {name}")
        self._continue_btn.setVisible(True)

    def _on_continue_clicked(self) -> None:
        instance_id = config.get("selected_instance_id", "")
        if not instance_id:
            return
        instances = list_instances()
        instance = next((i for i in instances if i.get("id") == instance_id), None)
        if instance is None:
            return
        version_id = instance.get("mc_version", "")
        if not version_id:
            return
        self.continue_requested.emit(version_id, instance_id)
