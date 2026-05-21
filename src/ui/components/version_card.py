"""
VersionCard — clean light-theme card for a single Minecraft version.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from .animated_button import OutlineButton


class VersionCard(QWidget):
    """
    Light-theme card displaying a single Minecraft version.

    Left side: version number (bold 16px), type badge pill, subtitle.
    Right side: Launch or Install OutlineButton.
    Installed versions show a green checkmark badge.
    Shadow deepens on hover (no color change to the card itself).

    Signals:
        launch_requested(str)  — emitted with version_id on button click
        install_requested(str) — emitted with version_id when not installed
    """

    launch_requested = Signal(str)
    install_requested = Signal(str)

    _TYPE_META: dict[str, tuple[str, str, str]] = {
        # type: (label, text-color, bg-color)
        'release':   ('Release',  C['accent_green'],  C['accent_green_soft']),
        'snapshot':  ('Snapshot', C['accent_orange'], '#FFF7ED'),
        'old_alpha': ('Alpha',    C['accent_blue'],   C['accent_blue_soft']),
        'old_beta':  ('Beta',     C['accent_blue'],   C['accent_blue_soft']),
    }

    def __init__(
        self,
        version_id: str,
        version_type: str = 'release',
        is_installed: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._version_id = version_id
        self._version_type = version_type
        self._is_installed = is_installed
        self._hover_progress: float = 0.0

        # Shadow that lifts on hover
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(10)
        self._shadow.setOffset(0, 2)
        self._shadow.setColor(QColor(0, 0, 0, 14))
        self.setGraphicsEffect(self._shadow)

        self._anim = QPropertyAnimation(self, b"hover_progress", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self._build_ui()

    # --- Qt property -------------------------------------------------------

    def _get_hover(self) -> float:
        return self._hover_progress

    def _set_hover(self, val: float) -> None:
        self._hover_progress = val
        blur   = int(10 + val * 10)
        offset = int(2  + val * 2)
        alpha  = int(14 + val * 14)
        self._shadow.setBlurRadius(blur)
        self._shadow.setOffset(0, offset)
        self._shadow.setColor(QColor(0, 0, 0, alpha))
        self.update()

    hover_progress = Property(float, _get_hover, _set_hover)

    # --- UI ----------------------------------------------------------------

    def _badge(self, text: str, text_color: str, bg_color: str) -> QLabel:
        lbl = QLabel(text, self)
        lbl.setStyleSheet(
            f"color: {text_color}; background-color: {bg_color}; "
            f"border-radius: 10px; padding: 2px 10px; "
            f"font-size: {FONT['xs']}; font-weight: 600;"
        )
        lbl.setFixedHeight(20)
        return lbl

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(12)

        # Left content
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(4)

        # Version number
        ver_label = QLabel(self._version_id, self)
        ver_label.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {C['text_primary']}; "
            f"letter-spacing: -0.2px;"
        )
        left.addWidget(ver_label)

        # Badge row
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(6)

        label, text_color, bg_color = self._TYPE_META.get(
            self._version_type,
            ('Release', C['accent_green'], C['accent_green_soft']),
        )
        badge_row.addWidget(self._badge(label, text_color, bg_color))

        if self._is_installed:
            badge_row.addWidget(
                self._badge("  Installed", C['accent_green'], C['accent_green_soft'])
            )

        badge_row.addStretch()
        left.addLayout(badge_row)

        # Subtitle
        subtitle_map = {
            'release':   'Official stable release',
            'snapshot':  'Development preview · may be unstable',
            'old_alpha': 'Classic Alpha era',
            'old_beta':  'Classic Beta era',
        }
        subtitle = QLabel(subtitle_map.get(self._version_type, ''), self)
        subtitle.setStyleSheet(
            f"color: {C['text_tertiary']}; font-size: {FONT['sm']};"
        )
        left.addWidget(subtitle)

        outer.addLayout(left, 1)

        # Right: action button
        right = QVBoxLayout()
        right.setAlignment(Qt.AlignVCenter | Qt.AlignRight)

        action_label = "Launch" if self._is_installed else "Install"
        btn = OutlineButton(action_label, parent=self)
        btn.setFixedHeight(34)
        btn.setMinimumWidth(80)
        btn.clicked.connect(self._on_action)
        right.addWidget(btn)

        outer.addLayout(right)

    def _on_action(self) -> None:
        if self._is_installed:
            self.launch_requested.emit(self._version_id)
        else:
            self.install_requested.emit(self._version_id)

    # --- Events ------------------------------------------------------------

    def enterEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover_progress)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover_progress)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)

    # --- Paint -------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = 10.0

        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)

        # White card fill
        painter.fillPath(path, QColor(C['bg_card']))

        # 1px border
        painter.setPen(QColor(C['border']))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(0.5, 0.5, w - 1, h - 1, r, r)

        painter.end()
