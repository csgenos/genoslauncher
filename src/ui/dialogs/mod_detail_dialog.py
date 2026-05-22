"""Mod detail dialog — full project info, version list, and dependency view."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ...core import modrinth as mr
from ...core.config import APP_DIR, config
from ...core.dependency_resolver import DepNode, detect_conflicts, flatten_required, resolve_dependencies

_XS  = FONT["xs"]
_SM  = FONT["sm"]
_MD  = FONT["md"]
_LG  = FONT["lg"]
_XL  = FONT["xl"]
_2XL = FONT["2xl"]

_ICON_CACHE = APP_DIR / "cache" / "mod_icons"


def _strip_markdown(text: str) -> str:
    """Convert Modrinth markdown body to plain text for display."""
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    text = re.sub(r"^\s*[-*+]\s+", "• ", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class _DetailWorker(QObject):
    """Load full project body + gallery."""
    done  = Signal(dict)
    error = Signal(str)

    def __init__(self, project_id: str) -> None:
        super().__init__()
        self._id = project_id

    def run(self) -> None:
        try:
            data = mr.get_project_full(self._id)
            self.done.emit(data)
        except mr.ModrinthError as exc:
            self.error.emit(str(exc))


class _VersionsWorker(QObject):
    done  = Signal(list)
    error = Signal(str)

    def __init__(self, project_id: str, mc_version: str, loader: str) -> None:
        super().__init__()
        self._id = project_id
        self._mc = mc_version
        self._loader = loader

    def run(self) -> None:
        try:
            vers = mr.get_project_versions(
                self._id,
                game_versions=[self._mc] if self._mc else None,
                loaders=[self._loader] if self._loader else None,
            )
            self.done.emit(vers)
        except mr.ModrinthError as exc:
            self.error.emit(str(exc))


class _DepsWorker(QObject):
    done   = Signal(list)
    status = Signal(str)

    def __init__(self, version_id: str, loader: str, mc_version: str, installed_ids: set) -> None:
        super().__init__()
        self._vid = version_id
        self._loader = loader
        self._mc = mc_version
        self._installed = installed_ids

    def run(self) -> None:
        self.status.emit("Resolving dependencies…")
        nodes = resolve_dependencies(
            self._vid,
            loader=self._loader,
            mc_version=self._mc,
            installed_ids=self._installed,
        )
        self.done.emit(nodes)


class _IconWorker(QObject):
    done = Signal(str)

    def __init__(self, icon_url: str) -> None:
        super().__init__()
        self._url = icon_url

    def run(self) -> None:
        _ICON_CACHE.mkdir(parents=True, exist_ok=True)
        path = mr.download_icon(self._url, _ICON_CACHE)
        if path:
            self.done.emit(str(path))


# ---------------------------------------------------------------------------
# Small sub-widgets
# ---------------------------------------------------------------------------

class _CategoryChip(QLabel):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(
            "background: " + C["bg_tertiary"] + "; color: " + C["text_secondary"] +
            "; border-radius: 4px; padding: 2px 7px; font-size: " + _XS + "; font-weight: 600;"
        )


class _VersionRow(QFrame):
    install_requested = Signal(dict)

    def __init__(self, version: dict, parent=None) -> None:
        super().__init__(parent)
        self._ver = version
        self.setFixedHeight(52)
        self.setStyleSheet(
            "QFrame { background: " + C["bg_primary"] + "; border: 1px solid " +
            C["border"] + "; border-radius: 8px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        vtype = version.get("version_type", "release")
        type_colors = {
            "release": (C["accent_green_soft"], C["accent_green"]),
            "beta":    (C["bg_tertiary"],       C["accent_orange"]),
            "alpha":   (C["bg_tertiary"],       C["danger"]),
        }
        bg, fg = type_colors.get(vtype, type_colors["release"])
        badge = QLabel(vtype.capitalize())
        badge.setStyleSheet(
            "background: " + bg + "; color: " + fg +
            "; border-radius: 4px; padding: 2px 7px; font-size: " + _XS + "; font-weight: 700;"
        )
        layout.addWidget(badge)

        num_lbl = QLabel(version.get("version_number", "?"))
        num_lbl.setStyleSheet(
            "font-size: " + _SM + "; font-weight: 700; color: " + C["text_primary"] + ";"
        )
        layout.addWidget(num_lbl, 1)

        loaders = ", ".join(version.get("loaders", []))
        if loaders:
            loader_lbl = QLabel(loaders)
            loader_lbl.setStyleSheet(
                "font-size: " + _XS + "; color: " + C["text_tertiary"] + ";"
            )
            layout.addWidget(loader_lbl)

        btn = QPushButton("Install")
        btn.setFixedSize(72, 28)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background: " + C["accent"] + "; color: " + C["text_inverse"] +
            "; border: none; border-radius: 5px; font-size: " + _XS + "; font-weight: 700; }"
            "QPushButton:hover { background: " + C["accent_blue"] + "; }"
        )
        btn.clicked.connect(lambda: self.install_requested.emit(self._ver))
        layout.addWidget(btn)


class _DepRow(QFrame):
    install_requested = Signal(object)

    def __init__(self, node: DepNode, parent=None) -> None:
        super().__init__(parent)
        self._node = node
        self.setFixedHeight(52)

        type_style = {
            "required":     C["accent_blue"],
            "optional":     C["accent_green"],
            "incompatible": C["danger"],
            "embedded":     C["text_tertiary"],
        }
        border_color = type_style.get(node.dependency_type, C["border"])
        self.setStyleSheet(
            "QFrame { background: " + C["bg_primary"] + "; border: 1px solid " +
            border_color + "; border-radius: 8px; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        type_lbl = QLabel(node.dependency_type.capitalize())
        type_lbl.setStyleSheet(
            "color: " + border_color + "; font-size: " + _XS + "; font-weight: 700;"
        )
        layout.addWidget(type_lbl)

        name_lbl = QLabel(node.title)
        name_lbl.setStyleSheet(
            "font-size: " + _SM + "; font-weight: 700; color: " + C["text_primary"] + ";"
        )
        layout.addWidget(name_lbl, 1)

        ver_lbl = QLabel(node.version_number)
        ver_lbl.setStyleSheet(
            "font-size: " + _XS + "; color: " + C["text_tertiary"] + ";"
        )
        layout.addWidget(ver_lbl)

        if node.already_installed:
            installed_lbl = QLabel("Installed")
            installed_lbl.setStyleSheet(
                "color: " + C["accent_green"] + "; font-size: " + _XS + "; font-weight: 700;"
            )
            layout.addWidget(installed_lbl)
        elif node.dependency_type not in ("incompatible", "embedded"):
            btn = QPushButton("Install")
            btn.setFixedSize(68, 28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: " + C["accent_blue"] + "; color: " + C["text_inverse"] +
                "; border: none; border-radius: 5px; font-size: " + _XS + "; font-weight: 700; }"
                "QPushButton:hover { background: " + C["accent"] + "; }"
            )
            btn.clicked.connect(lambda: self.install_requested.emit(self._node))
            layout.addWidget(btn)


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class ModDetailDialog(QDialog):
    """
    Full detail view for a Modrinth mod project.

    Shows: icon, title, author, download count, categories, description,
    version list, and dependency graph.
    """
    install_version_requested = Signal(dict, dict)   # (project, version)
    install_dep_requested     = Signal(object, dict)  # (DepNode, instance)

    def __init__(
        self,
        project: dict,
        instance: dict | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._project = project
        self._instance = instance
        self._mc_version = (instance or {}).get("mc_version", "")
        self._loader = ""
        self._threads: list[QThread] = []
        self._workers: list[QObject] = []

        self.setWindowTitle(project.get("title", "Mod Details"))
        self.setMinimumSize(740, 560)
        self.setModal(True)
        self.setStyleSheet("background: " + C["bg_secondary"] + ";")
        self._build_ui()
        self._load_async()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background: " + C["bg_primary"] + ";")
        header.setFixedHeight(100)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 16, 24, 16)
        h_layout.setSpacing(16)

        self._icon_lbl = QLabel("MOD")
        self._icon_lbl.setFixedSize(64, 64)
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setStyleSheet(
            "background: " + C["bg_tertiary"] + "; border: 1px solid " + C["border"] +
            "; border-radius: 10px; font-size: " + _XS + "; font-weight: 800; color: " +
            C["text_secondary"] + ";"
        )
        h_layout.addWidget(self._icon_lbl)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        title_lbl = QLabel(self._project.get("title", "Unknown"))
        title_lbl.setStyleSheet(
            "font-size: " + _XL + "; font-weight: 800; color: " + C["text_primary"] + ";"
        )
        info_col.addWidget(title_lbl)

        author_lbl = QLabel(f"by {self._project.get('author', '?')}")
        author_lbl.setStyleSheet(
            "font-size: " + _SM + "; color: " + C["text_secondary"] + ";"
        )
        info_col.addWidget(author_lbl)

        cats_row = QHBoxLayout()
        cats_row.setSpacing(6)
        for cat in (self._project.get("categories", []) or [])[:5]:
            cats_row.addWidget(_CategoryChip(cat))
        cats_row.addStretch()
        info_col.addLayout(cats_row)
        h_layout.addLayout(info_col, 1)

        dl_col = QVBoxLayout()
        dl_col.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        downloads = self._project.get("downloads", 0)
        if downloads >= 1_000_000:
            dl_str = f"{downloads / 1_000_000:.1f}M"
        elif downloads >= 1_000:
            dl_str = f"{downloads / 1_000:.0f}K"
        else:
            dl_str = str(downloads)
        dl_lbl = QLabel(dl_str)
        dl_lbl.setStyleSheet(
            "font-size: " + _LG + "; font-weight: 800; color: " + C["text_primary"] + ";"
        )
        dl_lbl.setAlignment(Qt.AlignRight)
        dl_col.addWidget(dl_lbl)
        dl_sub = QLabel("downloads")
        dl_sub.setStyleSheet(
            "font-size: " + _XS + "; color: " + C["text_tertiary"] + ";"
        )
        dl_sub.setAlignment(Qt.AlignRight)
        dl_col.addWidget(dl_sub)
        h_layout.addLayout(dl_col)

        root.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: " + C["border"] + "; border: none;")
        root.addWidget(sep)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabWidget::pane { border: none; background: " + C["bg_secondary"] + "; }"
            "QTabBar::tab { padding: 8px 18px; font-size: " + _SM + "; color: " + C["text_secondary"] +
            "; border: none; background: transparent; }"
            "QTabBar::tab:selected { color: " + C["accent_blue"] + "; border-bottom: 2px solid " +
            C["accent_blue"] + "; }"
        )
        self._tabs.addTab(self._build_overview_tab(), "Overview")
        self._tabs.addTab(self._build_versions_tab(), "Versions")
        self._tabs.addTab(self._build_deps_tab(), "Dependencies")
        root.addWidget(self._tabs, 1)

        # Footer
        footer = QWidget()
        footer.setStyleSheet("background: " + C["bg_primary"] + ";")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(24, 12, 24, 12)
        f_layout.setSpacing(10)

        self._install_btn = QPushButton("Install Latest")
        self._install_btn.setFixedHeight(36)
        self._install_btn.setCursor(Qt.PointingHandCursor)
        self._install_btn.setStyleSheet(
            "QPushButton { background: " + C["accent"] + "; color: " + C["text_inverse"] +
            "; border: none; border-radius: 7px; padding: 0 20px; font-size: " + _SM +
            "; font-weight: 700; }"
            "QPushButton:hover { background: " + C["accent_blue"] + "; }"
        )
        self._install_btn.clicked.connect(self._install_latest)
        f_layout.addWidget(self._install_btn)

        f_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedSize(80, 36)
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(
            "QPushButton { background: " + C["bg_tertiary"] + "; color: " + C["text_primary"] +
            "; border: 1px solid " + C["border"] + "; border-radius: 7px; font-size: " + _SM + "; }"
            "QPushButton:hover { border-color: " + C["border_strong"] + "; }"
        )
        f_layout.addWidget(close_btn)
        root.addWidget(footer)

    def _build_overview_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: " + C["bg_secondary"] + ";")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(0, 0, 8, 0)
        c_layout.setSpacing(10)

        # Short description
        desc = self._project.get("description", "")
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(
                "font-size: " + _SM + "; color: " + C["text_secondary"] + ";"
            )
            c_layout.addWidget(desc_lbl)

        self._body_lbl = QLabel("Loading description…")
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setAlignment(Qt.AlignTop)
        self._body_lbl.setStyleSheet(
            "font-size: " + _SM + "; color: " + C["text_primary"] + "; line-height: 1.5;"
        )
        self._body_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        c_layout.addWidget(self._body_lbl)
        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return w

    def _build_versions_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: " + C["bg_secondary"] + ";")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(8)

        self._ver_status = QLabel(
            "Showing versions compatible with the active instance."
            if self._mc_version else "Showing all versions."
        )
        self._ver_status.setStyleSheet(
            "font-size: " + _XS + "; color: " + C["text_tertiary"] + ";"
        )
        layout.addWidget(self._ver_status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._ver_area = QVBoxLayout(content)
        self._ver_area.setContentsMargins(0, 0, 8, 0)
        self._ver_area.setSpacing(6)
        self._ver_area.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return w

    def _build_deps_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: " + C["bg_secondary"] + ";")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(8)

        self._deps_status = QLabel("Resolving dependencies…")
        self._deps_status.setStyleSheet(
            "font-size: " + _XS + "; color: " + C["text_tertiary"] + ";"
        )
        layout.addWidget(self._deps_status)

        self._conflict_banner = QLabel("")
        self._conflict_banner.setWordWrap(True)
        self._conflict_banner.setVisible(False)
        self._conflict_banner.setStyleSheet(
            "background: #FEF2F2; color: " + C["danger"] + "; border: 1px solid " + C["danger"] +
            "; border-radius: 6px; padding: 8px 12px; font-size: " + _SM + ";"
        )
        layout.addWidget(self._conflict_banner)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._deps_area = QVBoxLayout(content)
        self._deps_area.setContentsMargins(0, 0, 8, 0)
        self._deps_area.setSpacing(6)
        self._deps_area.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return w

    # ------------------------------------------------------------------
    # Async loading
    # ------------------------------------------------------------------

    def _load_async(self) -> None:
        self._spawn(
            _DetailWorker(self._project["id"]),
            started=lambda: None,
            done=self._on_detail,
            error=lambda e: self._body_lbl.setText(f"Could not load details: {e}"),
        )
        self._spawn(
            _VersionsWorker(self._project["id"], self._mc_version, self._loader),
            done=self._on_versions,
            error=lambda e: self._ver_status.setText(f"Error: {e}"),
        )
        icon_url = self._project.get("icon_url", "")
        if icon_url:
            self._spawn(
                _IconWorker(icon_url),
                done=self._on_icon,
            )

    def _on_detail(self, data: dict) -> None:
        body = data.get("body", "")
        self._body_lbl.setText(_strip_markdown(body) if body else "No description available.")
        # Load first-version deps once we have full project
        versions = data.get("versions", [])
        if versions:
            first_vid = versions[0]
            from ...core.dependency_resolver import resolve_dependencies as _rd
            instance_dir = Path(
                (self._instance or {}).get("directory", "")
            ) if self._instance else Path("")
            installed = set()
            if instance_dir.exists():
                try:
                    from ...core.modrinth import ModrinthError
                    from ..tabs.mods_tab import _load_index
                    idx = _load_index(instance_dir)
                    installed = set(idx.keys())
                except Exception:
                    pass
            self._spawn(
                _DepsWorker(first_vid, self._loader, self._mc_version, installed),
                done=self._on_deps,
                status=self._deps_status.setText,
            )

    def _on_versions(self, versions: list) -> None:
        while self._ver_area.count() > 1:
            item = self._ver_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not versions:
            lbl = QLabel("No compatible versions found.")
            lbl.setStyleSheet(
                "font-size: " + _SM + "; color: " + C["text_tertiary"] + ";"
            )
            self._ver_area.insertWidget(0, lbl)
            return
        self._latest_version = versions[0]
        for v in versions[:25]:
            row = _VersionRow(v, self)
            row.install_requested.connect(
                lambda ver: self.install_version_requested.emit(self._project, ver)
            )
            self._ver_area.insertWidget(self._ver_area.count() - 1, row)

    def _on_deps(self, nodes: list) -> None:
        while self._deps_area.count() > 1:
            item = self._deps_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not nodes:
            self._deps_status.setText("No dependencies.")
            return

        conflicts = detect_conflicts(nodes)
        if conflicts:
            msgs = "\n".join(f"⚠ {c['message']}" for c in conflicts)
            self._conflict_banner.setText(msgs)
            self._conflict_banner.setVisible(True)

        required_count = len(flatten_required(nodes))
        self._deps_status.setText(
            f"{len(nodes)} direct dependencies"
            + (f" · {required_count} to install" if required_count else " · all installed")
        )
        self._populate_dep_rows(nodes, 0)

    def _populate_dep_rows(self, nodes: list[DepNode], indent: int) -> None:
        for node in nodes:
            row = _DepRow(node, self)
            row.install_requested.connect(
                lambda n, inst=self._instance: self.install_dep_requested.emit(n, inst or {})
            )
            self._deps_area.insertWidget(self._deps_area.count() - 1, row)
            if node.children:
                self._populate_dep_rows(node.children, indent + 1)

    def _on_icon(self, path: str) -> None:
        pix = QPixmap(path)
        if not pix.isNull():
            pix = pix.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._icon_lbl.setPixmap(pix)
            self._icon_lbl.setText("")

    def _install_latest(self) -> None:
        latest = getattr(self, "_latest_version", None)
        if latest:
            self.install_version_requested.emit(self._project, latest)
        else:
            self.install_version_requested.emit(self._project, {})

    # ------------------------------------------------------------------
    # Thread helper
    # ------------------------------------------------------------------

    def _spawn(self, worker: QObject, done=None, error=None, started=None, status=None) -> None:
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        if done and hasattr(worker, "done"):
            worker.done.connect(done)
            worker.done.connect(thread.quit)
        if error and hasattr(worker, "error"):
            worker.error.connect(error)
            worker.error.connect(thread.quit)
        if status and hasattr(worker, "status"):
            worker.status.connect(status)
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(
            lambda t=thread: self._threads.remove(t) if t in self._threads else None
        )
        thread.finished.connect(
            lambda w=worker: self._workers.remove(w) if w in self._workers else None
        )
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()
