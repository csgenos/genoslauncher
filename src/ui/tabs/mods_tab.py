"""
Mods tab — placeholder with coming-soon UI.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..styles import COLORS as C, FONT
from ..components.glass_card import GlassCard
from ..components.animated_button import GhostButton


class ComingSoonWidget(QWidget):
    """Animated 'coming soon' widget."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._phase: float = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.03) % (2 * math.pi)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p = self._phase

        pulse = (math.sin(p) + 1) / 2

        # Background orbs
        for i, (rx, ry, r, col) in enumerate([
            (0.5, 0.5, 160, (0, 200, 255)),
            (0.3, 0.6, 100, (130, 80, 220)),
            (0.7, 0.4, 120, (60, 120, 255)),
        ]):
            ox = int(w * rx + math.sin(p + i) * 20)
            oy = int(h * ry + math.cos(p * 0.7 + i) * 15)
            alpha = int(15 + pulse * 8)
            for j in range(4):
                c = QColor(*col, max(0, alpha - j * 3))
                painter.setBrush(c)
                painter.setPen(Qt.NoPen)
                s = r + j * 30
                painter.drawEllipse(ox - s // 2, oy - s // 2, s, s)

        painter.end()


class ModCard(GlassCard):
    """A placeholder mod entry card."""

    def __init__(self, name: str, description: str, category: str, parent=None) -> None:
        super().__init__(hover_glow=True, glow_color=C["accent_purple"], parent=parent)
        self.setFixedHeight(90)

        layout = self.layout()
        layout.setContentsMargins(20, 0, 20, 0)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        from PySide6.QtWidgets import QHBoxLayout
        hl = QHBoxLayout(inner)
        hl.setSpacing(16)
        hl.setContentsMargins(0, 0, 0, 0)

        # Colored dot
        dot = QLabel("◆")
        dot.setStyleSheet(f"color: {C['accent_purple']}; font-size: 20px;")
        hl.addWidget(dot)

        info = QVBoxLayout()
        info.setSpacing(3)
        n = QLabel(name)
        n.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        info.addWidget(n)
        d = QLabel(description)
        d.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        info.addWidget(d)
        hl.addLayout(info)
        hl.addStretch()

        cat = QLabel(category)
        cat.setStyleSheet(f"""
            color: {C["accent_purple"]};
            background: {C["accent_purple"]}22;
            border: 1px solid {C["accent_purple"]}44;
            border-radius: 6px;
            padding: 3px 10px;
            font-size: {FONT["xs"]};
            font-weight: 600;
        """)
        hl.addWidget(cat)

        install_btn = GhostButton("Install", accent=C["accent_cyan"])
        install_btn.setFixedSize(80, 34)
        hl.addWidget(install_btn)

        layout.addWidget(inner)


class ModsTab(QWidget):
    """Mods browser tab — partially placeholder."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 32, 48, 32)
        root.setSpacing(24)

        # Header
        title = QLabel("Mods")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        root.addWidget(title)

        # Coming soon banner
        banner = GlassCard(border=C["accent_purple"] + "44", hover_glow=True, glow_color=C["accent_purple"])
        banner.setFixedHeight(80)
        b_layout = banner.layout()
        b_layout.setContentsMargins(24, 0, 24, 0)
        b_inner = QWidget()
        b_inner.setStyleSheet("background: transparent;")
        from PySide6.QtWidgets import QHBoxLayout
        b_h = QHBoxLayout(b_inner)
        b_h.setSpacing(14)
        icon_lbl = QLabel("🔧")
        icon_lbl.setStyleSheet("font-size: 28px;")
        b_h.addWidget(icon_lbl)
        t_vb = QVBoxLayout()
        t_vb.setSpacing(2)
        tl = QLabel("Mod Browser — Coming in v0.2")
        tl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        t_vb.addWidget(tl)
        sl = QLabel("CurseForge & Modrinth integration is in active development.")
        sl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        t_vb.addWidget(sl)
        b_h.addLayout(t_vb)
        b_h.addStretch()
        b_layout.addWidget(b_inner)
        root.addWidget(banner)

        # Sample mod cards
        mods_label = QLabel("Popular Mods Preview")
        mods_label.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        root.addWidget(mods_label)

        sample_mods = [
            ("OptiFine", "Performance and HD graphics mod", "Performance"),
            ("Sodium", "Modern rendering engine, huge FPS boost", "Performance"),
            ("Fabric API", "Essential library for Fabric mods", "Library"),
            ("JEI", "Just Enough Items — item and recipe viewer", "Utility"),
            ("Biomes O' Plenty", "Adds 90+ new biomes to explore", "World Gen"),
            ("Tinkers' Construct", "Modular weapon and tool crafting system", "Tech"),
        ]
        for name, desc, cat in sample_mods:
            root.addWidget(ModCard(name, desc, cat))

        root.addStretch()
