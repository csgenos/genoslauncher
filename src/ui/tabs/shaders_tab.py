"""
Shaders & Resource Packs tab.

Features:
  - Browse installed shaders from the shaderpacks folder
  - Browse Modrinth shaders with search
  - One-click Iris + Sodium installation
  - Resource packs section
  - "Open folder" shortcuts
  - Drag-and-drop support
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, QObject, Signal, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
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
from ...core.instances import create_custom_instance, list_instances, selected_instance_dir, set_selected_instance
from ...core import modrinth as mr


# ---------------------------------------------------------------------------
# Modrinth shader search worker
# ---------------------------------------------------------------------------

class ShaderSearchWorker(QObject):
    results_ready = Signal(list, int)
    error = Signal(str)

    def __init__(self, query: str, game_version: str) -> None:
        super().__init__()
        self.query = query
        self.game_version = game_version

    def run(self) -> None:
        try:
            hits, total = mr.search_shaders(
                query=self.query,
                game_version=self.game_version,
                limit=16,
            )
            self.results_ready.emit(hits, total)
        except mr.ModrinthError as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Iris + Sodium install worker
# ---------------------------------------------------------------------------

_IRIS_VERSIONS = ["1.21.4", "1.21.1", "1.20.6", "1.20.1", "1.19.4", "1.18.2"]


class IrisInstallWorker(QObject):
    """Installs Fabric loader then downloads Iris and Sodium JARs from Modrinth."""

    progress = Signal(str)
    finished = Signal(bool, str, str)

    IRIS_SLUG   = "iris"
    SODIUM_SLUG = "sodium"

    def __init__(self, mc_version: str, mc_dir: Path) -> None:
        super().__init__()
        self._mc_version = mc_version
        self._mc_dir     = mc_dir

    def run(self) -> None:
        try:
            version_id = self._do_install()
            self.finished.emit(True, "Iris + Sodium installed successfully.", version_id)
        except Exception as exc:
            self.finished.emit(False, str(exc), "")

    def _do_install(self) -> str:
        from ...core.launcher import MLL_AVAILABLE

        # 1. Install Fabric loader
        if not MLL_AVAILABLE:
            raise RuntimeError("minecraft-launcher-lib is required to install Fabric for Iris.")
        import minecraft_launcher_lib as mll
        self.progress.emit(f"Installing Fabric for {self._mc_version}…")
        try:
            loader_version = mll.fabric.get_latest_loader_version()
        except Exception:
            loader_version = ""
        install_kwargs = {
            "minecraft_version": self._mc_version,
            "minecraft_directory": str(self._mc_dir),
            "callback": {"setStatus": lambda t: self.progress.emit(t)},
        }
        if loader_version:
            install_kwargs["loader_version"] = loader_version
        mll.fabric.install_fabric(**install_kwargs)
        fabric_version_id = (
            f"fabric-loader-{loader_version}-{self._mc_version}"
            if loader_version else self._find_installed_fabric_version()
        )
        if not fabric_version_id:
            raise RuntimeError("Fabric installed, but the loader version id could not be verified.")

        # 2. Download Iris and Sodium JARs into <mc_dir>/mods/
        mods_dir = self._mc_dir / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)

        for slug, name in [(self.IRIS_SLUG, "Iris"), (self.SODIUM_SLUG, "Sodium")]:
            self.progress.emit(f"Fetching {name} for {self._mc_version}…")
            versions = mr.get_project_versions(
                slug,
                game_versions=[self._mc_version],
                loaders=["fabric"],
            )
            if not versions:
                raise RuntimeError(
                    f"No {name} release found for Minecraft {self._mc_version} + Fabric.\n"
                    "Try selecting a different version."
                )
            files = versions[0].get("files", [])
            primary = next((f for f in files if f.get("primary")), files[0] if files else None)
            if not primary:
                raise RuntimeError(f"No downloadable file found for {name}.")
            filename = mr.safe_filename(primary["filename"])
            dest = mr.safe_download_path(mods_dir, filename)
            hashes = primary.get("hashes", {})
            if dest.exists() and not mr.verify_file_hash(dest, hashes.get("sha1", ""), hashes.get("sha512", "")):
                dest.unlink(missing_ok=True)
            if not dest.exists():
                self.progress.emit(f"Downloading {primary['filename']}…")
                mr.download_file(
                    primary["url"], dest,
                    expected_sha1=hashes.get("sha1", ""),
                    expected_sha512=hashes.get("sha512", ""),
                )
        return fabric_version_id

    def _find_installed_fabric_version(self) -> str:
        versions_dir = self._mc_dir / "versions"
        if not versions_dir.exists():
            return ""
        prefix = "fabric-loader-"
        suffix = f"-{self._mc_version}"
        matches = sorted(
            child.name for child in versions_dir.iterdir()
            if child.is_dir() and child.name.startswith(prefix) and child.name.endswith(suffix)
        )
        return matches[-1] if matches else ""


class ShaderDownloadWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, project: dict, primary: dict, dest: Path) -> None:
        super().__init__()
        self.project = project
        self.primary = primary
        self.dest = dest

    def run(self) -> None:
        try:
            hashes = self.primary.get("hashes", {})
            mr.download_file(
                self.primary["url"],
                self.dest,
                expected_sha1=hashes.get("sha1", ""),
                expected_sha512=hashes.get("sha512", ""),
            )
            self.finished.emit(True, f"Installed '{self.project['title']}'")
        except Exception as exc:
            self.finished.emit(False, f"Download failed: {exc}")


# ---------------------------------------------------------------------------
# Installed shader row
# ---------------------------------------------------------------------------

class InstalledShaderRow(QFrame):
    """Single row for an installed shader/resource pack file."""

    remove_requested = Signal(str)   # emits filename

    def __init__(self, filename: str, parent=None) -> None:
        super().__init__(parent)
        self._filename = filename
        self.setObjectName("InstalledRow")
        self.setFixedHeight(52)
        self.setStyleSheet(f"""
            #InstalledRow {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(12)

        ext_icon = "🗂" if filename.endswith(".zip") else "📄"
        icon_lbl = QLabel(ext_icon)
        icon_lbl.setFixedWidth(24)
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)

        name_lbl = QLabel(filename)
        name_lbl.setStyleSheet(f"font-size: {FONT['md']}; color: {C['text_primary']}; font-weight: 500;")
        layout.addWidget(name_lbl, 1)

        remove_btn = QPushButton("Remove")
        remove_btn.setFixedSize(72, 30)
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {C["border_strong"]};
                border-radius: 6px;
                font-size: {FONT["xs"]};
                color: {C["text_secondary"]};
            }}
            QPushButton:hover {{
                background: #FEE2E2;
                border-color: {C["danger"]};
                color: {C["danger"]};
            }}
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self._filename))
        layout.addWidget(remove_btn)


# ---------------------------------------------------------------------------
# Modrinth shader card (browse)
# ---------------------------------------------------------------------------

def _fmt_dl(n: int) -> str:
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000:     return f"{n/1_000:.0f}K"
    return str(n)


class ShaderCard(QFrame):
    """Compact card for a Modrinth shader result."""

    install_requested = Signal(dict)

    def __init__(self, project: dict, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self.setObjectName("ShaderCard")
        self.setFixedHeight(88)
        self.setStyleSheet(f"""
            #ShaderCard {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 8px;
            }}
            #ShaderCard:hover {{ border-color: {C["border_strong"]}; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        # Icon
        icon_lbl = QLabel("✨")
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(f"""
            background: {C["bg_tertiary"]};
            border-radius: 8px;
            font-size: 18px;
        """)
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        title_row = QHBoxLayout()
        title_lbl = QLabel(project["title"])
        title_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 600; color: {C['text_primary']};")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        text_col.addLayout(title_row)

        desc_lbl = QLabel(project.get("description", "")[:100])
        desc_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_secondary']};")
        text_col.addWidget(desc_lbl)

        meta_lbl = QLabel(f"by {project.get('author', '?')}  ·  ↓ {_fmt_dl(project.get('downloads', 0))}")
        meta_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        text_col.addWidget(meta_lbl)

        layout.addLayout(text_col, 1)

        install_btn = QPushButton("Install")
        install_btn.setFixedSize(74, 30)
        install_btn.setCursor(Qt.PointingHandCursor)
        install_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C["accent"]};
                color: {C["text_inverse"]};
                border: none;
                border-radius: 6px;
                font-size: {FONT["xs"]};
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #1F2937; }}
            QPushButton:pressed {{ background: #0F172A; }}
        """)
        install_btn.clicked.connect(lambda: self.install_requested.emit(self._project))
        layout.addWidget(install_btn)


# ---------------------------------------------------------------------------
# Section header widget
# ---------------------------------------------------------------------------

class SectionHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        layout.addWidget(title_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
            layout.addWidget(sub_lbl)


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {C['border']}; border: none;")
    return sep


# ---------------------------------------------------------------------------
# Drag-and-drop zone
# ---------------------------------------------------------------------------

class DropZone(QWidget):
    """A dashed-border drop target for shader/resource pack ZIP files."""

    files_dropped = Signal(list)   # list of local file paths

    def __init__(self, label: str = "Drop .zip files here", parent=None) -> None:
        super().__init__(parent)
        self._label = label
        self.setAcceptDrops(True)
        self.setFixedHeight(72)
        self.setStyleSheet("background: transparent;")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)

    def paintEvent(self, _event) -> None:
        from PySide6.QtGui import QPainter, QPainterPath, QPen, QFont
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = 10

        # Dashed border
        pen = QPen(QColor(C["border_strong"]))
        pen.setStyle(Qt.DashLine)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QColor(C["bg_secondary"]))
        painter.drawRoundedRect(2, 2, w - 4, h - 4, r, r)

        # Label
        painter.setPen(QColor(C["text_tertiary"]))
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self._label)
        painter.end()


# ---------------------------------------------------------------------------
# Shaders Tab
# ---------------------------------------------------------------------------

class ShadersTab(QWidget):
    """Shaders and resource packs management tab."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mc_dir = selected_instance_dir()
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._execute_shader_search)
        self._search_threads: list[QThread] = []
        self._install_threads: list[QThread] = []
        self._workers: list[QObject] = []
        self._search_generation = 0
        self.setAcceptDrops(True)
        self._build_ui()
        QTimer.singleShot(300, self._refresh_installed)

    def _shaderpacks_dir(self) -> Path:
        return self._mc_dir / "shaderpacks"

    def _resourcepacks_dir(self) -> Path:
        return self._mc_dir / "resourcepacks"

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
        cl.setContentsMargins(40, 28, 40, 40)
        cl.setSpacing(28)

        # ---- Page header ----
        page_header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        title = QLabel("Shaders & Resource Packs")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        title_col.addWidget(title)
        sub = QLabel("Manage visual enhancements and texture packs for your Minecraft instances.")
        sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        title_col.addWidget(sub)
        page_header.addLayout(title_col)
        page_header.addStretch()
        self._instance_combo = QComboBox()
        self._instance_combo.setFixedSize(240, 36)
        self._instance_combo.currentIndexChanged.connect(self._on_instance_changed)
        page_header.addWidget(self._instance_combo)
        cl.addLayout(page_header)

        # ---- Iris + Sodium quick install ----
        iris_card = self._build_iris_card()
        cl.addWidget(iris_card)

        cl.addWidget(_separator())

        # ---- Installed shaders ----
        sh_header = QHBoxLayout()
        sh_header.addWidget(SectionHeader("Installed Shaders", "Drop a .zip here or install from Modrinth below"))
        sh_header.addStretch()
        open_sh_btn = QPushButton("Open Folder")
        open_sh_btn.setFixedHeight(32)
        open_sh_btn.setCursor(Qt.PointingHandCursor)
        open_sh_btn.setStyleSheet(self._outline_btn_style())
        open_sh_btn.clicked.connect(lambda: self._open_folder(self._shaderpacks_dir()))
        sh_header.addWidget(open_sh_btn)
        cl.addLayout(sh_header)

        # Drop zone
        self._shader_drop = DropZone("Drop shader .zip files here to install", self)
        self._shader_drop.files_dropped.connect(lambda paths: self._install_dropped(paths, "shaderpacks"))
        cl.addWidget(self._shader_drop)

        # Installed list
        self._installed_shader_container = QVBoxLayout()
        self._installed_shader_container.setSpacing(6)
        cl.addLayout(self._installed_shader_container)

        cl.addWidget(_separator())

        # ---- Resource Packs ----
        rp_header = QHBoxLayout()
        rp_header.addWidget(SectionHeader("Resource Packs", "Custom textures and assets"))
        rp_header.addStretch()
        open_rp_btn = QPushButton("Open Folder")
        open_rp_btn.setFixedHeight(32)
        open_rp_btn.setCursor(Qt.PointingHandCursor)
        open_rp_btn.setStyleSheet(self._outline_btn_style())
        open_rp_btn.clicked.connect(lambda: self._open_folder(self._resourcepacks_dir()))
        rp_header.addWidget(open_rp_btn)
        cl.addLayout(rp_header)

        self._rp_drop = DropZone("Drop resource pack .zip files here to install", self)
        self._rp_drop.files_dropped.connect(lambda paths: self._install_dropped(paths, "resourcepacks"))
        cl.addWidget(self._rp_drop)

        self._installed_rp_container = QVBoxLayout()
        self._installed_rp_container.setSpacing(6)
        cl.addLayout(self._installed_rp_container)

        cl.addWidget(_separator())

        # ---- Browse Modrinth Shaders ----
        cl.addWidget(SectionHeader("Browse Shaders on Modrinth"))

        # Search bar
        search_row = QHBoxLayout()
        self._shader_search = QLineEdit()
        self._shader_search.setPlaceholderText("Search shaders…")
        self._shader_search.setFixedHeight(38)
        self._shader_search.textChanged.connect(lambda _: self._search_timer.start(400))
        search_row.addWidget(self._shader_search)

        self._shader_ver = QComboBox()
        self._shader_ver.setFixedSize(130, 38)
        for v in ["Any version", "1.21.4", "1.21.1", "1.20.1", "1.19.4", "1.18.2"]:
            self._shader_ver.addItem(v)
        self._shader_ver.currentTextChanged.connect(lambda _: self._search_timer.start(400))
        search_row.addWidget(self._shader_ver)
        cl.addLayout(search_row)

        self._shader_status = QLabel("Loading shaders…")
        self._shader_status.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        cl.addWidget(self._shader_status)

        self._shader_results_layout = QVBoxLayout()
        self._shader_results_layout.setSpacing(8)
        cl.addLayout(self._shader_results_layout)

        cl.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)
        self._reload_instances()

    def _reload_instances(self) -> None:
        self._instance_combo.blockSignals(True)
        self._instance_combo.clear()
        active_id = config.get("selected_instance_id", "")
        instances = list_instances()
        if not instances:
            self._instance_combo.addItem("Default Minecraft folder", "")
            self._mc_dir = Path(config.get("minecraft_dir", str(APP_DIR / "minecraft")))
        else:
            for instance in instances:
                self._instance_combo.addItem(instance.get("name", "Instance"), instance.get("id", ""))
            index = max(0, self._instance_combo.findData(active_id))
            self._instance_combo.setCurrentIndex(index)
            self._mc_dir = Path(instances[index].get("directory", self._mc_dir))
        self._instance_combo.blockSignals(False)

    def _on_instance_changed(self, index: int) -> None:
        instance_id = self._instance_combo.itemData(index) or ""
        set_selected_instance(instance_id)
        self._mc_dir = selected_instance_dir()
        self._refresh_installed()

    def _build_iris_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("IrisCard")
        card.setFixedHeight(100)
        card.setStyleSheet(f"""
            #IrisCard {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 12px;
            }}
        """)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(16)

        # Icon area
        icon_box = QLabel("⚡")
        icon_box.setFixedSize(52, 52)
        icon_box.setAlignment(Qt.AlignCenter)
        icon_box.setStyleSheet(f"""
            background: {C["bg_secondary"]};
            border: 1px solid {C["border"]};
            border-radius: 10px;
            font-size: 22px;
        """)
        layout.addWidget(icon_box)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        title = QLabel("Iris + Sodium")
        title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        text_col.addWidget(title)
        sub = QLabel("The fastest Fabric rendering pipeline. Required to use shaders on modern versions.")
        sub.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        sub.setWordWrap(True)
        text_col.addWidget(sub)
        layout.addLayout(text_col, 1)

        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        right_col.setContentsMargins(0, 0, 0, 0)

        self._iris_version_combo = QComboBox()
        self._iris_version_combo.setFixedSize(130, 30)
        self._iris_version_combo.setStyleSheet(f"""
            QComboBox {{
                background: {C["bg_secondary"]};
                border: 1px solid {C["border"]};
                border-radius: 6px;
                padding: 0 8px;
                font-size: {FONT["xs"]};
                color: {C["text_primary"]};
            }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
        """)
        for v in _IRIS_VERSIONS:
            self._iris_version_combo.addItem(v)
        current_ver = config.get("selected_version", "1.21.4") or "1.21.4"
        idx = self._iris_version_combo.findText(current_ver)
        if idx >= 0:
            self._iris_version_combo.setCurrentIndex(idx)
        right_col.addWidget(self._iris_version_combo)

        self._iris_btn = QPushButton("Install")
        self._iris_btn.setFixedSize(130, 34)
        self._iris_btn.setCursor(Qt.PointingHandCursor)
        self._iris_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C["accent"]};
                color: {C["text_inverse"]};
                border: none;
                border-radius: 8px;
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
        self._iris_btn.clicked.connect(self._install_iris)
        right_col.addWidget(self._iris_btn)

        layout.addLayout(right_col)

        return card

    def _outline_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {C["border_strong"]};
                border-radius: 7px;
                padding: 0 12px;
                font-size: {FONT["xs"]};
                color: {C["text_secondary"]};
            }}
            QPushButton:hover {{
                background: {C["bg_hover"]};
                color: {C["text_primary"]};
            }}
        """

    # ------------------------------------------------------------------
    # Installed files
    # ------------------------------------------------------------------

    def _refresh_installed(self) -> None:
        self._populate_installed(self._shaderpacks_dir(), self._installed_shader_container, "shader")
        self._populate_installed(self._resourcepacks_dir(), self._installed_rp_container, "resourcepack")
        self._execute_shader_search()

    def _populate_installed(self, folder: Path, container: QVBoxLayout, kind: str) -> None:
        # Clear
        while container.count():
            item = container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not folder.exists():
            empty = QLabel(f"No {kind}s installed yet.")
            empty.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_tertiary']}; padding: 8px 0;")
            container.addWidget(empty)
            return

        files = sorted(
            [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".zip"],
            key=lambda f: f.stat().st_mtime, reverse=True,
        )
        if not files:
            empty = QLabel(f"No {kind}s installed yet.")
            empty.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_tertiary']}; padding: 8px 0;")
            container.addWidget(empty)
        for f in files[:10]:
            row = InstalledShaderRow(f.name)
            row.remove_requested.connect(
                lambda name, folder=folder: self._remove_file(folder / name)
            )
            container.addWidget(row)

    def _remove_file(self, file_path: Path) -> None:
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
        self._refresh_installed()

    def _install_dropped(self, paths: list[str], subdir: str) -> None:
        dest_dir = self._mc_dir / subdir
        dest_dir.mkdir(parents=True, exist_ok=True)
        installed = 0
        rejected: list[str] = []
        for path in paths:
            src = Path(path)
            if src.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(src) as zf:
                        mr._validate_zip_limits(zf)
                except Exception as exc:
                    self._shader_status.setText(f"Rejected {src.name}: {exc}")
                    continue
                import shutil
                dest = mr.safe_download_path(dest_dir, src.name)
                shutil.copy2(src, dest)
                installed += 1
            else:
                rejected.append(src.name)
        if installed and rejected:
            self._shader_status.setText(
                f"Installed {installed} archive(s); ignored {len(rejected)} non-.zip file(s)."
            )
        elif rejected:
            self._shader_status.setText(
                f"Ignored {len(rejected)} unsupported file(s). Only .zip packs can be installed."
            )
        self._refresh_installed()

    # ------------------------------------------------------------------
    # Iris + Sodium install
    # ------------------------------------------------------------------

    def _install_iris(self) -> None:
        mc_version = self._iris_version_combo.currentText()
        self._iris_btn.setText("Installing…")
        self._iris_btn.setEnabled(False)
        self._iris_version_combo.setEnabled(False)

        thread = QThread(self)
        worker = IrisInstallWorker(mc_version, self._mc_dir)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def on_progress(status: str) -> None:
            self._iris_btn.setText(status[:14] if status else "Installing…")

        def on_finished(success: bool, message: str, fabric_version_id: str) -> None:
            self._iris_version_combo.setEnabled(True)
            if success:
                instance = create_custom_instance(
                    f"Iris + Sodium {mc_version}",
                    fabric_version_id,
                    directory=self._mc_dir,
                )
                set_selected_instance(instance["id"])
                self._iris_btn.setText("Installed ✓")
                self._iris_btn.setEnabled(False)
            else:
                self._iris_btn.setText("Install")
                self._iris_btn.setEnabled(True)
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Install Failed", message)

        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        worker.finished.connect(thread.quit)
        self._install_threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(
            lambda: self._install_threads.remove(thread)
            if thread in self._install_threads else None
        )
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    # ------------------------------------------------------------------
    # Modrinth shader search
    # ------------------------------------------------------------------

    def _execute_shader_search(self) -> None:
        query = self._shader_search.text().strip() if hasattr(self, '_shader_search') else ""
        ver = self._shader_ver.currentText() if hasattr(self, '_shader_ver') else ""
        game_version = "" if ver.startswith("Any") else ver

        self._shader_status.setText("Searching…")
        self._search_generation += 1
        generation = self._search_generation
        # Clear old results
        while self._shader_results_layout.count():
            item = self._shader_results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        thread = QThread(self)
        worker = ShaderSearchWorker(query, game_version)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.results_ready.connect(lambda hits, total, gen=generation: self._on_shader_results(gen, hits, total))
        worker.error.connect(lambda e, gen=generation: self._on_shader_error(gen, e))
        worker.results_ready.connect(thread.quit)
        worker.error.connect(thread.quit)
        self._search_threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda: self._search_threads.remove(thread) if thread in self._search_threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_shader_results(self, generation: int, hits: list[dict], total: int) -> None:
        if generation != self._search_generation:
            return
        self._shader_status.setText(f"{total:,} shaders found on Modrinth")
        for project in hits:
            card = ShaderCard(project, self)
            card.install_requested.connect(self._on_shader_install)
            self._shader_results_layout.addWidget(card)

    def _on_shader_error(self, generation: int, msg: str) -> None:
        if generation != self._search_generation:
            return
        self._shader_status.setText(f"Error: {msg}")

    def _on_shader_install(self, project: dict) -> None:
        self._shader_status.setText(f"Fetching versions for '{project['title']}'…")

        thread = QThread(self)
        ver = self._shader_ver.currentText() if hasattr(self, "_shader_ver") else ""
        game_version = "" if ver.startswith("Any") else ver

        class VersionFetcher(QObject):
            done = Signal(list)
            err  = Signal(str)
            def __init__(self, pid, game_version):
                super().__init__()
                self.pid = pid
                self.game_version = game_version
            def run(self):
                try:
                    self.done.emit(mr.get_project_versions(
                        self.pid,
                        game_versions=[self.game_version] if self.game_version else None,
                    ))
                except mr.ModrinthError as e: self.err.emit(str(e))

        fetcher = VersionFetcher(project["id"], game_version)
        fetcher.moveToThread(thread)
        thread.started.connect(fetcher.run)
        fetcher.done.connect(lambda versions: self._start_shader_download(project, versions))
        fetcher.err.connect(lambda e: self._shader_status.setText(f"Error: {e}"))
        fetcher.done.connect(thread.quit)
        fetcher.err.connect(thread.quit)
        self._search_threads.append(thread)
        self._workers.append(fetcher)
        thread.finished.connect(
            lambda: self._search_threads.remove(thread) if thread in self._search_threads else None
        )
        thread.finished.connect(lambda: self._workers.remove(fetcher) if fetcher in self._workers else None)
        thread.finished.connect(fetcher.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _start_shader_download(self, project: dict, versions: list[dict]) -> None:
        if not versions:
            self._shader_status.setText("No versions available.")
            return
        version = versions[0]
        files = version.get("files", [])
        primary = next((f for f in files if f.get("primary")), files[0] if files else None)
        if not primary:
            self._shader_status.setText("No file found for this shader.")
            return

        filename = mr.safe_filename(primary["filename"])
        dest = mr.safe_download_path(self._shaderpacks_dir(), filename)
        self._shader_status.setText(f"Downloading {primary['filename']}…")

        thread = QThread(self)
        worker = ShaderDownloadWorker(project, primary, dest)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda ok, msg: self._on_shader_download_finished(ok, msg))
        worker.finished.connect(thread.quit)
        self._search_threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda: self._search_threads.remove(thread) if thread in self._search_threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_shader_download_finished(self, success: bool, message: str) -> None:
        self._shader_status.setText(message)
        if success:
            self._refresh_installed()

    # ------------------------------------------------------------------
    # Open folder
    # ------------------------------------------------------------------

    def _open_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
