"""Crash report viewer with smart suggestions and one-click fixes."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ..styles import COLORS as C, FONT
from ...core.crash_analyzer import analyze_crash_text
from ...core.instances import repair_instance_layout, update_instance


MAX_CRASH_BYTES = 2 * 1024 * 1024


class CrashReportDialog(QDialog):
    """Shows crash reports from <instance>/crash-reports/ folder."""

    def __init__(self, instance: dict, parent=None) -> None:
        super().__init__(parent)
        self._instance = instance
        self._crash_dir = Path(instance.get("directory", "")) / "crash-reports"
        self._suggestion_actions: set[str] = set()
        self.setWindowTitle(f"Crash Reports - {instance.get('name', 'Instance')}")
        self.resize(860, 620)
        self._build_ui()
        self._load_reports()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        hdr = QHBoxLayout()
        title = QLabel("Crash Reports")
        title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        hdr.addWidget(title)
        hdr.addStretch()
        self._selector = QComboBox()
        self._selector.setFixedWidth(360)
        self._selector.currentIndexChanged.connect(self._show_selected)
        hdr.addWidget(self._selector)
        layout.addLayout(hdr)

        search_row = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search in report...")
        self._search_box.setFixedHeight(32)
        self._search_box.setStyleSheet(f"""
            QLineEdit {{
                background: {C["bg_secondary"]};
                border: 1px solid {C["border"]};
                border-radius: 6px;
                padding: 0 10px;
                font-size: {FONT["sm"]};
                color: {C["text_primary"]};
            }}
        """)
        self._search_box.textChanged.connect(self._on_search)
        search_row.addWidget(self._search_box)
        find_next_btn = QPushButton("Find Next")
        find_next_btn.setFixedSize(90, 32)
        find_next_btn.clicked.connect(self._find_next)
        search_row.addWidget(find_next_btn)
        layout.addLayout(search_row)

        self._viewer = QPlainTextEdit()
        self._viewer.setReadOnly(True)
        self._viewer.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {C["bg_secondary"]};
                color: {C["text_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 8px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self._viewer, 1)

        sugg_title = QLabel("Smart Suggestions")
        sugg_title.setStyleSheet(f"font-size: {FONT['sm']}; font-weight: 700; color: {C['text_primary']};")
        layout.addWidget(sugg_title)
        self._suggestions = QTextEdit()
        self._suggestions.setReadOnly(True)
        self._suggestions.setFixedHeight(130)
        self._suggestions.setStyleSheet(f"""
            QTextEdit {{
                background: {C["bg_secondary"]};
                color: {C["text_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 8px;
                font-size: {FONT["xs"]};
                padding: 6px;
            }}
        """)
        layout.addWidget(self._suggestions)

        fix_row = QHBoxLayout()
        self._fix_ram_btn = QPushButton("Apply: Increase RAM")
        self._fix_ram_btn.setFixedHeight(30)
        self._fix_ram_btn.clicked.connect(self._apply_increase_ram)
        fix_row.addWidget(self._fix_ram_btn)
        self._fix_repair_btn = QPushButton("Apply: Repair Instance")
        self._fix_repair_btn.setFixedHeight(30)
        self._fix_repair_btn.clicked.connect(self._apply_repair)
        fix_row.addWidget(self._fix_repair_btn)
        self._fix_logs_btn = QPushButton("Apply: Clear Logs")
        self._fix_logs_btn.setFixedHeight(30)
        self._fix_logs_btn.clicked.connect(self._apply_clear_logs)
        fix_row.addWidget(self._fix_logs_btn)
        fix_row.addStretch()
        layout.addLayout(fix_row)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setFixedHeight(34)
        copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        self._set_action_buttons_enabled()

    def _copy_to_clipboard(self) -> None:
        QApplication.clipboard().setText(self._viewer.toPlainText())

    def _on_search(self, text: str) -> None:
        if not text:
            cursor = self._viewer.textCursor()
            cursor.clearSelection()
            self._viewer.setTextCursor(cursor)
            return
        self._viewer.moveCursor(QTextCursor.MoveOperation.Start)
        self._viewer.find(text)

    def _find_next(self) -> None:
        text = self._search_box.text()
        if not text:
            return
        found = self._viewer.find(text)
        if not found:
            self._viewer.moveCursor(QTextCursor.MoveOperation.Start)
            self._viewer.find(text)

    def _load_reports(self) -> None:
        self._selector.blockSignals(True)
        self._selector.clear()
        self._selector.blockSignals(False)
        if not self._crash_dir.exists():
            self._viewer.setPlainText("No crash-reports folder found for this instance.")
            self._suggestions.setPlainText("No suggestions available.")
            self._suggestion_actions.clear()
            self._set_action_buttons_enabled()
            return

        reports = sorted(
            [f for f in self._crash_dir.iterdir() if f.suffix in (".txt", ".log")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not reports:
            self._viewer.setPlainText("No crash reports found for this instance.")
            self._suggestions.setPlainText("No suggestions available.")
            self._suggestion_actions.clear()
            self._set_action_buttons_enabled()
            return

        self._selector.blockSignals(True)
        for r in reports[:30]:
            self._selector.addItem(r.name, str(r))
        self._selector.blockSignals(False)
        self._show_selected(0)

    def _show_selected(self, _index: int) -> None:
        path_str = self._selector.currentData()
        if not path_str:
            return
        try:
            path = Path(path_str)
            size = path.stat().st_size
            if size > MAX_CRASH_BYTES:
                with open(path, "rb") as fh:
                    fh.seek(max(0, size - MAX_CRASH_BYTES))
                    raw = fh.read(MAX_CRASH_BYTES)
                text = (
                    f"[Showing last {MAX_CRASH_BYTES // 1024:,} KB of {size // 1024:,} KB]\n\n"
                    + raw.decode("utf-8", errors="replace")
                )
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
            self._viewer.setPlainText(text)
            suggestions = analyze_crash_text(text)
            self._suggestion_actions = {s.action_key for s in suggestions if s.action_key}
            self._suggestions.setPlainText("\n\n".join([f"[{s.severity.upper()}] {s.title}\n{s.detail}" for s in suggestions]))
            self._set_action_buttons_enabled()
        except OSError as exc:
            self._viewer.setPlainText(f"Could not read file:\n{exc}")
            self._suggestions.setPlainText("No suggestions available.")
            self._suggestion_actions.clear()
            self._set_action_buttons_enabled()

    def _set_action_buttons_enabled(self) -> None:
        self._fix_ram_btn.setEnabled("increase_ram" in self._suggestion_actions)
        self._fix_repair_btn.setEnabled("repair_instance" in self._suggestion_actions)
        self._fix_logs_btn.setEnabled("clear_runtime_logs" in self._suggestion_actions)

    def _apply_increase_ram(self) -> None:
        try:
            current = int(self._instance.get("ram_mb", 0) or 0)
        except (TypeError, ValueError):
            current = 0
        if current < 2048:
            target = 4096
        elif current < 4096:
            target = 6144
        else:
            target = min(current + 1024, 16384)
        update_instance(self._instance.get("id", ""), ram_mb=target)
        self._instance["ram_mb"] = target
        QMessageBox.information(self, "Applied", f"Instance RAM override set to {target} MB.")

    def _apply_repair(self) -> None:
        created = repair_instance_layout(self._instance)
        text = "Instance layout repaired."
        if created:
            text += f"\nCreated: {', '.join(created)}"
        QMessageBox.information(self, "Applied", text)

    def _apply_clear_logs(self) -> None:
        root = Path(str(self._instance.get("directory", "")).strip())
        cleared: list[str] = []
        for rel in ("logs", "crash-reports"):
            target = root / rel
            if not target.exists():
                continue
            shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True, exist_ok=True)
            cleared.append(rel)
        QMessageBox.information(self, "Applied", f"Cleared: {', '.join(cleared) if cleared else 'nothing'}")
        self._load_reports()

