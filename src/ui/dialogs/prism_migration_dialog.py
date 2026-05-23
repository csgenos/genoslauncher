from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import OutlineButton, PrimaryButton
from ...core.instances import import_prism_instances


def _detect_prism_roots() -> list[Path]:
    candidates: list[Path] = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")
        if appdata:
            candidates.append(Path(appdata) / "PrismLauncher")
        if localappdata:
            candidates.append(Path(localappdata) / "Programs" / "PrismLauncher")
    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / "PrismLauncher")
    else:
        candidates.append(Path.home() / ".local" / "share" / "PrismLauncher")
        candidates.append(Path.home() / "snap" / "prismlauncher" / "current" / ".local" / "share" / "PrismLauncher")
    return candidates


def _is_valid_prism_root(path: Path) -> bool:
    return path.is_dir() and (path / "instances").is_dir()


def _parse_mc_version_from_mmc_pack(mmc_pack_path: Path) -> str:
    try:
        data = json.loads(mmc_pack_path.read_text(encoding="utf-8", errors="replace"))
        for component in data.get("components", []):
            if component.get("uid") == "net.minecraft":
                ver = component.get("cachedVersion") or component.get("version", "")
                if ver:
                    return str(ver)
    except Exception:
        pass
    return ""


def _parse_instance_name_from_cfg(cfg_path: Path) -> str:
    try:
        for line in cfg_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("name="):
                return line[5:].strip()
    except Exception:
        pass
    return cfg_path.parent.name


def _scan_prism_instances(root: Path) -> list[dict]:
    instances_dir = root / "instances"
    if not instances_dir.is_dir():
        return []
    results: list[dict] = []
    for child in sorted(instances_dir.iterdir()):
        if not child.is_dir():
            continue
        has_mmc = (child / "mmc-pack.json").exists()
        has_cfg = (child / "instance.cfg").exists()
        if not (has_mmc or has_cfg):
            continue
        mc_version = ""
        if has_mmc:
            mc_version = _parse_mc_version_from_mmc_pack(child / "mmc-pack.json")
        name = _parse_instance_name_from_cfg(child / "instance.cfg") if has_cfg else child.name
        results.append({
            "folder": child.name,
            "name": name,
            "mc_version": mc_version or "?",
        })
    return results


class _ImportWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, prism_root: Path, selected_names: list[str]) -> None:
        super().__init__()
        self._root = prism_root
        self._names = selected_names

    def run(self) -> None:
        try:
            instances_dir = self._root / "instances"
            imported = import_prism_instances(instances_dir, self._names if self._names else None)
            self.finished.emit(len(imported))
        except Exception as exc:
            self.error.emit(str(exc))


class PrismMigrationDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import from Prism Launcher")
        self.setMinimumSize(600, 480)
        self.setStyleSheet(f"background: {C['bg_primary']}; color: {C['text_primary']};")

        self._prism_root: Path | None = None
        self._instance_rows: list[dict] = []
        self._checkboxes: list[tuple[QCheckBox, str]] = []
        self._thread: QThread | None = None
        self._worker: _ImportWorker | None = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._stack = QStackedWidget()
        root_layout.addWidget(self._stack)

        self._stack.addWidget(self._build_page0())
        self._stack.addWidget(self._build_page1())
        self._stack.addWidget(self._build_page2())

        self._stack.setCurrentIndex(0)
        self._auto_detect()

    def _build_page0(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("Step 1 — Detect Prism Launcher")
        title.setStyleSheet(f"font-size: {FONT['xl']}; font-weight: 700; color: {C['text_primary']};")
        layout.addWidget(title)

        desc = QLabel(
            "GenosLauncher will look for your Prism Launcher data directory automatically. "
            "If not found, use Browse to select it manually."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        layout.addWidget(desc)

        self._detect_lbl = QLabel("Searching…")
        self._detect_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_tertiary']};")
        self._detect_lbl.setWordWrap(True)
        layout.addWidget(self._detect_lbl)

        browse_row = QHBoxLayout()
        browse_btn = OutlineButton("Browse…")
        browse_btn.setFixedHeight(34)
        browse_btn.clicked.connect(self._browse_prism_root)
        browse_row.addWidget(browse_btn)
        browse_row.addStretch()
        layout.addLayout(browse_row)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._page0_next = PrimaryButton("Next →")
        self._page0_next.setFixedHeight(36)
        self._page0_next.setEnabled(False)
        self._page0_next.clicked.connect(self._go_to_page1)
        btn_row.addWidget(self._page0_next)
        layout.addLayout(btn_row)

        return page

    def _build_page1(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(12)

        title = QLabel("Step 2 — Select Instances")
        title.setStyleSheet(f"font-size: {FONT['xl']}; font-weight: 700; color: {C['text_primary']};")
        layout.addWidget(title)

        ctrl_row = QHBoxLayout()
        sel_all_btn = OutlineButton("Select All")
        sel_all_btn.setFixedHeight(30)
        sel_all_btn.clicked.connect(self._select_all)
        ctrl_row.addWidget(sel_all_btn)
        desel_all_btn = OutlineButton("Deselect All")
        desel_all_btn.setFixedHeight(30)
        desel_all_btn.clicked.connect(self._deselect_all)
        ctrl_row.addWidget(desel_all_btn)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: 1px solid " + C["border"] + "; border-radius: 8px; }")
        self._instances_container = QWidget()
        self._instances_container.setStyleSheet("background: transparent;")
        self._instances_vbox = QVBoxLayout(self._instances_container)
        self._instances_vbox.setContentsMargins(8, 8, 8, 8)
        self._instances_vbox.setSpacing(4)
        self._instances_vbox.addStretch()
        scroll.setWidget(self._instances_container)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        back_btn = OutlineButton("← Back")
        back_btn.setFixedHeight(36)
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        btn_row.addWidget(back_btn)
        btn_row.addStretch()
        self._import_btn = PrimaryButton("Import →")
        self._import_btn.setFixedHeight(36)
        self._import_btn.clicked.connect(self._start_import)
        btn_row.addWidget(self._import_btn)
        layout.addLayout(btn_row)

        return page

    def _build_page2(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("Step 3 — Importing…")
        title.setStyleSheet(f"font-size: {FONT['xl']}; font-weight: 700; color: {C['text_primary']};")
        layout.addWidget(title)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setFixedHeight(12)
        layout.addWidget(self._progress_bar)

        self._progress_lbl = QLabel("Starting import…")
        self._progress_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        self._progress_lbl.setWordWrap(True)
        layout.addWidget(self._progress_lbl)

        layout.addStretch()

        self._close_btn = QPushButton("Close")
        self._close_btn.setFixedHeight(36)
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.accept)
        layout.addWidget(self._close_btn)

        return page

    def _auto_detect(self) -> None:
        candidates = _detect_prism_roots()
        for path in candidates:
            if _is_valid_prism_root(path):
                self._set_prism_root(path, auto=True)
                return
        self._detect_lbl.setText("Not found automatically — use Browse to select your Prism Launcher folder.")

    def _set_prism_root(self, path: Path, auto: bool = False) -> None:
        self._prism_root = path
        prefix = "Auto-detected" if auto else "Selected"
        self._detect_lbl.setText(f"{prefix}: {path}")
        self._detect_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['success']};")
        self._page0_next.setEnabled(True)

    def _browse_prism_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Prism Launcher Data Folder")
        if not folder:
            return
        path = Path(folder)
        if _is_valid_prism_root(path):
            self._set_prism_root(path)
        elif (path / "instances").is_dir() is False and path.is_dir():
            self._detect_lbl.setText(f"Selected: {path}\n(No instances/ subdirectory found — import may find nothing)")
            self._detect_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['warning']};")
            self._prism_root = path
            self._page0_next.setEnabled(True)
        else:
            self._detect_lbl.setText("Selected path is not a valid Prism Launcher folder.")
            self._detect_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['danger']};")

    def _go_to_page1(self) -> None:
        if self._prism_root is None:
            return
        self._instance_rows = _scan_prism_instances(self._prism_root)
        self._populate_instance_list()
        self._stack.setCurrentIndex(1)

    def _populate_instance_list(self) -> None:
        while self._instances_vbox.count() > 1:
            item = self._instances_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._checkboxes.clear()

        if not self._instance_rows:
            lbl = QLabel("No importable instances found.")
            lbl.setStyleSheet(f"color: {C['text_tertiary']}; font-size: {FONT['sm']};")
            self._instances_vbox.insertWidget(0, lbl)
            self._import_btn.setEnabled(False)
            return

        self._import_btn.setEnabled(True)
        for idx, row in enumerate(self._instance_rows):
            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent;")
            h = QHBoxLayout(row_widget)
            h.setContentsMargins(4, 2, 4, 2)
            h.setSpacing(10)
            cb = QCheckBox()
            cb.setChecked(True)
            h.addWidget(cb)
            name_lbl = QLabel(row["name"])
            name_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_primary']}; font-weight: 600;")
            h.addWidget(name_lbl)
            ver_lbl = QLabel(f"MC {row['mc_version']}")
            ver_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
            h.addWidget(ver_lbl)
            h.addStretch()
            skip_btn = QPushButton("Skip")
            skip_btn.setFixedHeight(24)
            skip_btn.clicked.connect(lambda _=False, c=cb: c.setChecked(False))
            h.addWidget(skip_btn)
            self._instances_vbox.insertWidget(idx, row_widget)
            self._checkboxes.append((cb, row["folder"]))

    def _select_all(self) -> None:
        for cb, _ in self._checkboxes:
            cb.setChecked(True)

    def _deselect_all(self) -> None:
        for cb, _ in self._checkboxes:
            cb.setChecked(False)

    def _start_import(self) -> None:
        if self._prism_root is None:
            return
        selected = [folder for cb, folder in self._checkboxes if cb.isChecked()]
        self._stack.setCurrentIndex(2)
        self._progress_lbl.setText(f"Importing {len(selected)} instance(s)…")

        thread = QThread(self)
        worker = _ImportWorker(self._prism_root, selected)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_import_done)
        worker.error.connect(self._on_import_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_import_done(self, count: int) -> None:
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(1)
        self._progress_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['success']};")
        self._progress_lbl.setText(f"Imported {count} instance(s) successfully.")
        self._close_btn.setEnabled(True)
        self._thread = None
        self._worker = None

    def _on_import_error(self, msg: str) -> None:
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(0)
        self._progress_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['danger']};")
        self._progress_lbl.setText(f"Error: {msg}")
        self._close_btn.setEnabled(True)
        self._thread = None
        self._worker = None
