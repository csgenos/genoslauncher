"""
Home tab — featured version card + quick launch + news section.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
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
from ..components.animated_button import LaunchButton, GhostButton
from ..components.version_card import VersionCard
from ..components.glass_card import GlassCard
from ..components.progress_widget import LaunchProgressPanel


class HeroBackground(QWidget):
    """Animated gradient orb background for the hero section."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._phase: float = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30fps
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.008) % (2 * math.pi)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p = self._phase

        # Base gradient
        base_grad = QLinearGradient(0, 0, 0, h)
        base_grad.setColorAt(0.0, QColor(C["bg_deep"]))
        base_grad.setColorAt(1.0, QColor(C["bg_primary"]))
        painter.fillRect(self.rect(), base_grad)

        # Orb 1 — cyan, top-right, slow float
        cx1 = int(w * 0.75 + math.sin(p) * 30)
        cy1 = int(h * 0.35 + math.cos(p * 0.7) * 20)
        r1 = 220
        orb1 = QColor(0, 200, 255, 25)
        painter.setBrush(orb1)
        painter.setPen(Qt.NoPen)
        # Soft radial look via layered ellipses
        for i in range(5):
            alpha = 20 - i * 3
            size = r1 + i * 40
            c = QColor(0, 200, 255, max(0, alpha))
            painter.setBrush(c)
            painter.drawEllipse(cx1 - size // 2, cy1 - size // 2, size, size)

        # Orb 2 — purple, bottom-left
        cx2 = int(w * 0.2 + math.sin(p * 0.6 + 1.2) * 25)
        cy2 = int(h * 0.65 + math.cos(p * 0.8) * 20)
        r2 = 180
        for i in range(5):
            alpha = 18 - i * 3
            size = r2 + i * 35
            c = QColor(130, 80, 220, max(0, alpha))
            painter.setBrush(c)
            painter.drawEllipse(cx2 - size // 2, cy2 - size // 2, size, size)

        # Orb 3 — blue, center
        cx3 = int(w * 0.5 + math.sin(p * 0.4 + 2.5) * 40)
        cy3 = int(h * 0.2 + math.cos(p * 0.5) * 15)
        r3 = 140
        for i in range(4):
            alpha = 12 - i * 2
            size = r3 + i * 30
            c = QColor(60, 120, 255, max(0, alpha))
            painter.setBrush(c)
            painter.drawEllipse(cx3 - size // 2, cy3 - size // 2, size, size)

        # Vignette overlay (darkens edges)
        vignette = QLinearGradient(0, 0, 0, h)
        vignette.setColorAt(0.0, QColor(0, 0, 0, 60))
        vignette.setColorAt(0.4, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 80))
        painter.fillRect(self.rect(), vignette)

        painter.end()


class NewsCard(GlassCard):
    """A simple news/update item card."""

    def __init__(self, title: str, body: str, date: str, parent=None) -> None:
        super().__init__(hover_glow=True, glow_color=C["accent_purple"], parent=parent)
        layout = self.layout()
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        header.addWidget(title_lbl)
        header.addStretch()
        date_lbl = QLabel(date)
        date_lbl.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_muted']};")
        header.addWidget(date_lbl)
        layout.addLayout(header)

        body_lbl = QLabel(body)
        body_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        body_lbl.setWordWrap(True)
        layout.addWidget(body_lbl)


class HomeTab(QWidget):
    """
    Home tab content.

    Signals:
        launch_requested(str)  — version ID to launch
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

        # Scrollable content
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet(f"background-color: {C['bg_primary']};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 40)
        content_layout.setSpacing(0)

        # ---- HERO SECTION ----
        hero = QWidget()
        hero.setMinimumHeight(340)
        hero.setStyleSheet("background: transparent;")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(48, 0, 48, 40)
        hero_layout.setSpacing(0)

        # Animated background
        self._hero_bg = HeroBackground(hero)
        self._hero_bg.setGeometry(0, 0, 9999, 9999)

        hero_layout.addStretch(1)

        # Welcome tag
        welcome_tag = QLabel("✨  Welcome back, Player")
        welcome_tag.setStyleSheet(f"""
            color: {C["accent_cyan"]};
            background-color: {C["accent_cyan"]}18;
            border: 1px solid {C["accent_cyan"]}33;
            border-radius: 20px;
            padding: 5px 14px;
            font-size: {FONT["sm"]};
            font-weight: 600;
        """)
        welcome_tag.setFixedWidth(220)
        hero_layout.addWidget(welcome_tag)
        hero_layout.addSpacing(16)

        # Big headline
        headline = QLabel("Ready to Play?")
        headline.setStyleSheet(f"""
            font-size: {FONT["4xl"]};
            font-weight: 800;
            color: {C["text_primary"]};
            letter-spacing: -1px;
        """)
        hero_layout.addWidget(headline)

        sub = QLabel("Launch Minecraft instantly or browse versions below.")
        sub.setStyleSheet(f"font-size: {FONT['lg']}; color: {C['text_secondary']}; margin-top: 6px;")
        hero_layout.addWidget(sub)

        hero_layout.addSpacing(32)

        # Launch controls
        launch_row = QHBoxLayout()
        launch_row.setSpacing(12)

        # Version picker
        self._version_combo = QComboBox()
        self._version_combo.setFixedHeight(64)
        self._version_combo.setMinimumWidth(160)
        self._version_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {C["bg_card"]};
                color: {C["text_primary"]};
                border: 1px solid {C["border_accent"]};
                border-radius: 32px;
                padding: 0 20px;
                font-size: {FONT["md"]};
                font-weight: 600;
            }}
            QComboBox:hover {{ border-color: {C["accent_cyan_dim"]}; }}
            QComboBox::drop-down {{ border: none; width: 32px; }}
        """)
        versions = [
            "1.21.4", "1.21.3", "1.21.1", "1.20.6", "1.20.4",
            "1.20.2", "1.20.1", "1.19.4", "1.18.2", "1.16.5",
            "1.12.2", "1.8.9",
        ]
        self._version_combo.addItems(versions)
        self._version_combo.currentTextChanged.connect(self._on_version_changed)
        launch_row.addWidget(self._version_combo)

        # Launch button
        self._launch_btn = LaunchButton("⚡  LAUNCH")
        self._launch_btn.setMinimumWidth(200)
        self._launch_btn.clicked.connect(self._on_launch_clicked)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(C["accent_cyan"] + "66"))
        self._launch_btn.setGraphicsEffect(shadow)
        launch_row.addWidget(self._launch_btn)

        launch_row.addStretch()
        hero_layout.addLayout(launch_row)

        # Launch progress
        self._progress_panel = LaunchProgressPanel()
        hero_layout.addWidget(self._progress_panel)

        hero_layout.addStretch(1)
        content_layout.addWidget(hero)

        # ---- FEATURED VERSIONS ----
        section_container = QWidget()
        section_layout = QVBoxLayout(section_container)
        section_layout.setContentsMargins(48, 32, 48, 0)
        section_layout.setSpacing(20)

        # Section header
        sec_header = QHBoxLayout()
        sec_title = QLabel("Quick Play")
        sec_title.setStyleSheet(f"font-size: {FONT['xl']}; font-weight: 700; color: {C['text_primary']};")
        sec_header.addWidget(sec_title)
        sec_header.addStretch()
        view_all = GhostButton("View All Versions →", accent=C["accent_cyan"])
        view_all.setFixedHeight(34)
        view_all.setFixedWidth(180)
        sec_header.addWidget(view_all)
        section_layout.addLayout(sec_header)

        # Featured version cards
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)

        featured_versions = [
            ("1.21.4", "release", True, True),
            ("1.20.1", "release", False, False),
            ("1.8.9",  "release", False, False),
        ]
        for vid, vtype, installed, featured in featured_versions:
            card = VersionCard(vid, vtype, installed, featured, self)
            card.setMinimumHeight(170)
            card.launch_requested.connect(self.launch_requested)
            cards_row.addWidget(card)

        section_layout.addLayout(cards_row)

        # ---- NEWS SECTION ----
        news_title = QLabel("What's New")
        news_title.setStyleSheet(f"font-size: {FONT['xl']}; font-weight: 700; color: {C['text_primary']}; margin-top: 16px;")
        section_layout.addWidget(news_title)

        news_items = [
            ("GenosLauncher Alpha Released", "The first public alpha of GenosLauncher is now available. Download and share your feedback!", "Today"),
            ("Minecraft 1.21.4 Support", "Full support for Minecraft 1.21.4 is live. Enjoy the latest features and bug fixes.", "2 days ago"),
            ("Microsoft Account Integration", "OAuth-based Microsoft login is in active development. Stay tuned for the next update.", "1 week ago"),
        ]
        for title, body, date in news_items:
            news = NewsCard(title, body, date, self)
            news.setFixedHeight(110)
            section_layout.addWidget(news)

        content_layout.addWidget(section_container)
        scroll.setWidget(content)
        root.addWidget(scroll)

    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        self._hero_bg.setGeometry(0, 0, self._hero_bg.parent().width(), self._hero_bg.parent().height())
        super().resizeEvent(event)

    def _on_version_changed(self, version: str) -> None:
        self._selected_version = version

    def _on_launch_clicked(self) -> None:
        self.launch_requested.emit(self._selected_version)

    def set_launch_state(self, launching: bool) -> None:
        self._launch_btn.set_launching(launching)
        if launching:
            self._progress_panel.show_panel()
        else:
            self._progress_panel.hide_panel()

    def update_progress(self, current: int, maximum: int, status: str) -> None:
        if status:
            self._progress_panel.set_status(status)
        if maximum > 0:
            self._progress_panel.set_progress(current, maximum)

    def update_username(self, username: str) -> None:
        pass  # wire up to welcome label if desired
