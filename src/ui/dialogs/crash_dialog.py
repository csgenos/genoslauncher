"""Crash report viewer — shows the latest Minecraft crash-reports for an instance."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ..styles import COLORS as C, FONT
from ...core.crash_analyzer import analyze_crash_text


MAX_CRASH_BYTES = 2 * 1024 * 1024


class CrashReportDialog(QDialog):
    """Shows crash reports from <instance>/crash-reports/ folder."""

    def __init__(self, instance: dict, parent=None) -> None:
        super().__init__(parent)
        self._instance = instance
        self._crash_dir = Path(instance.get("directory", "")) / "crash-reports"
        self.setWindowTitle(f"Crash Reports — {instance.get('name', 'Instance')}")
        self.resize(820, 580)
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
        self._selector.setFixedWidth(340)
        self._selector.currentIndexChanged.connect(self._show_selected)
        hdr.addWidget(self._selector)
        layout.addLayout(hdr)

        search_row = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search in report…")
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

    def _copy_to_clipboard(self) -> None:
        text = self._viewer.toPlainText()
        QApplication.clipboard().setText(text)

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
        if not self._crash_dir.exists():
            self._viewer.setPlainText("No crash-reports folder found for this instance.\n"
                                      "Minecraft creates one when a crash occurs.")
            return

        reports = sorted(
            [f for f in self._crash_dir.iterdir() if f.suffix in (".txt", ".log")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not reports:
            self._viewer.setPlainText("No crash reports found. This instance has not crashed yet.")
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
            lines = [f"[{s.severity.upper()}] {s.title}\n{s.detail}" for s in suggestions]
            self._suggestions.setPlainText("\n\n".join(lines))
        except OSError as exc:
            self._viewer.setPlainText(f"Could not read file:\n{exc}")
            self._suggestions.setPlainText("No suggestions available.")
