"""Theme-aware control helpers shared by GenosLauncher widgets."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QListView, QMenu

from ..styles import COLORS as C


def popup_stylesheet() -> str:
    return f"""
        QListView, QAbstractItemView {{
            background: {C['bg_elevated']};
            color: {C['text_primary']};
            border: 1px solid {C['border']};
            border-radius: 8px;
            padding: 4px;
            outline: none;
            selection-background-color: {C['accent_orange_soft']};
            selection-color: {C['text_primary']};
        }}
        QListView::item, QAbstractItemView::item {{
            color: {C['text_primary']};
            min-height: 28px;
            padding: 6px 10px;
            border-radius: 6px;
        }}
        QListView::item:hover, QAbstractItemView::item:hover {{
            background: {C['bg_hover']};
        }}
        QListView::item:selected, QAbstractItemView::item:selected {{
            background: {C['accent_orange_soft']};
            color: {C['text_primary']};
        }}
    """


class GComboBox(QComboBox):
    """QComboBox with a non-native, theme-styled popup view."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        view = QListView(self)
        view.setUniformItemSizes(True)
        self.setView(view)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        self.view().setStyleSheet(popup_stylesheet())

    def showPopup(self) -> None:
        self.refresh_theme()
        super().showPopup()


class GMenu(QMenu):
    """QMenu that refreshes its palette before opening."""

    def popup(self, *args, **kwargs) -> None:
        self.setStyleSheet(popup_stylesheet())
        super().popup(*args, **kwargs)

    def exec(self, *args, **kwargs):  # type: ignore[override]
        self.setStyleSheet(popup_stylesheet())
        return super().exec(*args, **kwargs)
