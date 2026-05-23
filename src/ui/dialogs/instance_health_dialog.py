"""Instance health and optimizer dialog."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTextEdit, QVBoxLayout

from ..styles import COLORS as C, FONT
from ...core.instance_health import analyze_instance_health, optimize_instance


class InstanceHealthDialog(QDialog):
    def __init__(self, instance: dict, parent=None) -> None:
        super().__init__(parent)
        self._instance = instance
        self.setWindowTitle(f"Instance Health - {instance.get('name', 'Instance')}")
        self.resize(760, 520)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        self._headline = QLabel("Health Score: -")
        self._headline.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        root.addWidget(self._headline)

        self._summary = QLabel("")
        self._summary.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        root.addWidget(self._summary)

        self._issues = QTextEdit()
        self._issues.setReadOnly(True)
        self._issues.setStyleSheet(
            f"background: {C['bg_secondary']}; border: 1px solid {C['border']}; border-radius: 8px; color: {C['text_primary']};"
        )
        root.addWidget(self._issues, 1)

        btns = QHBoxLayout()
        optimize_btn = QPushButton("Run Optimizer")
        optimize_btn.setFixedHeight(34)
        optimize_btn.clicked.connect(self._run_optimizer)
        btns.addWidget(optimize_btn)
        btns.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(96)
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        root.addLayout(btns)

    def _refresh(self) -> None:
        report = analyze_instance_health(self._instance)
        self._headline.setText(f"Health Score: {report.score}/100")
        self._summary.setText(
            f"Issues: {len(report.issues)}   Reclaimable: {report.reclaimable_bytes // 1024} KB"
        )
        lines = []
        for issue in report.issues:
            lines.append(f"[{issue.severity.upper()}] {issue.message}")
        if not lines:
            lines.append("No issues found.")
        self._issues.setPlainText("\n".join(lines))

    def _run_optimizer(self) -> None:
        reclaimed, actions = optimize_instance(self._instance)
        QMessageBox.information(
            self,
            "Optimizer Complete",
            f"Reclaimed: {reclaimed // 1024} KB\n\n" + "\n".join(actions[:8]),
        )
        self._refresh()

