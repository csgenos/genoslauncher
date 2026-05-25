from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import OutlineButton, PrimaryButton
from ..components.themed_controls import GMenu
from ...core.config import config, APP_DIR
from ...core.instances import list_instances
from ...core.cloud_sync import (
    get_sync_config,
    save_sync_config,
    push_instance,
    pull_instance,
    list_remote_backups,
    sync_all,
)


class _PushWorker(QObject):
    done = Signal(str)
    error = Signal(str)

    def __init__(self, instance: dict, sync_dir: str) -> None:
        super().__init__()
        self._instance = instance
        self._sync_dir = sync_dir

    def run(self) -> None:
        try:
            path = push_instance(self._instance, self._sync_dir)
            self.done.emit(path)
        except Exception as exc:
            self.error.emit(str(exc))


class _PullWorker(QObject):
    done = Signal(str)
    error = Signal(str)

    def __init__(self, instance_id: str, zip_path: str, instances_dir: str) -> None:
        super().__init__()
        self._instance_id = instance_id
        self._zip_path = zip_path
        self._instances_dir = instances_dir

    def run(self) -> None:
        try:
            dest = pull_instance(self._instance_id, self._zip_path, self._instances_dir)
            self.done.emit(dest)
        except Exception as exc:
            self.error.emit(str(exc))


class _SyncAllWorker(QObject):
    progress = Signal(int, int, str)
    done = Signal(int)
    error = Signal(str)

    def __init__(self, sync_dir: str) -> None:
        super().__init__()
        self._sync_dir = sync_dir

    def run(self) -> None:
        try:
            count = sync_all(self._sync_dir, progress_cb=self.progress.emit)
            self.done.emit(count)
        except Exception as exc:
            self.error.emit(str(exc))


class CloudSyncDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cloud Sync / Backup")
        self.setMinimumSize(640, 520)
        self.setStyleSheet(f"background: {C['bg_primary']}; color: {C['text_primary']};")
        self._threads: list[QThread] = []
        self._workers: list[QObject] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {C['border']};
                border-radius: 8px;
                background: {C['bg_primary']};
            }}
            QTabBar::tab {{
                padding: 8px 18px;
                font-size: {FONT['sm']};
                color: {C['text_secondary']};
            }}
            QTabBar::tab:selected {{
                color: {C['text_primary']};
                font-weight: 700;
                border-bottom: 2px solid {C['accent_blue']};
            }}
        """)
        self._tabs.addTab(self._build_overview_tab(), "Overview")
        self._tabs.addTab(self._build_instances_tab(), "Instances")
        self._tabs.addTab(self._build_settings_tab(), "Settings")
        root.addWidget(self._tabs)

    def _sync_dir(self) -> str:
        return str(config.get("cloud_sync_dir", "") or "")

    def _build_overview_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        cfg = get_sync_config()
        enabled = cfg.get("enabled", False)
        last_sync = cfg.get("last_sync") or "Never"

        status_lbl = QLabel(f"Sync: {'Enabled' if enabled else 'Disabled'}   Last sync: {last_sync}")
        status_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        status_lbl.setWordWrap(True)
        layout.addWidget(status_lbl)
        self._overview_status = status_lbl

        self._sync_now_btn = PrimaryButton("Sync Now")
        self._sync_now_btn.setFixedHeight(36)
        self._sync_now_btn.clicked.connect(self._on_sync_now)
        layout.addWidget(self._sync_now_btn)

        self._sync_result_lbl = QLabel("")
        self._sync_result_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        self._sync_result_lbl.setWordWrap(True)
        layout.addWidget(self._sync_result_lbl)

        self._auto_sync_cb = QCheckBox("Auto-sync before each launch")
        self._auto_sync_cb.setChecked(bool(cfg.get("auto_sync_on_launch", False)))
        self._auto_sync_cb.toggled.connect(lambda v: self._patch_config("cloud_sync_auto", v))
        layout.addWidget(self._auto_sync_cb)

        layout.addStretch()
        return page

    def _build_instances_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._inst_layout = QVBoxLayout(container)
        self._inst_layout.setContentsMargins(16, 12, 16, 12)
        self._inst_layout.setSpacing(8)

        self._rebuild_instances_list()

        self._inst_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)
        return page

    def _rebuild_instances_list(self) -> None:
        while self._inst_layout.count():
            item = self._inst_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sync_dir = self._sync_dir()
        instances = list_instances()

        if not instances:
            lbl = QLabel("No instances found.")
            lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_tertiary']};")
            self._inst_layout.addWidget(lbl)
            return

        for instance in instances:
            row = QWidget()
            row.setStyleSheet(f"background: {C['bg_secondary']}; border: 1px solid {C['border']}; border-radius: 6px;")
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 8, 12, 8)
            h.setSpacing(10)

            name_lbl = QLabel(f"{instance.get('name', '?')}  ({instance.get('mc_version', '?')})")
            name_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_primary']}; font-weight: 600;")
            h.addWidget(name_lbl, 1)

            push_btn = OutlineButton("Push")
            push_btn.setFixedHeight(28)
            push_btn.setFixedWidth(60)
            if not sync_dir:
                push_btn.setEnabled(False)
                push_btn.setToolTip("Configure sync directory in Settings tab")
            push_btn.clicked.connect(lambda _=False, inst=instance: self._push_instance(inst))
            h.addWidget(push_btn)

            pull_btn = OutlineButton("Pull ▾")
            pull_btn.setFixedHeight(28)
            pull_btn.setFixedWidth(72)
            if not sync_dir:
                pull_btn.setEnabled(False)
                pull_btn.setToolTip("Configure sync directory in Settings tab")
            pull_btn.clicked.connect(lambda _=False, inst=instance, b=pull_btn: self._show_pull_menu(inst, b))
            h.addWidget(pull_btn)

            self._inst_layout.addWidget(row)

    def _push_instance(self, instance: dict) -> None:
        sync_dir = self._sync_dir()
        if not sync_dir:
            return
        thread = QThread(self)
        worker = _PushWorker(instance, sync_dir)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(lambda path: self._sync_result_lbl.setText(f"Pushed: {path}"))
        worker.error.connect(lambda msg: self._sync_result_lbl.setText(f"Push error: {msg}"))
        worker.done.connect(thread.quit)
        worker.error.connect(thread.quit)
        self._attach_thread(thread, worker)
        thread.start()

    def _show_pull_menu(self, instance: dict, button: QPushButton) -> None:
        sync_dir = self._sync_dir()
        if not sync_dir:
            return
        instance_id = instance.get("id", "")
        backups = list_remote_backups(instance_id, sync_dir)
        menu = GMenu(self)
        if not backups:
            menu.addAction("No backups available").setEnabled(False)
        else:
            for backup in backups:
                size_mb = backup["size_bytes"] / (1024 * 1024)
                label = f"{backup['timestamp']}  ({size_mb:.1f} MB)"
                menu.addAction(label, lambda _=False, b=backup: self._pull_instance(instance, b["path"]))
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _pull_instance(self, instance: dict, zip_path: str) -> None:
        instances_dir = str(APP_DIR / "instances")
        instance_id = instance.get("id", "")
        thread = QThread(self)
        worker = _PullWorker(instance_id, zip_path, instances_dir)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(lambda dest: self._sync_result_lbl.setText(f"Pulled to: {dest}"))
        worker.error.connect(lambda msg: self._sync_result_lbl.setText(f"Pull error: {msg}"))
        worker.done.connect(thread.quit)
        worker.error.connect(thread.quit)
        self._attach_thread(thread, worker)
        thread.start()

    def _on_sync_now(self) -> None:
        sync_dir = self._sync_dir()
        if not sync_dir:
            self._sync_result_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['danger']};")
            self._sync_result_lbl.setText("No sync directory configured. Go to the Settings tab.")
            return
        self._sync_now_btn.setEnabled(False)
        self._sync_result_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        self._sync_result_lbl.setText("Syncing…")

        thread = QThread(self)
        worker = _SyncAllWorker(sync_dir)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(lambda i, n, name: self._sync_result_lbl.setText(f"[{i+1}/{n}] {name}…"))
        worker.done.connect(self._on_sync_done)
        worker.error.connect(self._on_sync_error)
        worker.done.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(lambda: self._sync_now_btn.setEnabled(True))
        self._attach_thread(thread, worker)
        thread.start()

    def _on_sync_done(self, count: int) -> None:
        self._sync_result_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['success']};")
        self._sync_result_lbl.setText(f"Done — {count} instance(s) pushed.")
        cfg = get_sync_config()
        self._overview_status.setText(
            f"Sync: {'Enabled' if cfg.get('enabled') else 'Disabled'}   Last sync: {cfg.get('last_sync') or 'Never'}"
        )

    def _on_sync_error(self, msg: str) -> None:
        self._sync_result_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['danger']};")
        self._sync_result_lbl.setText(f"Sync error: {msg}")

    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        dir_lbl = QLabel("Sync Directory")
        dir_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 600; color: {C['text_primary']};")
        layout.addWidget(dir_lbl)

        dir_hint = QLabel("Point to a local folder that syncs to the cloud (Dropbox, OneDrive, NAS, etc.).")
        dir_hint.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        dir_hint.setWordWrap(True)
        layout.addWidget(dir_hint)

        dir_row = QHBoxLayout()
        self._dir_input = QLineEdit()
        self._dir_input.setPlaceholderText("Select a folder…")
        self._dir_input.setText(str(config.get("cloud_sync_dir", "") or ""))
        self._dir_input.setFixedHeight(36)
        dir_row.addWidget(self._dir_input)

        browse_btn = OutlineButton("Browse…")
        browse_btn.setFixedHeight(36)
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        self._dir_current_lbl = QLabel(f"Current: {config.get('cloud_sync_dir', '') or '(not set)'}")
        self._dir_current_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        layout.addWidget(self._dir_current_lbl)

        save_btn = PrimaryButton("Save")
        save_btn.setFixedHeight(36)
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn)

        layout.addStretch()
        return page

    def _browse_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Sync Directory")
        if folder:
            self._dir_input.setText(folder)

    def _save_settings(self) -> None:
        sync_dir = self._dir_input.text().strip()
        cfg = get_sync_config()
        cfg["sync_dir"] = sync_dir
        save_sync_config(cfg)
        self._dir_current_lbl.setText(f"Current: {sync_dir or '(not set)'}")
        self._rebuild_instances_list()

    def _patch_config(self, key: str, value: object) -> None:
        config.set(key, value)

    def _attach_thread(self, thread: QThread, worker: QObject) -> None:
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
