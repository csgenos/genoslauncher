"""
GenosLauncher — Master stylesheet and design tokens.
Light / white premium theme, with optional dark mode.
"""

from __future__ import annotations

COLORS: dict[str, str] = {
    'bg_window':        '#F3F4F6',
    'bg_primary':       '#FFFFFF',
    'bg_secondary':     '#F8FAFC',
    'bg_tertiary':      '#EEF2F7',
    'bg_sidebar':       '#F7F8FA',
    'bg_card':          '#FFFFFF',
    'bg_hover':         '#F1F3F5',
    'bg_pressed':       '#E5E7EB',
    'bg_input':         '#FFFFFF',
    'bg_elevated':      '#FFFFFF',
    'accent':           '#111827',
    'accent_hover':     '#1F2937',
    'accent_pressed':   '#030712',
    'accent_blue':      '#D97706',
    'accent_blue_soft': '#FFF7ED',
    'accent_green':     '#047857',
    'accent_green_soft':'#ECFDF5',
    'accent_red':       '#DC2626',
    'accent_orange':    '#D97706',
    'accent_orange_soft':'#FFF7ED',
    'text_primary':     '#111827',
    'text_secondary':   '#4B5563',
    'text_tertiary':    '#8A94A6',
    'text_disabled':    '#C7CED8',
    'text_inverse':     '#FFFFFF',
    'border':           '#E2E8F0',
    'border_strong':    '#CBD5E1',
    'border_focus':     '#D97706',
    'danger':           '#DC2626',
    'warning':          '#D97706',
    'success':          '#047857',
}

_LIGHT_COLORS: dict[str, str] = dict(COLORS)

_DARK_COLORS: dict[str, str] = {
    'bg_window':        '#0B0F14',
    'bg_primary':       '#111827',
    'bg_secondary':     '#0F172A',
    'bg_tertiary':      '#1F2937',
    'bg_sidebar':       '#0D131D',
    'bg_card':          '#111827',
    'bg_hover':         '#1F2937',
    'bg_pressed':       '#263244',
    'bg_input':         '#0F172A',
    'bg_elevated':      '#172033',
    'accent':           '#F8FAFC',
    'accent_hover':     '#E5E7EB',
    'accent_pressed':   '#CBD5E1',
    'accent_blue':      '#F59E0B',
    'accent_blue_soft': '#2A1B08',
    'accent_green':     '#34D399',
    'accent_green_soft':'#052E21',
    'accent_red':       '#F87171',
    'accent_orange':    '#F59E0B',
    'accent_orange_soft':'#2A1B08',
    'text_primary':     '#F8FAFC',
    'text_secondary':   '#CBD5E1',
    'text_tertiary':    '#94A3B8',
    'text_disabled':    '#475569',
    'text_inverse':     '#111827',
    'border':           '#233044',
    'border_strong':    '#334155',
    'border_focus':     '#F59E0B',
    'danger':           '#F87171',
    'warning':          '#F59E0B',
    'success':          '#34D399',
}


_THEME_MODE = "light"


def normalize_theme_mode(mode: str | bool | None) -> str:
    if isinstance(mode, bool):
        return "dark" if mode else "light"
    value = str(mode or "light").strip().lower()
    return value if value in {"light", "dark", "system"} else "light"


def resolve_theme_mode(mode: str | bool | None) -> str:
    normalized = normalize_theme_mode(mode)
    if normalized != "system":
        return normalized
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        scheme = app.styleHints().colorScheme() if app else None
        return "dark" if str(scheme).lower().endswith("dark") else "light"
    except Exception:
        return "light"


def current_theme_mode() -> str:
    return _THEME_MODE


def is_dark_theme() -> bool:
    return _THEME_MODE == "dark"


def apply_theme(mode: str | bool | None) -> None:
    """Switch COLORS in-place and re-apply the global QSS stylesheet."""
    from PySide6.QtWidgets import QApplication
    global _THEME_MODE
    _THEME_MODE = resolve_theme_mode(mode)
    COLORS.update(_DARK_COLORS if _THEME_MODE == "dark" else _LIGHT_COLORS)
    app = QApplication.instance()
    if app:
        app.setStyleSheet(get_stylesheet())
        for widget in app.allWidgets():
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

FONT: dict[str, str] = {
    'xs':  '11px',
    'sm':  '12px',
    'md':  '13px',
    'lg':  '15px',
    'xl':  '18px',
    '2xl': '22px',
    '3xl': '28px',
    '4xl': '36px',
}

# Short alias used throughout the codebase.
C = COLORS


def get_stylesheet() -> str:
    """Return the complete QSS master stylesheet for GenosLauncher."""
    c = COLORS
    return f"""
/* ── Global reset ─────────────────────────────────────────────────────── */
* {{
    font-family: "Segoe UI", "Inter", "SF Pro Display", system-ui, sans-serif;
    font-size: 13px;
    color: {c['text_primary']};
    outline: none;
}}

QMainWindow, QDialog {{
    background-color: {c['bg_window']};
}}

QWidget {{
    background-color: transparent;
    color: {c['text_primary']};
}}

QFrame {{
    color: {c['text_primary']};
}}

QWidget#centralWidget,
QWidget#mainContent {{
    background-color: {c['bg_window']};
}}

/* ── QPushButton base ─────────────────────────────────────────────────── */
QPushButton {{
    background-color: {c['bg_secondary']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: 500;
    min-height: 32px;
}}

QPushButton:hover {{
    background-color: {c['bg_hover']};
    border-color: {c['border_strong']};
}}

QPushButton:pressed {{
    background-color: {c['bg_pressed']};
    border-color: {c['border_strong']};
}}

QPushButton:disabled {{
    background-color: {c['bg_secondary']};
    color: {c['text_disabled']};
    border-color: {c['border']};
}}

QPushButton:focus {{
    border: 1px solid {c['border_focus']};
}}

/* ── Primary (dark navy) button variant ──────────────────────────────── */
QPushButton[class="primary"] {{
    background-color: {c['accent']};
    color: {c['text_inverse']};
    border: none;
}}

QPushButton[class="primary"]:hover {{
    background-color: {c['accent_hover']};
}}

QPushButton[class="primary"]:pressed {{
    background-color: {c['accent_pressed']};
}}

QPushButton[class="primary"]:disabled {{
    background-color: {c['text_disabled']};
    color: {c['text_inverse']};
}}

/* ── Outline (ghost) button variant ─────────────────────────────────── */
QPushButton[class="outline"] {{
    background-color: transparent;
    color: {c['text_primary']};
    border: 1px solid {c['border_strong']};
}}

QPushButton[class="outline"]:hover {{
    background-color: {c['bg_hover']};
    border-color: {c['text_tertiary']};
}}

QPushButton[class="outline"]:pressed {{
    background-color: {c['bg_pressed']};
}}

/* ── QLineEdit ────────────────────────────────────────────────────────── */
QLineEdit {{
    background-color: {c['bg_input']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 13px;
    selection-background-color: {c['accent_blue_soft']};
    selection-color: {c['text_primary']};
    min-height: 32px;
}}

QLineEdit:hover {{
    border-color: {c['border_strong']};
}}

QLineEdit:focus {{
    border: 1.5px solid {c['border_focus']};
    background-color: {c['bg_primary']};
}}

QLineEdit:disabled {{
    background-color: {c['bg_secondary']};
    color: {c['text_disabled']};
    border-color: {c['border']};
}}

QLineEdit::placeholder {{
    color: {c['text_tertiary']};
}}

/* ── QComboBox ────────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {c['bg_input']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 13px;
    min-height: 32px;
}}

QComboBox:hover {{
    border-color: {c['border_strong']};
}}

QComboBox:focus {{
    border: 1.5px solid {c['border_focus']};
}}

QComboBox::drop-down {{
    border: none;
    width: 28px;
}}

QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {c['text_secondary']};
    margin-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {c['bg_elevated']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    selection-background-color: {c['accent_blue_soft']};
    selection-color: {c['text_primary']};
    padding: 4px;
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    color: {c['text_primary']};
    padding: 6px 10px;
    border-radius: 6px;
    min-height: 28px;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {c['bg_hover']};
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: {c['accent_orange_soft']};
    color: {c['text_primary']};
}}

/* ── QScrollBar ───────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 5px;
    margin: 0;
    border-radius: 3px;
}}

QScrollBar::handle:vertical {{
    background: {c['border_strong']};
    border-radius: 3px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c['text_tertiary']};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
    background: transparent;
}}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 5px;
    margin: 0;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal {{
    background: {c['border_strong']};
    border-radius: 3px;
    min-width: 24px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {c['text_tertiary']};
}}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0;
    background: transparent;
}}

/* ── QSlider ──────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {c['border']};
    height: 4px;
    border-radius: 2px;
}}

QSlider::sub-page:horizontal {{
    background: {c['accent']};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {c['bg_primary']};
    border: 2px solid {c['accent']};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    border-color: {c['accent_blue']};
}}

/* ── QCheckBox ────────────────────────────────────────────────────────── */
QCheckBox {{
    spacing: 8px;
    font-size: 13px;
    color: {c['text_primary']};
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid {c['border_strong']};
    border-radius: 4px;
    background: {c['bg_input']};
}}

QCheckBox::indicator:hover {{
    border-color: {c['accent_blue']};
}}

QCheckBox::indicator:checked {{
    background: {c['accent_orange']};
    border-color: {c['accent_orange']};
    image: none;
}}

QCheckBox::indicator:checked:hover {{
    background: {c['accent_orange']};
}}

QCheckBox:disabled {{
    color: {c['text_disabled']};
}}

QCheckBox::indicator:disabled {{
    border-color: {c['border']};
    background: {c['bg_secondary']};
}}

/* ── QProgressBar ─────────────────────────────────────────────────────── */
QProgressBar {{
    background: {c['border']};
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
    font-size: 0px;
}}

QProgressBar::chunk {{
    background: {c['accent_orange']};
    border-radius: 3px;
}}

/* ── QGroupBox ────────────────────────────────────────────────────────── */
QGroupBox {{
    background-color: transparent;
    border: 1px solid {c['border']};
    border-radius: 10px;
    margin-top: 20px;
    padding: 16px 12px 12px 12px;
    font-size: 12px;
    font-weight: 600;
    color: {c['text_secondary']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: 2px;
    padding: 0 6px;
    background: {c['bg_window']};
    color: {c['text_secondary']};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* ── QTabBar ──────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: none;
    background: transparent;
}}

QTabWidget::tab-bar {{
    alignment: left;
}}

QTabBar::tab {{
    background: transparent;
    color: {c['text_tertiary']};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    min-width: 80px;
}}

QTabBar::tab:hover {{
    color: {c['text_secondary']};
    background: {c['bg_hover']};
    border-radius: 6px 6px 0 0;
}}

QTabBar::tab:selected {{
    color: {c['accent_blue']};
    border-bottom: 2px solid {c['accent_blue']};
    font-weight: 600;
}}

/* ── Semantic QLabel classes ──────────────────────────────────────────── */
QLabel#heading {{
    font-size: 22px;
    font-weight: 700;
    color: {c['text_primary']};
    letter-spacing: 0px;
}}

QLabel#subheading {{
    font-size: 15px;
    font-weight: 600;
    color: {c['text_primary']};
}}

QLabel#caption {{
    font-size: 11px;
    color: {c['text_secondary']};
}}

QLabel#muted {{
    font-size: 12px;
    color: {c['text_tertiary']};
}}

/* ── QScrollArea ──────────────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

/* ── QToolTip ─────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {c['bg_primary']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ── QSplitter ────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {c['border']};
    width: 1px;
    height: 1px;
}}

/* ── QMenu ────────────────────────────────────────────────────────────── */
QMenu {{
    background-color: {c['bg_elevated']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 4px;
}}

QMenu::item {{
    color: {c['text_primary']};
    padding: 6px 32px 6px 12px;
    border-radius: 6px;
    font-size: 13px;
}}

QMenu::item:selected {{
    background-color: {c['accent_orange_soft']};
}}

QMenu::separator {{
    height: 1px;
    background: {c['border']};
    margin: 4px 8px;
}}

/* ── QStatusBar ───────────────────────────────────────────────────────── */
QStatusBar {{
    background: {c['bg_primary']};
    border-top: 1px solid {c['border']};
    color: {c['text_secondary']};
    font-size: 11px;
    padding: 0 8px;
}}

/* ── QSpinBox ─────────────────────────────────────────────────────────── */
QSpinBox {{
    background-color: {c['bg_input']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 13px;
    min-height: 32px;
}}

QSpinBox:focus {{
    border: 1.5px solid {c['border_focus']};
}}

QSpinBox::up-button,
QSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 16px;
}}

/* ── Separators ───────────────────────────────────────────────────────── */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: {c['border']};
    background: {c['border']};
}}
"""


def card_style(
    radius: int = 12,
    bg: str = COLORS['bg_card'],
    border: str = COLORS['border'],
) -> str:
    """Return inline-style string for a clean card widget."""
    return (
        f"background-color: {bg}; "
        f"border: 1px solid {border}; "
        f"border-radius: {radius}px;"
    )


def primary_button_style() -> str:
    """QSS snippet for a dark navy primary CTA button."""
    c = COLORS
    return f"""
        QPushButton {{
            background-color: {c['accent']};
            color: {c['text_inverse']};
            border: none;
            border-radius: 8px;
            padding: 8px 20px;
            font-size: 13px;
            font-weight: 600;
            min-height: 36px;
        }}
        QPushButton:hover {{
            background-color: {c['accent_hover']};
        }}
        QPushButton:pressed {{
            background-color: {c['accent_pressed']};
        }}
        QPushButton:disabled {{
            background-color: {c['text_disabled']};
            color: {c['text_inverse']};
        }}
    """


def secondary_button_style() -> str:
    """QSS snippet for a ghost / outline secondary button."""
    c = COLORS
    return f"""
        QPushButton {{
            background-color: transparent;
            color: {c['text_primary']};
            border: 1px solid {c['border_strong']};
            border-radius: 8px;
            padding: 8px 20px;
            font-size: 13px;
            font-weight: 500;
            min-height: 36px;
        }}
        QPushButton:hover {{
            background-color: {c['bg_hover']};
            border-color: {c['text_tertiary']};
        }}
        QPushButton:pressed {{
            background-color: {c['bg_pressed']};
        }}
        QPushButton:disabled {{
            color: {c['text_disabled']};
            border-color: {c['border']};
        }}
    """
