"""Crash report viewer — shows the latest Minecraft crash-reports for an instance."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..styles import COLORS as C, FONT


MAX_CRASH_BYTES = 2 * 1024 * 1024


class CrashReportDialog(QDialog):
    """Shows crash reports from <instance>/crash-reports/ folder."""

    def __init__(self, instance: dict, parent=None) -> None:
        super().__init__(parent)
        self._instance = instance
        self._crash_dir = Path(instance.get("directory", "")) / "crash-reports"
        self.setWindowTitle(f"Crash Reports — {instance.get('name', 'Instance')}")
        self.resize(820, 560)
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

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)

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
        except OSError as exc:
            self._viewer.setPlainText(f"Could not read file:\n{exc}")
