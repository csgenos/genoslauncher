"""
Mods tab — coming-soon placeholder with sample mod browser cards.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ..components.animated_button import OutlineButton


# ---------------------------------------------------------------------------
# Sample mod card
# ---------------------------------------------------------------------------

class ModCard(QFrame):
    """A clean card for a sample mod entry."""

    def __init__(self, name: str, description: str, category: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ModCard")
        self.setFixedHeight(80)
        self.setStyleSheet(f"""
            #ModCard {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 8px;
            }}
            #ModCard:hover {{ border-color: {C["border_strong"]}; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)

        # Dot icon
        dot = QLabel("◆")
        dot.setStyleSheet(f"color: {C['text_tertiary']}; font-size: 18px;")
        dot.setFixedWidth(24)
        layout.addWidget(dot)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        n_lbl = QLabel(name)
        n_lbl.setStyleSheet(f"font-size: {FONT['md']}; font-weight: 700; color: {C['text_primary']};")
        text_col.addWidget(n_lbl)
        d_lbl = QLabel(description)
        d_lbl.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        text_col.addWidget(d_lbl)
        layout.addLayout(text_col, 1)

        cat_lbl = QLabel(category)
        cat_lbl.setStyleSheet(f"""
            background: {C["bg_secondary"]};
            color: {C["text_secondary"]};
            border: 1px solid {C["border"]};
            border-radius: 5px;
            padding: 2px 8px;
            font-size: {FONT["xs"]};
            font-weight: 600;
        """)
        layout.addWidget(cat_lbl)

        install_btn = OutlineButton("Install")
        install_btn.setFixedSize(72, 30)
        layout.addWidget(install_btn)


# ---------------------------------------------------------------------------
# Mods Tab
# ---------------------------------------------------------------------------

class ModsTab(QWidget):
    """Mods browser — partially placeholder until v0.3."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 28, 40, 28)
        root.setSpacing(20)

        # Header
        title = QLabel("Mods")
        title.setStyleSheet(f"font-size: {FONT['2xl']}; font-weight: 800; color: {C['text_primary']};")
        root.addWidget(title)

        # Coming-soon banner
        banner = QFrame()
        banner.setObjectName("Banner")
        banner.setFixedHeight(80)
        banner.setStyleSheet(f"""
            #Banner {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
            }}
        """)
        b_h = QHBoxLayout(banner)
        b_h.setContentsMargins(20, 0, 20, 0)
        b_h.setSpacing(14)
        icon_lbl = QLabel("🔧")
        icon_lbl.setStyleSheet("font-size: 26px;")
        b_h.addWidget(icon_lbl)
        t_col = QVBoxLayout()
        t_col.setSpacing(2)
        t_col.addWidget(_lbl("Mod Browser — Coming in v0.3", FONT["md"], C["text_primary"], bold=True))
        t_col.addWidget(_lbl("CurseForge & Modrinth integration is in active development.", FONT["sm"], C["text_secondary"]))
        b_h.addLayout(t_col)
        b_h.addStretch()
        root.addWidget(banner)

        # Sample mod cards
        root.addWidget(_lbl("Popular Mods Preview", FONT["lg"], C["text_primary"], bold=True))

        mods = [
            ("OptiFine",            "Performance and HD graphics mod",              "Performance"),
            ("Sodium",              "Modern rendering engine, huge FPS boost",       "Performance"),
            ("Fabric API",          "Essential library for all Fabric mods",         "Library"),
            ("JEI",                 "Just Enough Items — item and recipe viewer",    "Utility"),
            ("Biomes O' Plenty",    "Adds 90+ new biomes to explore",               "World Gen"),
            ("Tinkers' Construct",  "Modular weapon and tool crafting system",       "Tech"),
        ]
        for name, desc, cat in mods:
            root.addWidget(ModCard(name, desc, cat))

        root.addStretch()


def _lbl(text: str, size: str, color: str, bold: bool = False) -> QLabel:
    w = QLabel(text)
    weight = "700" if bold else "400"
    w.setStyleSheet(f"font-size: {size}; font-weight: {weight}; color: {color};")
    return w
