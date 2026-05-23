"""World backup manager — zip/restore saves per instance."""

from __future__ import annotations

import shutil
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..qt_dispatch import run_on_ui_thread
from ...core.config import APP_DIR


def _backup_dir() -> Path:
    d = APP_DIR / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


_MAX_BACKUP_FILES = 20_000
_MAX_BACKUP_BYTES = 4 * 1024 * 1024 * 1024


def _zipinfo_is_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _safe_child(base_dir: Path, relative: str) -> Path:
    target = (base_dir / relative).resolve()
    target.relative_to(base_dir.resolve())
    return target


def _ensure_within(base_dir: Path, path: Path) -> None:
    path.resolve().relative_to(base_dir.resolve())


def _validate_backup_zip(zf: zipfile.ZipFile) -> None:
    infos = zf.infolist()
    if len(infos) > _MAX_BACKUP_FILES:
        raise ValueError("Backup contains too many files")
    total = 0
    for info in infos:
        if _zipinfo_is_symlink(info):
            raise ValueError("Backup contains symbolic links")
        total += info.file_size
        if total > _MAX_BACKUP_BYTES:
            raise ValueError("Backup is too large to restore safely")
        _safe_child(Path("."), info.filename)


def _extract_backup_safe(backup_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(backup_path, "r") as zf:
        _validate_backup_zip(zf)
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = _safe_child(dest, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


class WorldRow(QFrame):
    def __init__(self, world_name: str, on_backup, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("WorldRow")
        self.setFixedHeight(52)
        self.setStyleSheet(f"""
            #WorldRow {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 8px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        lbl = QLabel(world_name)
        lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 600; color: {C['text_primary']};")
        layout.addWidget(lbl, 1)
        btn = QPushButton("Backup")
        btn.setFixedSize(80, 30)
        btn.clicked.connect(on_backup)
        layout.addWidget(btn)


class BackupRow(QFrame):
    def __init__(self, backup_path: Path, on_restore, on_delete, on_selection_changed=None, parent=None) -> None:
        super().__init__(parent)
        self._backup_path = backup_path
        self._on_selection_changed = on_selection_changed
        self.setObjectName("BackupRow")
        self.setFixedHeight(52)
        self.setStyleSheet(f"""
            #BackupRow {{
                background: {C["bg_secondary"]};
                border: 1px solid {C["border"]};
                border-radius: 8px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)

        self._checkbox = QCheckBox()
        self._checkbox.stateChanged.connect(self._on_check_changed)
        layout.addWidget(self._checkbox)

        size_kb = backup_path.stat().st_size // 1024
        lbl = QLabel(f"{backup_path.stem}  ({size_kb:,} KB)")
        lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        layout.addWidget(lbl, 1)
        restore_btn = QPushButton("Restore")
        restore_btn.setFixedSize(76, 28)
        restore_btn.clicked.connect(on_restore)
        layout.addWidget(restore_btn)
        del_btn = QPushButton("Delete")
        del_btn.setFixedSize(64, 28)
        del_btn.clicked.connect(on_delete)
        layout.addWidget(del_btn)

    def _on_check_changed(self, state: int) -> None:
        if self._on_selection_changed:
            self._on_selection_changed(self._backup_path, state == Qt.Checked)

    def is_checked(self) -> bool:
        return self._checkbox.isChecked()

    def set_checked(self, checked: bool) -> None:
        self._checkbox.blockSignals(True)
        self._checkbox.setChecked(checked)
        self._checkbox.blockSignals(False)
        if self._on_selection_changed:
            self._on_selection_changed(self._backup_path, checked)


class WorldBackupDialog(QDialog):
    def __init__(self, instance: dict, parent=None) -> None:
        super().__init__(parent)
        self._instance = instance
        self._saves_dir = Path(instance.get("directory", "")) / "saves"
        self._instance_id = instance.get("id", "unknown")
        self._selected_backups: set[Path] = set()
        self._backup_rows: list[BackupRow] = []
        self.setWindowTitle(f"World Backups — {instance.get('name', 'Instance')}")
        self.resize(680, 560)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        title = QLabel("World Backup Manager")
        title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        layout.addWidget(title)

        layout.addWidget(QLabel("Worlds"))

        self._worlds_scroll = QScrollArea()
        self._worlds_scroll.setWidgetResizable(True)
        self._worlds_scroll.setMaximumHeight(200)
        self._worlds_scroll.setStyleSheet("QScrollArea { border: 1px solid " + C["border"] + "; border-radius: 8px; }")
        self._worlds_widget = QWidget()
        self._worlds_layout = QVBoxLayout(self._worlds_widget)
        self._worlds_layout.setContentsMargins(4, 4, 4, 4)
        self._worlds_layout.setSpacing(6)
        self._worlds_scroll.setWidget(self._worlds_widget)
        layout.addWidget(self._worlds_scroll)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C['border']}; border: none;")
        layout.addWidget(sep)

        backup_hdr = QHBoxLayout()
        backup_hdr_lbl = QLabel("Existing Backups")
        backup_hdr_lbl.setStyleSheet(f"font-size: {FONT['sm']}; font-weight: 600; color: {C['text_primary']};")
        backup_hdr.addWidget(backup_hdr_lbl)
        backup_hdr.addStretch()
        self._select_all_cb = QCheckBox("Select All")
        self._select_all_cb.stateChanged.connect(self._on_select_all)
        backup_hdr.addWidget(self._select_all_cb)
        layout.addLayout(backup_hdr)

        self._backups_scroll = QScrollArea()
        self._backups_scroll.setWidgetResizable(True)
        self._backups_scroll.setStyleSheet("QScrollArea { border: 1px solid " + C["border"] + "; border-radius: 8px; }")
        self._backups_widget = QWidget()
        self._backups_layout = QVBoxLayout(self._backups_widget)
        self._backups_layout.setContentsMargins(4, 4, 4, 4)
        self._backups_layout.setSpacing(6)
        self._backups_scroll.setWidget(self._backups_widget)
        layout.addWidget(self._backups_scroll, 1)

        self._storage_lbl = QLabel("")
        self._storage_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        layout.addWidget(self._storage_lbl)

        self._status = QLabel("")
        self._status.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        layout.addWidget(self._status)

        btn_row = QHBoxLayout()
        self._delete_sel_btn = QPushButton("Delete Selected")
        self._delete_sel_btn.setFixedHeight(30)
        self._delete_sel_btn.setEnabled(False)
        self._delete_sel_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self._delete_sel_btn)
        self._export_sel_btn = QPushButton("Export Selected")
        self._export_sel_btn.setFixedHeight(30)
        self._export_sel_btn.setEnabled(False)
        self._export_sel_btn.clicked.connect(self._export_selected)
        btn_row.addWidget(self._export_sel_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _refresh(self) -> None:
        self._selected_backups.clear()
        self._backup_rows.clear()

        # Worlds
        while self._worlds_layout.count():
            item = self._worlds_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._saves_dir.exists():
            worlds = [d for d in self._saves_dir.iterdir() if d.is_dir()]
        else:
            worlds = []

        if not worlds:
            lbl = QLabel("No worlds found for this instance.")
            lbl.setStyleSheet(f"color: {C['text_tertiary']}; font-size: {FONT['sm']};")
            lbl.setContentsMargins(8, 8, 8, 8)
            self._worlds_layout.addWidget(lbl)
        else:
            for world in sorted(worlds, key=lambda d: d.stat().st_mtime, reverse=True):
                row = WorldRow(world.name, lambda _=False, w=world: self._backup_world(w))
                self._worlds_layout.addWidget(row)
        self._worlds_layout.addStretch()

        # Backups
        while self._backups_layout.count():
            item = self._backups_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        backup_dir = _backup_dir() / self._instance_id
        if backup_dir.exists():
            backups = sorted(
                [f for f in backup_dir.iterdir() if f.suffix == ".zip"],
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
        else:
            backups = []

        if not backups:
            lbl = QLabel("No backups yet.")
            lbl.setStyleSheet(f"color: {C['text_tertiary']}; font-size: {FONT['sm']};")
            lbl.setContentsMargins(8, 8, 8, 8)
            self._backups_layout.addWidget(lbl)
            self._storage_lbl.setText("")
        else:
            total_bytes = sum(bp.stat().st_size for bp in backups if bp.exists())
            total_mb = total_bytes / (1024 * 1024)
            unit = "GB" if total_mb >= 1024 else "MB"
            total_display = f"{total_mb / 1024:.2f} {unit}" if total_mb >= 1024 else f"{total_mb:.1f} MB"
            self._storage_lbl.setText(
                f"Total: {total_display} across {len(backups)} backup(s)  ·  Use checkboxes to select"
            )
            for bp in backups[:20]:
                row = BackupRow(
                    bp,
                    on_restore=lambda _=False, b=bp: self._restore_backup(b),
                    on_delete=lambda _=False, b=bp: self._delete_backup(b),
                    on_selection_changed=self._on_backup_selection_changed,
                )
                self._backup_rows.append(row)
                self._backups_layout.addWidget(row)
        self._backups_layout.addStretch()

        self._select_all_cb.blockSignals(True)
        self._select_all_cb.setChecked(False)
        self._select_all_cb.blockSignals(False)
        self._update_sel_buttons()

    def _on_backup_selection_changed(self, path: Path, selected: bool) -> None:
        if selected:
            self._selected_backups.add(path)
        else:
            self._selected_backups.discard(path)
        self._update_sel_buttons()

    def _update_sel_buttons(self) -> None:
        has_sel = bool(self._selected_backups)
        self._delete_sel_btn.setEnabled(has_sel)
        self._export_sel_btn.setEnabled(has_sel)

    def _on_select_all(self, state: int) -> None:
        checked = state == Qt.Checked
        for row in self._backup_rows:
            row.set_checked(checked)

    def _delete_selected(self) -> None:
        count = len(self._selected_backups)
        reply = QMessageBox.question(
            self, "Delete Backups",
            f"Permanently delete {count} selected backup(s)?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        errors = []
        for path in list(self._selected_backups):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(str(exc))
        if errors:
            self._status.setText(f"Some deletions failed: {errors[0]}")
        else:
            self._status.setText(f"Deleted {count} backup(s).")
        self._refresh()

    def _export_selected(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Export Backups to Folder")
        if not folder:
            return
        dest_dir = Path(folder)
        copied = 0
        errors = []
        for path in self._selected_backups:
            if path.exists():
                try:
                    shutil.copy2(path, dest_dir / path.name)
                    copied += 1
                except OSError as exc:
                    errors.append(str(exc))
        if errors:
            self._status.setText(f"Exported {copied} backup(s); {len(errors)} error(s): {errors[0]}")
        else:
            self._status.setText(f"Exported {copied} backup(s) to {folder}.")

    def _backup_world(self, world_dir: Path) -> None:
        self._status.setText(f"Backing up {world_dir.name}…")
        dest_dir = _backup_dir() / self._instance_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = dest_dir / f"{world_dir.name}_{timestamp}.zip"

        def _do():
            try:
                total_files = 0
                total_bytes = 0
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for file in world_dir.rglob("*"):
                        if file.is_symlink():
                            _ensure_within(world_dir, file.resolve())
                            continue
                        if file.is_file():
                            _ensure_within(world_dir, file)
                            total_files += 1
                            if total_files > _MAX_BACKUP_FILES:
                                raise ValueError("World contains too many files to back up safely")
                            total_bytes += file.stat().st_size
                            if total_bytes > _MAX_BACKUP_BYTES:
                                raise ValueError("World is too large to back up safely")
                            zf.write(file, file.relative_to(world_dir))
                run_on_ui_thread(lambda: (
                    self._status.setText(f"Backup saved: {zip_path.name}"),
                    self._refresh(),
                ))
            except Exception as exc:
                msg = str(exc)
                zip_path.unlink(missing_ok=True)
                run_on_ui_thread(lambda msg=msg: self._status.setText(f"Backup failed: {msg}"))

        threading.Thread(target=_do, daemon=True).start()

    def _restore_backup(self, backup_path: Path) -> None:
        reply = QMessageBox.question(
            self, "Restore Backup",
            f"Restore {backup_path.stem}?\nThis will overwrite the existing world folder.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        world_name = backup_path.stem.rsplit("_", 2)[0]
        try:
            self._saves_dir.mkdir(parents=True, exist_ok=True)
            dest = _safe_child(self._saves_dir, world_name)
        except (OSError, ValueError):
            self._status.setText("Restore failed: unsafe backup name.")
            return

        def _do():
            staging = Path(tempfile.mkdtemp(prefix=f".restore-{world_name}-", dir=str(self._saves_dir)))
            rollback = self._saves_dir / f".rollback-{world_name}-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                _extract_backup_safe(backup_path, staging)
                if dest.exists():
                    dest.replace(rollback)
                staging.replace(dest)
                if rollback.exists():
                    shutil.rmtree(rollback)
                run_on_ui_thread(lambda: self._status.setText(f"Restored {world_name} successfully."))
            except Exception as exc:
                if rollback.exists() and not dest.exists():
                    try:
                        rollback.replace(dest)
                    except OSError:
                        pass
                shutil.rmtree(staging, ignore_errors=True)
                msg = str(exc)
                run_on_ui_thread(lambda msg=msg: self._status.setText(f"Restore failed: {msg}"))

        threading.Thread(target=_do, daemon=True).start()

    def _delete_backup(self, backup_path: Path) -> None:
        reply = QMessageBox.question(
            self, "Delete Backup",
            f"Permanently delete {backup_path.name}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                backup_path.unlink()
                self._refresh()
            except OSError as exc:
                self._status.setText(f"Delete failed: {exc}")
