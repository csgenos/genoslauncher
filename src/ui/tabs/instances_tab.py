"""
Instances tab — browse, install, and manage Minecraft versions.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import OutlineButton
from ..components.version_card import VersionCard
from ...core.launcher import get_available_versions, get_installed_versions


class InstancesTab(QWidget):
    """Browse all available Minecraft versions with filtering."""

    launch_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._all_versions: list[dict] = []
        self._installed: set[str] = set()
        self._show_snapshots = False
        self._show_old = False
        self._search_text = ""
        self._build_ui()
        self._load_versions()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 32, 48, 32)
        root.setSpacing(24)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Instances")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        header_row.addWidget(title)
        header_row.addStretch()

        refresh_btn = OutlineButton("↻  Refresh")
        refresh_btn.setFixedHeight(34)
        refresh_btn.setFixedWidth(110)
        refresh_btn.clicked.connect(self._load_versions)
        header_row.addWidget(refresh_btn)
        root.addLayout(header_row)

        # Filter bar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search versions…")
        self._search_box.setFixedHeight(38)
        self._search_box.textChanged.connect(self._on_search)
        filter_row.addWidget(self._search_box)

        self._snap_check = QCheckBox("Snapshots")
        self._snap_check.setChecked(False)
        self._snap_check.toggled.connect(self._on_filter_changed)
        filter_row.addWidget(self._snap_check)

        self._old_check = QCheckBox("Legacy")
        self._old_check.setChecked(False)
        self._old_check.toggled.connect(self._on_filter_changed)
        filter_row.addWidget(self._old_check)

        root.addLayout(filter_row)

        # Count label
        self._count_label = QLabel("Loading versions...")
        self._count_label.setStyleSheet(f"color: {C['text_secondary']}; font-size: {FONT['sm']};")
        root.addWidget(self._count_label)

        # Scrollable version grid
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._versions_container = QWidget()
        self._versions_container.setStyleSheet("background: transparent;")
        self._versions_layout = QVBoxLayout(self._versions_container)
        self._versions_layout.setSpacing(10)
        self._versions_layout.setContentsMargins(0, 0, 8, 0)
        self._versions_layout.addStretch()

        self._scroll.setWidget(self._versions_container)
        root.addWidget(self._scroll)

    def _load_versions(self) -> None:
        self._all_versions = get_available_versions(
            include_snapshots=self._show_snapshots,
            include_old=self._show_old,
        )
        try:
            self._installed = set(get_installed_versions())
        except Exception:
            self._installed = set()
        self._render_versions()

    def _on_search(self, text: str) -> None:
        self._search_text = text.lower()
        self._render_versions()

    def _on_filter_changed(self) -> None:
        self._show_snapshots = self._snap_check.isChecked()
        self._show_old = self._old_check.isChecked()
        self._load_versions()

    def _render_versions(self) -> None:
        # Clear existing cards
        while self._versions_layout.count() > 1:
            item = self._versions_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        filtered = [
            v for v in self._all_versions
            if self._search_text in v["id"].lower()
        ]

        self._count_label.setText(f"{len(filtered)} versions found")

        for v in filtered[:60]:  # cap for performance
            vid = v["id"]
            card = VersionCard(
                version_id=vid,
                version_type=v.get("type", "release"),
                is_installed=vid in self._installed,
                parent=self._versions_container,
            )
            card.setFixedHeight(115)
            card.launch_requested.connect(self.launch_requested)
            self._versions_layout.insertWidget(self._versions_layout.count() - 1, card)
