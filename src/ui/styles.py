"""
Master stylesheet and color constants for GenosLauncher.

All QSS lives here. Import COLORS for dynamic styling in Python,
and call get_stylesheet() to apply the global style to QApplication.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

COLORS = {
    # Backgrounds
    "bg_deep":          "#070A0F",
    "bg_primary":       "#0D1117",
    "bg_secondary":     "#13161F",
    "bg_sidebar":       "#0F1219",
    "bg_card":          "#1A1E2E",
    "bg_card_hover":    "#1F2438",
    "bg_card_alt":      "#141824",
    "bg_input":         "#0D1117",
    "bg_hover":         "#1C2030",
    "bg_pressed":       "#252A40",

    # Accents
    "accent_cyan":      "#00E5FF",
    "accent_cyan_dim":  "#00B8D4",
    "accent_cyan_glow": "#00E5FF66",
    "accent_purple":    "#9B59F0",
    "accent_purple_dim":"#7C3AED",
    "accent_blue":      "#4488FF",
    "accent_green":     "#00E676",
    "accent_orange":    "#FF9F43",

    # Text
    "text_primary":     "#F0F6FC",
    "text_secondary":   "#8B949E",
    "text_muted":       "#484F58",
    "text_accent":      "#00E5FF",

    # Borders
    "border":           "#21262D",
    "border_accent":    "#00E5FF33",
    "border_hover":     "#00E5FF66",

    # Semantic
    "danger":           "#F85149",
    "warning":          "#D29922",
    "success":          "#3FB950",

    # Sidebar active indicator
    "sidebar_active_bg": "#00E5FF18",
}

# Font sizes (px)
FONT = {
    "xs":   "11px",
    "sm":   "12px",
    "md":   "14px",
    "lg":   "16px",
    "xl":   "20px",
    "2xl":  "24px",
    "3xl":  "32px",
    "4xl":  "40px",
}

C = COLORS  # shorthand alias


def get_stylesheet() -> str:
    """Return the complete application QSS stylesheet."""
    return f"""

/* =========================================================
   GLOBAL RESET & BASE
   ========================================================= */

* {{
    font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
    font-size: {FONT["md"]};
    color: {C["text_primary"]};
    selection-background-color: {C["accent_cyan"]}55;
    selection-color: {C["text_primary"]};
    outline: none;
}}

QMainWindow, QDialog, QWidget {{
    background-color: {C["bg_primary"]};
}}

/* =========================================================
   SCROLL BARS  — thin, minimal, accent-colored
   ========================================================= */

QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {C["border"]};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {C["accent_cyan_dim"]};
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: none;
    border: none;
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {C["border"]};
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {C["accent_cyan_dim"]};
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: none;
    border: none;
    width: 0;
}}

/* =========================================================
   TOOL TIPS
   ========================================================= */

QToolTip {{
    background-color: {C["bg_card"]};
    color: {C["text_primary"]};
    border: 1px solid {C["border_accent"]};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: {FONT["sm"]};
}}

/* =========================================================
   PUSH BUTTONS — base style (components override individually)
   ========================================================= */

QPushButton {{
    background-color: {C["bg_card"]};
    color: {C["text_primary"]};
    border: 1px solid {C["border"]};
    border-radius: 8px;
    padding: 8px 18px;
    font-size: {FONT["md"]};
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {C["bg_card_hover"]};
    border-color: {C["accent_cyan_dim"]};
}}
QPushButton:pressed {{
    background-color: {C["bg_pressed"]};
    border-color: {C["accent_cyan"]};
}}
QPushButton:disabled {{
    color: {C["text_muted"]};
    border-color: {C["border"]};
    background-color: {C["bg_secondary"]};
}}

/* =========================================================
   LINE EDITS / TEXT INPUTS
   ========================================================= */

QLineEdit {{
    background-color: {C["bg_input"]};
    color: {C["text_primary"]};
    border: 1px solid {C["border"]};
    border-radius: 8px;
    padding: 10px 14px;
    font-size: {FONT["md"]};
}}
QLineEdit:focus {{
    border-color: {C["accent_cyan_dim"]};
    background-color: {C["bg_card"]};
}}
QLineEdit:hover {{
    border-color: {C["border_hover"]};
}}
QLineEdit::placeholder {{
    color: {C["text_muted"]};
}}

/* =========================================================
   COMBO BOXES
   ========================================================= */

QComboBox {{
    background-color: {C["bg_input"]};
    color: {C["text_primary"]};
    border: 1px solid {C["border"]};
    border-radius: 8px;
    padding: 8px 14px;
    font-size: {FONT["md"]};
    min-width: 120px;
}}
QComboBox:hover {{
    border-color: {C["border_hover"]};
}}
QComboBox:focus {{
    border-color: {C["accent_cyan_dim"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {C["text_secondary"]};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {C["bg_card"]};
    border: 1px solid {C["border_accent"]};
    border-radius: 8px;
    selection-background-color: {C["accent_cyan"]}22;
    selection-color: {C["accent_cyan"]};
    padding: 4px;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 8px 12px;
    border-radius: 4px;
}}

/* =========================================================
   SLIDERS
   ========================================================= */

QSlider::groove:horizontal {{
    height: 4px;
    background: {C["border"]};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {C["accent_cyan"]};
    border: 2px solid {C["bg_primary"]};
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
}}
QSlider::handle:horizontal:hover {{
    background: {C["text_primary"]};
    border-color: {C["accent_cyan"]};
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {C["accent_purple"]},
        stop:1 {C["accent_cyan"]}
    );
    border-radius: 2px;
}}

/* =========================================================
   CHECK BOXES
   ========================================================= */

QCheckBox {{
    spacing: 10px;
    color: {C["text_secondary"]};
    font-size: {FONT["md"]};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 2px solid {C["border"]};
    background: {C["bg_input"]};
}}
QCheckBox::indicator:hover {{
    border-color: {C["accent_cyan_dim"]};
}}
QCheckBox::indicator:checked {{
    background: {C["accent_cyan"]};
    border-color: {C["accent_cyan"]};
    image: none;
}}

/* =========================================================
   PROGRESS BAR
   ========================================================= */

QProgressBar {{
    background-color: {C["bg_secondary"]};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    font-size: {FONT["xs"]};
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {C["accent_purple"]},
        stop:0.5 {C["accent_cyan"]},
        stop:1 {C["accent_blue"]}
    );
    border-radius: 4px;
}}

/* =========================================================
   TAB WIDGET (used inside settings panels, not sidebar)
   ========================================================= */

QTabWidget::pane {{
    border: 1px solid {C["border"]};
    border-radius: 10px;
    background-color: {C["bg_card"]};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {C["text_secondary"]};
    padding: 10px 20px;
    border-bottom: 2px solid transparent;
    font-size: {FONT["md"]};
    font-weight: 500;
}}
QTabBar::tab:selected {{
    color: {C["accent_cyan"]};
    border-bottom-color: {C["accent_cyan"]};
}}
QTabBar::tab:hover:!selected {{
    color: {C["text_primary"]};
}}

/* =========================================================
   LABELS (semantic classes)
   ========================================================= */

QLabel#heading {{
    font-size: {FONT["2xl"]};
    font-weight: 700;
    color: {C["text_primary"]};
}}
QLabel#subheading {{
    font-size: {FONT["lg"]};
    font-weight: 600;
    color: {C["text_secondary"]};
}}
QLabel#caption {{
    font-size: {FONT["sm"]};
    color: {C["text_muted"]};
}}
QLabel#accent {{
    color: {C["accent_cyan"]};
    font-weight: 700;
}}

/* =========================================================
   GROUP BOXES (settings sections)
   ========================================================= */

QGroupBox {{
    border: 1px solid {C["border"]};
    border-radius: 10px;
    margin-top: 16px;
    padding: 16px;
    background-color: {C["bg_card"]};
    font-size: {FONT["md"]};
    font-weight: 600;
    color: {C["text_secondary"]};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: -2px;
    padding: 0 6px;
    color: {C["accent_cyan"]};
    font-size: {FONT["sm"]};
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

/* =========================================================
   SPIN BOX
   ========================================================= */

QSpinBox {{
    background-color: {C["bg_input"]};
    color: {C["text_primary"]};
    border: 1px solid {C["border"]};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: {FONT["md"]};
}}
QSpinBox:focus {{
    border-color: {C["accent_cyan_dim"]};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 16px;
}}

/* =========================================================
   SEPARATOR
   ========================================================= */

QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: {C["border"]};
}}

/* =========================================================
   MENU BAR & MENUS (hidden in frameless, kept for reference)
   ========================================================= */

QMenuBar {{
    background-color: {C["bg_sidebar"]};
    color: {C["text_primary"]};
    border-bottom: 1px solid {C["border"]};
}}
QMenu {{
    background-color: {C["bg_card"]};
    border: 1px solid {C["border_accent"]};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 16px;
    border-radius: 5px;
}}
QMenu::item:selected {{
    background-color: {C["accent_cyan"]}22;
    color: {C["accent_cyan"]};
}}

"""


def card_style(
    bg: str = C["bg_card"],
    border: str = C["border"],
    radius: int = 14,
    padding: int = 20,
) -> str:
    """Generate inline style for a glass card widget."""
    return (
        f"background-color: {bg};"
        f"border: 1px solid {border};"
        f"border-radius: {radius}px;"
        f"padding: {padding}px;"
    )


def accent_button_style(
    bg_start: str = C["accent_purple"],
    bg_end: str = C["accent_cyan"],
    radius: int = 10,
) -> str:
    """Generate style for a gradient accent button."""
    return f"""
        QPushButton {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {bg_start},
                stop:1 {bg_end}
            );
            color: {C["bg_deep"]};
            border: none;
            border-radius: {radius}px;
            font-size: {FONT["md"]};
            font-weight: 700;
            letter-spacing: 0.5px;
        }}
        QPushButton:hover {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {bg_end},
                stop:1 {bg_start}
            );
        }}
        QPushButton:pressed {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {bg_start}cc,
                stop:1 {bg_end}cc
            );
        }}
    """
