"""
Home tab — clean light-theme launcher home screen.

Layout:
  - Hero section: headline + version picker + Play button
  - LaunchProgressPanel (hidden until launch)
  - Quick-play cards (featured versions)
  - Recent activity / news strip
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QLinearGradient
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import LaunchButton, OutlineButton
from ..components.version_card import VersionCard
from ..components.clean_card import CleanCard
from ..components.progress_widget import LaunchProgressPanel


# ---------------------------------------------------------------------------
# Hero section background — clean light gradient, no animation
# ---------------------------------------------------------------------------

class HeroWidget(QWidget):
    """
    Pale gradient hero banner — top is white, bottom fades to bg_secondary.
    Static; no animation needed in the clean theme.
    """

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(C["bg_primary"]))
        grad.setColorAt(1.0, QColor(C["bg_secondary"]))
        painter.fillRect(self.rect(), grad)
        painter.end()


# ---------------------------------------------------------------------------
# News / update card
# ---------------------------------------------------------------------------

class NewsItem(QFrame):
    """A single clean news card."""

    def __init__(self, title: str, body: str, date: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NewsItem")
        self.setStyleSheet(f"""
            #NewsItem {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        header_row.addWidget(title_lbl)
        header_row.addStretch()
        date_lbl = QLabel(date)
        date_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_tertiary']};")
        header_row.addWidget(date_lbl)
        layout.addLayout(header_row)

        body_lbl = QLabel(body)
        body_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        body_lbl.setWordWrap(True)
        layout.addWidget(body_lbl)


# ---------------------------------------------------------------------------
# Home Tab
# ---------------------------------------------------------------------------

class HomeTab(QWidget):
    """
    Home screen of GenosLauncher.

    Signals:
        launch_requested(str)   — version ID to launch
    """

    launch_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._selected_version: str = "1.21.4"
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet(f"background: {C['bg_secondary']};")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 40)
        cl.setSpacing(0)

        # ---- HERO ----
        hero = HeroWidget()
        hero.setMinimumHeight(300)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(48, 40, 48, 40)
        hero_layout.setSpacing(0)

        hero_layout.addStretch(1)

        # Headline
        headline = QLabel("GenosLauncher")
        headline.setStyleSheet(f"""
            font-size: {FONT["4xl"]};
            font-weight: 800;
            color: {C["text_primary"]};
            letter-spacing: -1.5px;
        """)
        hero_layout.addWidget(headline)

        subhead = QLabel("Open-source · Fast · Elegant")
        subhead.setStyleSheet(f"font-size: {FONT['lg']}; color: {C['text_secondary']}; margin-top: 4px;")
        hero_layout.addWidget(subhead)

        hero_layout.addSpacing(32)

        # Launch row
        launch_row = QHBoxLayout()
        launch_row.setSpacing(10)

        # Version picker
        self._version_combo = QComboBox()
        self._version_combo.setFixedHeight(52)
        self._version_combo.setMinimumWidth(150)
        self._version_combo.setStyleSheet(f"""
            QComboBox {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
                padding: 0 14px;
                font-size: {FONT["md"]};
                font-weight: 600;
                color: {C["text_primary"]};
            }}
            QComboBox:hover {{ border-color: {C["border_strong"]}; }}
            QComboBox:focus {{ border-color: {C["border_focus"]}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
        """)
        versions = [
            "1.21.4", "1.21.3", "1.21.1", "1.20.6", "1.20.4",
            "1.20.2", "1.20.1", "1.19.4", "1.18.2", "1.16.5",
            "1.12.2", "1.8.9",
        ]
        self._version_combo.addItems(versions)
        self._version_combo.currentTextChanged.connect(self._on_version_changed)
        launch_row.addWidget(self._version_combo)

        # Play button
        self._play_btn = LaunchButton("Play")
        self._play_btn.setMinimumWidth(160)

        # Subtle shadow below the button
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 35))
        self._play_btn.setGraphicsEffect(shadow)

        self._play_btn.clicked.connect(self._on_play_clicked)
        launch_row.addWidget(self._play_btn)

        launch_row.addStretch()
        hero_layout.addLayout(launch_row)

        # Progress panel
        self._progress = LaunchProgressPanel()
        hero_layout.addWidget(self._progress)

        hero_layout.addStretch(1)
        cl.addWidget(hero)

        # ---- CONTENT BELOW HERO ----
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(48, 28, 48, 0)
        inner_layout.setSpacing(24)

        # Quick Play section
        qp_header = QHBoxLayout()
        qp_title = QLabel("Quick Play")
        qp_title.setStyleSheet(f"font-size: {FONT['xl']}; font-weight: 700; color: {C['text_primary']};")
        qp_header.addWidget(qp_title)
        qp_header.addStretch()
        view_all = OutlineButton("View all versions →")
        view_all.setFixedHeight(32)
        view_all.setMinimumWidth(160)
        qp_header.addWidget(view_all)
        inner_layout.addLayout(qp_header)

        # Featured version cards — horizontal row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)

        for vid, vtype, installed in [
            ("1.21.4", "release", True),
            ("1.20.1", "release", False),
            ("1.8.9",  "release", False),
        ]:
            card = VersionCard(vid, vtype, installed, self)
            card.setMinimumHeight(115)
            card.launch_requested.connect(self.launch_requested)
            cards_row.addWidget(card)

        inner_layout.addLayout(cards_row)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {C['border']}; border: none;")
        inner_layout.addWidget(divider)

        # News section
        news_title = QLabel("What's New")
        news_title.setStyleSheet(f"font-size: {FONT['xl']}; font-weight: 700; color: {C['text_primary']};")
        inner_layout.addWidget(news_title)

        for title, body, date in [
            (
                "GenosLauncher v0.2 Released",
                "Modpack browser, shader management, and a complete premium light theme redesign are now live.",
                "Today",
            ),
            (
                "Modrinth Integration",
                "Browse and install thousands of modpacks and shaders directly from inside the launcher.",
                "2 days ago",
            ),
            (
                "Java Auto-Detection",
                "The launcher now automatically detects installed Java versions and recommends the best one for your Minecraft version.",
                "1 week ago",
            ),
        ]:
            inner_layout.addWidget(NewsItem(title, body, date, self))

        cl.addWidget(inner)
        scroll.setWidget(content)
        root.addWidget(scroll)

    # ------------------------------------------------------------------
    # Public API (called by main_window)
    # ------------------------------------------------------------------

    def set_launch_state(self, launching: bool) -> None:
        self._play_btn.set_launching(launching)
        if launching:
            self._progress.show_panel()
        else:
            self._progress.hide_panel()

    def update_progress(self, current: int, maximum: int, status: str) -> None:
        if status:
            self._progress.set_status(status)
        if maximum > 0:
            self._progress.set_progress(current, maximum)

    def _on_version_changed(self, version: str) -> None:
        self._selected_version = version

    def _on_play_clicked(self) -> None:
        self.launch_requested.emit(self._selected_version)
