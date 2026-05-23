"""Modrinth + CurseForge mods browser, per-instance mod installer, update checker, and mod profiles."""

from __future__ import annotations

import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ...core import modrinth as mr
from ...core.config import APP_DIR, config
from ...core.instances import list_instances, selected_instance, selected_instance_dir, set_selected_instance
from ...core import curseforge as cf

_XS  = FONT["xs"]
_SM  = FONT["sm"]
_MD  = FONT["md"]
_2XL = FONT["2xl"]

_ICON_CACHE = APP_DIR / "cache" / "mod_icons"

# ---------------------------------------------------------------------------
# Mod metadata helpers
# ---------------------------------------------------------------------------

def _index_path(instance_dir: Path) -> Path:
    return instance_dir / "mods_index.json"


def _load_index(instance_dir: Path) -> dict:
    p = _index_path(instance_dir)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            backup = p.with_suffix(f".corrupt-{int(time.time())}.json")
            try:
                shutil.copy2(p, backup)
            except OSError:
                pass
    return {}


def _save_index(instance_dir: Path, index: dict) -> None:
    p = _index_path(instance_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _register_mod(instance_dir: Path, project: dict, version: dict, filename: str) -> None:
    index = _load_index(instance_dir)
    project_id = str(project["id"])
    index[project_id] = {
        "project_id":     project_id,
        "source":         project.get("source", "modrinth"),
        "cf_id":          project.get("cf_id", ""),
        "file_id":        version.get("file_id", version.get("id", "")),
        "version_id":     version.get("id", ""),
        "version_number": version.get("version_number", ""),
        "filename":       filename,
        "title":          project.get("title", filename),
        "installed_at":   datetime.now(timezone.utc).isoformat(),
    }
    _save_index(instance_dir, index)


# ---------------------------------------------------------------------------
# Mod profile helpers
# ---------------------------------------------------------------------------

def _profile_path(instance_dir: Path) -> Path:
    return instance_dir / "mod_profiles.json"


def _load_profiles(instance_dir: Path) -> dict:
    def _default_profiles() -> dict:
        mods_dir = instance_dir / "mods"
        mods = [f.name for f in mods_dir.iterdir() if f.suffix.lower() == ".jar"] if mods_dir.exists() else []
        return {"active": "Default", "profiles": {"Default": mods}}

    p = _profile_path(instance_dir)
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Profile root must be an object.")
            profiles = raw.get("profiles", {})
            if not isinstance(profiles, dict):
                raise ValueError("profiles must be an object.")
            cleaned_profiles: dict[str, list[str]] = {}
            for name, values in profiles.items():
                if not isinstance(name, str):
                    continue
                if not isinstance(values, list):
                    continue
                cleaned_profiles[name] = [v for v in values if isinstance(v, str)]
            if "Default" not in cleaned_profiles:
                cleaned_profiles["Default"] = []
            active = raw.get("active", "Default")
            if not isinstance(active, str) or active not in cleaned_profiles:
                active = "Default"
            return {"active": active, "profiles": cleaned_profiles}
        except Exception:
            backup = p.with_suffix(f".corrupt-{int(time.time())}.json")
            try:
                shutil.copy2(p, backup)
            except OSError:
                pass
    return _default_profiles()


def _save_profiles(instance_dir: Path, data: dict) -> None:
    p = _profile_path(instance_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _switch_profile(instance_dir: Path, new_profile: str) -> None:
    data = _load_profiles(instance_dir)
    if new_profile not in data["profiles"]:
        return
    mods_dir     = instance_dir / "mods"
    disabled_dir = instance_dir / ".disabled_mods"
    mods_dir.mkdir(exist_ok=True)
    disabled_dir.mkdir(exist_ok=True)

    enabled_set = set(data["profiles"][new_profile])
    moves: list[tuple[Path, Path]] = []
    for f in list(mods_dir.iterdir()):
        if f.suffix.lower() == ".jar" and f.name not in enabled_set:
            moves.append((f, disabled_dir / f.name))
    for f in list(disabled_dir.iterdir()):
        if f.suffix.lower() == ".jar" and f.name in enabled_set:
            moves.append((f, mods_dir / f.name))

    completed: list[tuple[Path, Path]] = []
    try:
        for src, dst in moves:
            if dst.exists():
                raise RuntimeError(f"Cannot switch profile because '{dst.name}' already exists.")
            src.replace(dst)
            completed.append((src, dst))
    except Exception:
        for src, dst in reversed(completed):
            try:
                if dst.exists() and not src.exists():
                    dst.replace(src)
            except OSError:
                pass
        raise

    data["active"] = new_profile
    _save_profiles(instance_dir, data)


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class CFSearchWorker(QObject):
    results_ready = Signal(list, int)
    error = Signal(str)

    def __init__(self, query: str, game_version: str) -> None:
        super().__init__()
        self.query = query
        self.game_version = game_version

    def run(self) -> None:
        try:
            hits, total = cf.search_mods(self.query, self.game_version)
            self.results_ready.emit(hits, total)
        except cf.CurseForgeError as exc:
            self.error.emit(str(exc))


class ModSearchWorker(QObject):
    results_ready = Signal(list, int)
    error = Signal(str)

    def __init__(self, query: str, game_version: str, loader: str, sort_index: str) -> None:
        super().__init__()
        self.query = query
        self.game_version = game_version
        self.loader = loader
        self.sort_index = sort_index

    def run(self) -> None:
        try:
            hits, total = mr.search_projects(
                query=self.query,
                project_type="mod",
                game_version=self.game_version,
                limit=18,
                categories=[self.loader] if self.loader else None,
                sort_index=self.sort_index,
            )
            self.results_ready.emit(hits, total)
        except mr.ModrinthError as exc:
            self.error.emit(str(exc))


class ModInstallWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, project: dict, version: dict | None, instance: dict | None, fallback_dir: Path) -> None:
        super().__init__()
        self.project = project
        self.version = version
        self.instance = instance
        self.fallback_dir = fallback_dir

    def run(self) -> None:
        try:
            mc_version   = (self.instance or {}).get("mc_version", "")
            instance_dir = Path((self.instance or {}).get("directory", str(self.fallback_dir)))
            mods_dir     = instance_dir / "mods"
            mods_dir.mkdir(parents=True, exist_ok=True)

            if self.project.get("source") == "curseforge":
                files = cf.get_mod_files(int(self.project["cf_id"]), mc_version)
                if not files:
                    raise cf.CurseForgeError("No compatible CurseForge files found.")
                version = files[0]
                file_id = int(version.get("id", 0))
                url = version.get("downloadUrl") or cf.get_download_url(int(self.project["cf_id"]), file_id)
                if not url:
                    raise cf.CurseForgeError("CurseForge did not provide a download URL.")
                filename = mr.safe_filename(version.get("fileName", "mod.jar"))
                sha1, sha512 = cf.hashes_for_file(version)
                dest = mr.safe_download_path(mods_dir, filename)
                cf.download_file(url, dest, expected_sha1=sha1, expected_sha512=sha512)
                index_version = {
                    "id": str(file_id),
                    "file_id": str(file_id),
                    "version_number": version.get("displayName", filename),
                }
                _register_mod(instance_dir, self.project, index_version, filename)
            else:
                version = self.version
                if not version:
                    versions = mr.get_project_versions(
                        self.project["id"],
                        game_versions=[mc_version] if mc_version else None,
                    )
                    if not versions:
                        raise mr.ModrinthError("No compatible versions found.")
                    version = versions[0]
                files   = version.get("files", [])
                primary = next((f for f in files if f.get("primary")), files[0] if files else None)
                if not primary:
                    raise mr.ModrinthError("No downloadable mod file found.")

                hashes   = primary.get("hashes", {})
                filename = mr.safe_filename(primary["filename"])
                dest     = mr.safe_download_path(mods_dir, filename)
                mr.download_file(
                    primary["url"], dest,
                    expected_sha1=hashes.get("sha1", ""),
                    expected_sha512=hashes.get("sha512", ""),
                )
                _register_mod(instance_dir, self.project, version, filename)

            name = self.project.get("title", filename)
            self.finished.emit(True, f"Installed {name}.")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class ModUpdateWorker(QObject):
    updates_found = Signal(list)
    status        = Signal(str)

    def __init__(self, instance: dict) -> None:
        super().__init__()
        self._instance = instance

    def run(self) -> None:
        instance_dir = Path(self._instance.get("directory", ""))
        mc_version   = self._instance.get("mc_version", "")
        index        = _load_index(instance_dir)
        if not index:
            self.status.emit("No tracked mods for this instance.")
            self.updates_found.emit([])
            return
        updates: list[dict] = []
        items = list(index.items())

        def _check_one(item: tuple[str, dict], pos: int) -> dict | None:
            project_id, entry = item
            try:
                if entry.get("source") == "curseforge":
                    cf_id = int(entry.get("cf_id") or entry.get("project_id") or 0)
                    if not cf_id:
                        return None
                    files = cf.get_mod_files(cf_id, mc_version)
                    if not files:
                        return None
                    latest = files[0]
                    latest_file_id = str(latest.get("id", ""))
                    if latest_file_id and latest_file_id != str(entry.get("file_id") or entry.get("version_id")):
                        return {
                            "source":                "curseforge",
                            "project_id":            project_id,
                            "cf_id":                 cf_id,
                            "title":                 entry.get("title", project_id),
                            "current_version":       entry.get("version_number", "?"),
                            "current_filename":      entry.get("filename", ""),
                            "latest_version_id":     latest_file_id,
                            "latest_version_number": latest.get("displayName", latest.get("fileName", "?")),
                            "latest_file":           latest,
                            "instance_dir":          str(instance_dir),
                        }
                else:
                    versions = mr.get_project_versions(
                        project_id,
                        game_versions=[mc_version] if mc_version else None,
                    )
                    if not versions:
                        return None
                    latest = versions[0]
                    if latest.get("id") != entry.get("version_id"):
                        files   = latest.get("files", [])
                        primary = next((f for f in files if f.get("primary")), files[0] if files else None)
                        return {
                            "source":                "modrinth",
                            "project_id":            project_id,
                            "title":                 entry.get("title", project_id),
                            "current_version":       entry.get("version_number", "?"),
                            "current_filename":      entry.get("filename", ""),
                            "latest_version_id":     latest.get("id", ""),
                            "latest_version_number": latest.get("version_number", "?"),
                            "latest_file":           primary,
                            "instance_dir":          str(instance_dir),
                        }
            except Exception:
                return None
            return None

        with ThreadPoolExecutor(max_workers=min(8, max(2, len(items)))) as pool:
            future_map = {pool.submit(_check_one, item, idx): (idx, item) for idx, item in enumerate(items, start=1)}
            for fut in as_completed(future_map):
                idx, item = future_map[fut]
                project_id, entry = item
                self.status.emit(f"Checking {idx}/{len(items)}: {entry.get('title', project_id)}…")
                result = fut.result()
                if result:
                    updates.append(result)
        msg = f"{len(updates)} update(s) available." if updates else "All mods are up to date."
        self.status.emit(msg)
        self.updates_found.emit(updates)


class ModApplyUpdateWorker(QObject):
    finished = Signal(bool, str, dict)

    def __init__(self, info: dict) -> None:
        super().__init__()
        self._info = info

    def run(self) -> None:
        info = self._info
        latest_file = info.get("latest_file")
        if not latest_file:
            self.finished.emit(False, "No update payload found.", info)
            return
        try:
            instance_dir = Path(info["instance_dir"])
            mods_dir = instance_dir / "mods"
            if info.get("source") == "curseforge":
                filename = mr.safe_filename(latest_file.get("fileName", "mod.jar"))
                dest = mr.safe_download_path(mods_dir, filename)
                sha1, sha512 = cf.hashes_for_file(latest_file)
                url = latest_file.get("downloadUrl") or cf.get_download_url(
                    int(info.get("cf_id", 0)),
                    int(info["latest_version_id"]),
                )
                cf.download_file(url, dest, expected_sha1=sha1, expected_sha512=sha512)
            else:
                hashes = latest_file.get("hashes", {})
                filename = mr.safe_filename(latest_file["filename"])
                dest = mr.safe_download_path(mods_dir, filename)
                mr.download_file(
                    latest_file["url"], dest,
                    expected_sha1=hashes.get("sha1", ""),
                    expected_sha512=hashes.get("sha512", ""),
                )
            old_name = info.get("current_filename", "")
            if old_name:
                old = mr.safe_download_path(mods_dir, old_name)
                if old.exists() and old != dest:
                    old.unlink(missing_ok=True)
            index = _load_index(instance_dir)
            pid = info["project_id"]
            if pid in index:
                index[pid]["version_id"] = info["latest_version_id"]
                index[pid]["file_id"] = info["latest_version_id"]
                index[pid]["source"] = info.get("source", index[pid].get("source", "modrinth"))
                index[pid]["version_number"] = info["latest_version_number"]
                index[pid]["filename"] = filename
                _save_index(instance_dir, index)
            self.finished.emit(True, f"Updated {info['title']}.", info)
        except Exception as exc:
            self.finished.emit(False, f"Update failed: {exc}", info)


class _IconLoader(QObject):
    done = Signal(str, str)  # project_id, path

    def __init__(self, project_id: str, icon_url: str) -> None:
        super().__init__()
        self._id = project_id
        self._url = icon_url

    def run(self) -> None:
        _ICON_CACHE.mkdir(parents=True, exist_ok=True)
        path = mr.download_icon(self._url, _ICON_CACHE)
        if path:
            self.done.emit(self._id, str(path))


# ---------------------------------------------------------------------------
# Mod cards
# ---------------------------------------------------------------------------

class ModUpdateCard(QFrame):
    update_requested = Signal(dict)

    def __init__(self, info: dict, parent=None) -> None:
        super().__init__(parent)
        self._info = info
        self.setObjectName("ModUpdateCard")
        self.setFixedHeight(56)
        self.setStyleSheet(
            "#ModUpdateCard { background: " + C["bg_primary"] + "; border: 1px solid " +
            C["border"] + "; border-radius: 8px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        name = QLabel(info["title"])
        name.setStyleSheet(
            "font-size: " + _SM + "; font-weight: 700; color: " + C["text_primary"] + ";"
        )
        layout.addWidget(name, 1)

        ver_lbl = QLabel(f"{info['current_version']}  →  {info['latest_version_number']}")
        ver_lbl.setStyleSheet("font-size: " + _XS + "; color: " + C["text_secondary"] + ";")
        layout.addWidget(ver_lbl)

        self._btn = QPushButton("Update")
        self._btn.setFixedSize(72, 28)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setStyleSheet(
            "QPushButton { background: " + C["accent"] + "; color: " + C["text_inverse"] +
            "; border: none; border-radius: 5px; font-size: " + _XS + "; font-weight: 700; }"
            "QPushButton:hover { background: #1F2937; }"
            "QPushButton:disabled { background: " + C["bg_tertiary"] + "; color: " + C["text_disabled"] + "; }"
        )
        self._btn.clicked.connect(lambda: self.update_requested.emit(self._info))
        layout.addWidget(self._btn)

    def set_updated(self) -> None:
        self._btn.setText("Done")
        self._btn.setEnabled(False)


def _fmt_dl(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


class ModCard(QFrame):
    install_requested     = Signal(dict)
    view_details_requested = Signal(dict)

    def __init__(self, project: dict, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self.setObjectName("ModCard")
        self.setFixedHeight(100)
        self.setStyleSheet(
            "#ModCard { background: " + C["bg_primary"] + "; border: 1px solid " +
            C["border"] + "; border-radius: 8px; }"
            "#ModCard:hover { border-color: " + C["border_strong"] + "; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        self._icon_lbl = QLabel("MOD")
        self._icon_lbl.setFixedSize(52, 52)
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._icon_lbl.setStyleSheet(
            "background: " + C["bg_secondary"] + "; border: 1px solid " + C["border"] +
            "; border-radius: 8px; font-size: " + _XS + "; font-weight: 800; color: " + C["text_secondary"] + ";"
        )
        layout.addWidget(self._icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        title_row = QHBoxLayout()
        title = QLabel(project.get("title", "Unknown Mod"))
        title.setStyleSheet(
            "font-size: " + _MD + "; font-weight: 700; color: " + C["text_primary"] + ";"
        )
        title_row.addWidget(title)

        cats = project.get("categories", []) or []
        for cat in cats[:3]:
            chip = QLabel(cat)
            chip.setStyleSheet(
                "background: " + C["bg_tertiary"] + "; color: " + C["text_secondary"] +
                "; border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: 600;"
            )
            title_row.addWidget(chip)
        title_row.addStretch()
        text_col.addLayout(title_row)

        desc = QLabel(project.get("description", "")[:110])
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: " + _XS + "; color: " + C["text_secondary"] + ";")
        text_col.addWidget(desc)

        meta = QLabel(
            f"by {project.get('author', '?')}  ·  "
            f"{_fmt_dl(project.get('downloads', 0))} downloads"
        )
        meta.setStyleSheet("font-size: " + _XS + "; color: " + C["text_tertiary"] + ";")
        text_col.addWidget(meta)
        layout.addLayout(text_col, 1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)
        btn_col.setAlignment(Qt.AlignVCenter)

        install = QPushButton("Install")
        install.setFixedSize(78, 32)
        install.setCursor(Qt.PointingHandCursor)
        install.setStyleSheet(
            "QPushButton { background: " + C["accent"] + "; color: " + C["text_inverse"] +
            "; border: none; border-radius: 6px; font-size: " + _XS + "; font-weight: 700; }"
            "QPushButton:hover { background: " + C["accent_blue"] + "; }"
        )
        install.clicked.connect(lambda: self.install_requested.emit(self._project))
        btn_col.addWidget(install)

        details = QPushButton("Details")
        details.setFixedSize(78, 26)
        details.setCursor(Qt.PointingHandCursor)
        details.setStyleSheet(
            "QPushButton { background: transparent; color: " + C["text_secondary"] +
            "; border: 1px solid " + C["border"] + "; border-radius: 5px; font-size: " + _XS + "; }"
            "QPushButton:hover { border-color: " + C["border_strong"] + "; color: " + C["text_primary"] + "; }"
        )
        details.clicked.connect(lambda: self.view_details_requested.emit(self._project))
        btn_col.addWidget(details)

        layout.addLayout(btn_col)

    def set_icon(self, pixmap: QPixmap) -> None:
        if not pixmap.isNull():
            scaled = pixmap.scaled(52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._icon_lbl.setPixmap(scaled)
            self._icon_lbl.setText("")


# ---------------------------------------------------------------------------
# Mods Tab
# ---------------------------------------------------------------------------

class ModsTab(QWidget):
    """Search Modrinth / CurseForge mods and install them into the active instance."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._execute_search)
        self._threads: list[QThread] = []
        self._workers: list[QObject] = []
        self._search_generation = 0
        self._active_search_thread: QThread | None = None
        self._search_pending = False
        self._cards: dict[str, ModCard] = {}
        self._build_ui()
        QTimer.singleShot(250, self.refresh_instances)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 28, 40, 28)
        root.setSpacing(14)

        # Header row
        header = QHBoxLayout()
        title = QLabel("Mods")
        title.setStyleSheet(
            "font-size: " + _2XL + "; font-weight: 800; color: " + C["text_primary"] + ";"
        )
        header.addWidget(title)
        header.addStretch()

        self._check_updates_btn = QPushButton("Check for Updates")
        self._check_updates_btn.setFixedHeight(34)
        self._check_updates_btn.setCursor(Qt.PointingHandCursor)
        self._check_updates_btn.setStyleSheet(
            "QPushButton { background: transparent; color: " + C["text_secondary"] +
            "; border: 1px solid " + C["border"] + "; border-radius: 7px; padding: 0 14px;"
            " font-size: " + _SM + "; }"
            "QPushButton:hover { border-color: " + C["border_strong"] + "; color: " + C["text_primary"] + "; }"
        )
        self._check_updates_btn.clicked.connect(self._run_update_check)
        header.addWidget(self._check_updates_btn)

        self._instance_combo = QComboBox()
        self._instance_combo.setFixedSize(260, 36)
        self._instance_combo.currentIndexChanged.connect(self._on_instance_changed)
        header.addWidget(self._instance_combo)
        root.addLayout(header)

        # Source + profile row
        src_row = QHBoxLayout()
        src_lbl = QLabel("Source:")
        src_lbl.setStyleSheet("font-size: " + _SM + "; color: " + C["text_secondary"] + ";")
        src_row.addWidget(src_lbl)
        self._source_combo = QComboBox()
        self._source_combo.addItem("Modrinth", "modrinth")
        self._source_combo.addItem("CurseForge", "curseforge")
        self._source_combo.setFixedSize(140, 30)
        self._source_combo.currentIndexChanged.connect(lambda _: self._on_source_changed())
        src_row.addWidget(self._source_combo)
        src_row.addSpacing(12)

        prof_lbl = QLabel("Profile:")
        prof_lbl.setStyleSheet("font-size: " + _SM + "; color: " + C["text_secondary"] + ";")
        src_row.addWidget(prof_lbl)
        self._profile_combo = QComboBox()
        self._profile_combo.setFixedSize(160, 30)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        src_row.addWidget(self._profile_combo)
        new_prof_btn = QPushButton("+ New")
        new_prof_btn.setFixedSize(56, 28)
        new_prof_btn.clicked.connect(self._new_profile)
        src_row.addWidget(new_prof_btn)
        del_prof_btn = QPushButton("✕")
        del_prof_btn.setFixedSize(28, 28)
        del_prof_btn.clicked.connect(self._delete_profile)
        src_row.addWidget(del_prof_btn)
        root.addLayout(src_row)

        # Search + filters row
        search_row = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search mods…")
        self._search_box.setFixedHeight(38)
        self._search_box.textChanged.connect(lambda _: self._search_timer.start(400))
        search_row.addWidget(self._search_box, 2)

        self._version_filter = QComboBox()
        self._version_filter.setFixedSize(140, 38)
        self._version_filter.currentIndexChanged.connect(lambda _: self._search_timer.start(400))
        search_row.addWidget(self._version_filter)

        self._loader_filter = QComboBox()
        self._loader_filter.setFixedWidth(120)
        self._loader_filter.setFixedHeight(38)
        self._loader_filter.addItem("All loaders", "")
        for loader in ("fabric", "forge", "quilt", "neoforge"):
            self._loader_filter.addItem(loader.capitalize(), loader)
        self._loader_filter.currentIndexChanged.connect(lambda _: self._search_timer.start(400))
        search_row.addWidget(self._loader_filter)

        self._sort_combo = QComboBox()
        self._sort_combo.setFixedWidth(120)
        self._sort_combo.setFixedHeight(38)
        self._sort_combo.addItem("Downloads", "downloads")
        self._sort_combo.addItem("Relevance", "relevance")
        self._sort_combo.addItem("Updated",   "updated")
        self._sort_combo.addItem("Follows",   "follows")
        self._sort_combo.currentIndexChanged.connect(lambda _: self._search_timer.start(400))
        search_row.addWidget(self._sort_combo)
        root.addLayout(search_row)

        self._status = QLabel("Select an instance to install mods.")
        self._status.setStyleSheet("font-size: " + _SM + "; color: " + C["text_secondary"] + ";")
        root.addWidget(self._status)

        # Updates section (hidden until check runs)
        self._updates_section = QWidget()
        self._updates_section.setVisible(False)
        updates_layout = QVBoxLayout(self._updates_section)
        updates_layout.setContentsMargins(0, 0, 0, 0)
        updates_layout.setSpacing(6)
        updates_hdr = QLabel("Available updates")
        updates_hdr.setStyleSheet(
            "font-size: " + _SM + "; font-weight: 700; color: " + C["text_primary"] + ";"
        )
        updates_layout.addWidget(updates_hdr)
        self._updates_list = QVBoxLayout()
        self._updates_list.setSpacing(6)
        updates_layout.addLayout(self._updates_list)
        root.addWidget(self._updates_section)

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

    # ------------------------------------------------------------------
    # Instance / profile management
    # ------------------------------------------------------------------

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
        self._refresh_profiles()
        self._execute_search()

    def _refresh_profiles(self) -> None:
        instance = selected_instance()
        if not instance:
            self._profile_combo.setEnabled(False)
            return
        instance_dir = Path(instance.get("directory", ""))
        data = _load_profiles(instance_dir)
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        for name in data.get("profiles", {}).keys():
            self._profile_combo.addItem(name)
        active = data.get("active", "Default")
        idx = self._profile_combo.findText(active)
        if idx >= 0:
            self._profile_combo.setCurrentIndex(idx)
        self._profile_combo.setEnabled(True)
        self._profile_combo.blockSignals(False)

    def _on_profile_changed(self, _index: int) -> None:
        instance = selected_instance()
        if not instance:
            return
        new_profile = self._profile_combo.currentText()
        if not new_profile:
            return
        try:
            _switch_profile(Path(instance.get("directory", "")), new_profile)
            self._status.setText(f"Switched to profile: {new_profile}")
        except Exception as exc:
            self._status.setText(f"Profile switch failed: {exc}")

    def _new_profile(self) -> None:
        instance = selected_instance()
        if not instance:
            return
        name, ok = QInputDialog.getText(self, "New Mod Profile", "Profile name:")
        if not ok or not name.strip():
            return
        instance_dir = Path(instance.get("directory", ""))
        data = _load_profiles(instance_dir)
        mods_dir = instance_dir / "mods"
        current_mods = [f.name for f in mods_dir.iterdir() if f.suffix.lower() == ".jar"] if mods_dir.exists() else []
        data["profiles"][name.strip()] = list(current_mods)
        _save_profiles(instance_dir, data)
        self._refresh_profiles()
        self._status.setText(f"Created profile: {name.strip()}")

    def _delete_profile(self) -> None:
        instance = selected_instance()
        if not instance:
            return
        name = self._profile_combo.currentText()
        if name == "Default":
            QMessageBox.warning(self, "Cannot Delete", "The Default profile cannot be deleted.")
            return
        instance_dir = Path(instance.get("directory", ""))
        data = _load_profiles(instance_dir)
        data["profiles"].pop(name, None)
        if data.get("active") == name:
            data["active"] = "Default"
        _save_profiles(instance_dir, data)
        self._refresh_profiles()
        self._status.setText(f"Deleted profile: {name}")

    def _populate_versions(self) -> None:
        current = selected_instance()
        version = (current or {}).get("mc_version", config.get("selected_version", ""))
        self._version_filter.blockSignals(True)
        self._version_filter.clear()
        self._version_filter.addItem("Instance version", version)
        self._version_filter.addItem("Any version", "")
        self._version_filter.setCurrentIndex(0 if version else 1)
        self._version_filter.blockSignals(False)

    def _on_instance_changed(self, index: int) -> None:
        set_selected_instance(self._instance_combo.itemData(index) or "")
        self._populate_versions()
        self._refresh_profiles()
        self._execute_search()

    def _on_source_changed(self) -> None:
        source = self._source_combo.currentData()
        self._loader_filter.setEnabled(source == "modrinth")
        self._sort_combo.setEnabled(source == "modrinth")
        self._search_timer.start(200)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _execute_search(self) -> None:
        if self._active_search_thread is not None and self._active_search_thread.isRunning():
            self._search_generation += 1
            self._search_pending = True
            self._status.setText("Search queued...")
            return
        query        = self._search_box.text().strip() if hasattr(self, "_search_box") else ""
        game_version = self._version_filter.currentData() if hasattr(self, "_version_filter") else ""
        source       = self._source_combo.currentData() if hasattr(self, "_source_combo") else "modrinth"
        loader       = self._loader_filter.currentData() if hasattr(self, "_loader_filter") else ""
        sort_idx     = self._sort_combo.currentData() if hasattr(self, "_sort_combo") else "downloads"

        self._status.setText("Searching mods…")
        self._search_generation += 1
        generation = self._search_generation
        self._cards.clear()

        while self._results.count() > 1:
            item = self._results.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        thread = QThread(self)
        if source == "curseforge":
            worker = CFSearchWorker(query, game_version)
        else:
            worker = ModSearchWorker(query, game_version, loader, sort_idx)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.results_ready.connect(
            lambda hits, total, gen=generation: self._on_results(gen, hits, total)
        )
        worker.error.connect(
            lambda e, gen=generation: self._on_search_error(gen, e)
        )
        worker.results_ready.connect(thread.quit)
        worker.error.connect(thread.quit)
        self._threads.append(thread)
        self._workers.append(worker)
        self._active_search_thread = thread
        thread.finished.connect(lambda t=thread, w=worker: self._cleanup_search_thread(t, w))
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _cleanup_search_thread(self, thread: QThread, worker: QObject) -> None:
        if thread in self._threads:
            self._threads.remove(thread)
        if worker in self._workers:
            self._workers.remove(worker)
        if self._active_search_thread is thread:
            self._active_search_thread = None
        if self._search_pending:
            self._search_pending = False
            QTimer.singleShot(0, self._execute_search)

    def _on_results(self, generation: int, hits: list[dict], total: int) -> None:
        if generation != self._search_generation:
            return
        self._status.setText(f"{total:,} mods found.")
        for project in hits:
            card = ModCard(project, self)
            card.install_requested.connect(self._install_mod)
            card.view_details_requested.connect(self._open_detail)
            self._cards[project.get("id", "")] = card
            self._results.insertWidget(self._results.count() - 1, card)
            icon_url = project.get("icon_url", "")
            if icon_url:
                self._load_icon_async(project.get("id", ""), icon_url)

    def _on_search_error(self, generation: int, msg: str) -> None:
        if generation != self._search_generation:
            return
        self._status.setText(f"Error: {msg}")

    def _load_icon_async(self, project_id: str, icon_url: str) -> None:
        thread = QThread(self)
        worker = _IconLoader(project_id, icon_url)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_icon_loaded)
        worker.done.connect(thread.quit)
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_icon_loaded(self, project_id: str, path: str) -> None:
        card = self._cards.get(project_id)
        if card:
            pix = QPixmap(path)
            card.set_icon(pix)

    # ------------------------------------------------------------------
    # Detail dialog
    # ------------------------------------------------------------------

    def _open_detail(self, project: dict) -> None:
        from ..dialogs.mod_detail_dialog import ModDetailDialog
        instance = selected_instance()
        dlg = ModDetailDialog(project, instance, self)
        dlg.install_version_requested.connect(
            lambda proj, ver: self._install_mod_version(proj, ver)
        )
        dlg.exec()

    def _install_mod_version(self, project: dict, version: dict) -> None:
        self._install_mod(project, version=version)

    # ------------------------------------------------------------------
    # Update check
    # ------------------------------------------------------------------

    def _run_update_check(self) -> None:
        instance = selected_instance()
        if not instance:
            self._status.setText("Select an instance first.")
            return
        self._check_updates_btn.setEnabled(False)
        self._check_updates_btn.setText("Checking…")
        while self._updates_list.count():
            item = self._updates_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._updates_section.setVisible(False)

        thread = QThread(self)
        worker = ModUpdateWorker(instance)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.status.connect(self._status.setText)
        worker.updates_found.connect(self._on_updates_found)
        worker.updates_found.connect(thread.quit)
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(lambda: self._check_updates_btn.setEnabled(True))
        thread.finished.connect(lambda: self._check_updates_btn.setText("Check for Updates"))
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_updates_found(self, updates: list[dict]) -> None:
        if not updates:
            return
        self._updates_section.setVisible(True)
        for info in updates:
            card = ModUpdateCard(info, self._updates_section)
            card.update_requested.connect(self._execute_mod_update)
            self._updates_list.addWidget(card)

    def _execute_mod_update(self, info: dict) -> None:
        for i in range(self._updates_list.count()):
            item = self._updates_list.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), ModUpdateCard):
                card = item.widget()
                if card._info.get("project_id") == info.get("project_id"):
                    card.set_updated()
                    break
        thread = QThread(self)
        worker = ModApplyUpdateWorker(info)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda ok, msg, _info: self._status.setText(msg))
        worker.finished.connect(thread.quit)
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def _install_mod(self, project: dict, version: dict | None = None) -> None:
        instance    = selected_instance()
        fallback_dir = (
            selected_instance_dir() if instance
            else Path(config.get("minecraft_dir", str(APP_DIR / "minecraft")))
        )
        self._status.setText(f"Installing {project.get('title', 'mod')}…")
        thread = QThread(self)
        worker = ModInstallWorker(project, version, instance, fallback_dir)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(
            lambda ok, msg: self._status.setText(msg if ok else f"Install failed: {msg}")
        )
        worker.finished.connect(thread.quit)
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()
