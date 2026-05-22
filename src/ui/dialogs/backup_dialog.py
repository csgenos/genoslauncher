"""World backup manager — zip/restore saves per instance."""

from __future__ import annotations

import shutil
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
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
from ...core.config import APP_DIR


def _backup_dir() -> Path:
    d = APP_DIR / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


_MAX_BACKUP_FILES = 20_000
_MAX_BACKUP_BYTES = 4 * 1024 * 1024 * 1024


def _safe_child(base_dir: Path, relative: str) -> Path:
    target = (base_dir / relative).resolve()
    target.relative_to(base_dir.resolve())
    return target


def _validate_backup_zip(zf: zipfile.ZipFile) -> None:
    infos = zf.infolist()
    if len(infos) > _MAX_BACKUP_FILES:
        raise ValueError("Backup contains too many files")
    total = 0
    for info in infos:
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
    def __init__(self, backup_path: Path, on_restore, on_delete, parent=None) -> None:
        super().__init__(parent)
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


class WorldBackupDialog(QDialog):
    def __init__(self, instance: dict, parent=None) -> None:
        super().__init__(parent)
        self._instance = instance
        self._saves_dir = Path(instance.get("directory", "")) / "saves"
        self._instance_id = instance.get("id", "unknown")
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

        layout.addWidget(QLabel("Existing Backups"))

        self._backups_scroll = QScrollArea()
        self._backups_scroll.setWidgetResizable(True)
        self._backups_scroll.setStyleSheet("QScrollArea { border: 1px solid " + C["border"] + "; border-radius: 8px; }")
        self._backups_widget = QWidget()
        self._backups_layout = QVBoxLayout(self._backups_widget)
        self._backups_layout.setContentsMargins(4, 4, 4, 4)
        self._backups_layout.setSpacing(6)
        self._backups_scroll.setWidget(self._backups_widget)
        layout.addWidget(self._backups_scroll, 1)

        self._status = QLabel("")
        self._status.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        layout.addWidget(self._status)

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)

    def _refresh(self) -> None:
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
        else:
            for bp in backups[:20]:
                row = BackupRow(
                    bp,
                    on_restore=lambda _=False, b=bp: self._restore_backup(b),
                    on_delete=lambda _=False, b=bp: self._delete_backup(b),
                )
                self._backups_layout.addWidget(row)
        self._backups_layout.addStretch()

    def _backup_world(self, world_dir: Path) -> None:
        self._status.setText(f"Backing up {world_dir.name}…")
        dest_dir = _backup_dir() / self._instance_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = dest_dir / f"{world_dir.name}_{timestamp}.zip"

        def _do():
            try:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for file in world_dir.rglob("*"):
                        if file.is_file():
                            zf.write(file, file.relative_to(world_dir))
                QTimer.singleShot(0, lambda: (
                    self._status.setText(f"Backup saved: {zip_path.name}"),
                    self._refresh(),
                ))
            except Exception as exc:
                QTimer.singleShot(0, lambda: self._status.setText(f"Backup failed: {exc}"))

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
                QTimer.singleShot(0, lambda: self._status.setText(f"Restored {world_name} successfully."))
            except Exception as exc:
                if rollback.exists() and not dest.exists():
                    try:
                        rollback.replace(dest)
                    except OSError:
                        pass
                shutil.rmtree(staging, ignore_errors=True)
                QTimer.singleShot(0, lambda: self._status.setText(f"Restore failed: {exc}"))

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
