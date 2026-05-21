"""
VersionCard — a premium card displaying a single Minecraft version.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from .animated_button import GhostButton, LaunchButton


class VersionCard(QWidget):
    """
    Card that displays a Minecraft version with quick-launch action.

    Signals:
        launch_requested(str)  — emitted with the version ID when user clicks Launch
    """

    launch_requested = Signal(str)

    def __init__(
        self,
        version_id: str,
        version_type: str = "release",
        is_installed: bool = False,
        is_featured: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._version_id = version_id
        self._version_type = version_type
        self._is_installed = is_installed
        self._is_featured = is_featured

        self._hover_progress: float = 0.0

        # Glow shadow
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(0, 6)
        color = QColor(C["accent_cyan"] if is_featured else C["accent_purple"])
        color.setAlpha(0)
        self._shadow.setColor(color)
        self.setGraphicsEffect(self._shadow)

        self._anim = QPropertyAnimation(self, b"card_hover", self)
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self._build_ui()

    # ------------------------------------------------------------------
    # Property
    # ------------------------------------------------------------------

    def _get_card_hover(self) -> float:
        return self._hover_progress

    def _set_card_hover(self, val: float) -> None:
        self._hover_progress = val
        blur = int(val * 24)
        alpha = int(val * 140)
        c = QColor(C["accent_cyan"] if self._is_featured else C["accent_purple"])
        c.setAlpha(alpha)
        self._shadow.setBlurRadius(blur)
        self._shadow.setColor(c)
        self.update()

    card_hover = Property(float, _get_card_hover, _set_card_hover)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # Top row: version badge + type tag
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        tag_text = {
            "release": "RELEASE",
            "snapshot": "SNAPSHOT",
            "old_alpha": "ALPHA",
            "old_beta": "BETA",
        }.get(self._version_type, "RELEASE")

        tag_color = {
            "release": C["accent_green"],
            "snapshot": C["accent_orange"],
            "old_alpha": C["accent_purple"],
            "old_beta": C["accent_blue"],
        }.get(self._version_type, C["accent_green"])

        tag = QLabel(tag_text, self)
        tag.setStyleSheet(f"""
            background-color: {tag_color}22;
            color: {tag_color};
            border: 1px solid {tag_color}55;
            border-radius: 4px;
            padding: 2px 8px;
            font-size: {FONT["xs"]};
            font-weight: 700;
            letter-spacing: 0.8px;
        """)
        top_row.addWidget(tag)

        if self._is_featured:
            featured_tag = QLabel("⭐ FEATURED", self)
            featured_tag.setStyleSheet(f"""
                background-color: {C["accent_cyan"]}22;
                color: {C["accent_cyan"]};
                border: 1px solid {C["accent_cyan"]}44;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: {FONT["xs"]};
                font-weight: 700;
                letter-spacing: 0.8px;
            """)
            top_row.addWidget(featured_tag)

        if self._is_installed:
            inst_tag = QLabel("✓ INSTALLED", self)
            inst_tag.setStyleSheet(f"""
                background-color: {C["accent_green"]}22;
                color: {C["accent_green"]};
                border: 1px solid {C["accent_green"]}44;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: {FONT["xs"]};
                font-weight: 700;
            """)
            top_row.addWidget(inst_tag)

        top_row.addStretch()
        layout.addLayout(top_row)

        # Version number — big and bold
        version_label = QLabel(self._version_id, self)
        version_label.setStyleSheet(f"""
            font-size: {FONT["xl"]};
            font-weight: 700;
            color: {C["text_primary"]};
            letter-spacing: -0.3px;
        """)
        layout.addWidget(version_label)

        # Subtitle
        subtitle_map = {
            "release": "Vanilla Minecraft · Official Release",
            "snapshot": "Development Snapshot · May contain bugs",
            "old_alpha": "Classic Era · Minecraft Alpha",
            "old_beta": "Classic Era · Minecraft Beta",
        }
        subtitle = QLabel(subtitle_map.get(self._version_type, "Vanilla Minecraft"), self)
        subtitle.setStyleSheet(f"color: {C['text_secondary']}; font-size: {FONT['sm']};")
        layout.addWidget(subtitle)

        layout.addSpacing(4)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        if self._is_installed:
            launch_btn = GhostButton("⚡ Quick Launch", accent=C["accent_cyan"], parent=self)
            launch_btn.setFixedHeight(36)
            launch_btn.clicked.connect(self._on_launch)
            btn_row.addWidget(launch_btn)

            manage_btn = GhostButton("Manage", accent=C["text_muted"], parent=self)
            manage_btn.setFixedHeight(36)
            btn_row.addWidget(manage_btn)
        else:
            install_btn = GhostButton("↓ Install", accent=C["accent_purple"], parent=self)
            install_btn.setFixedHeight(36)
            install_btn.clicked.connect(self._on_launch)
            btn_row.addWidget(install_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_launch(self) -> None:
        self.launch_requested.emit(self._version_id)

    # ------------------------------------------------------------------
    # Events / Paint
    # ------------------------------------------------------------------

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

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = 14
        t = self._hover_progress

        # Background
        base = QColor(C["bg_card"])
        hover = QColor(C["bg_card_hover"])
        bg = QColor(
            int(base.red() + (hover.red() - base.red()) * t),
            int(base.green() + (hover.green() - base.green()) * t),
            int(base.blue() + (hover.blue() - base.blue()) * t),
        )
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)
        painter.fillPath(path, bg)

        # Left accent stripe (visible on featured/hover)
        if self._is_featured or t > 0.05:
            accent_color = QColor(C["accent_cyan"] if self._is_featured else C["accent_purple"])
            accent_color.setAlpha(int((0.3 + t * 0.7) * 255))
            stripe_path = QPainterPath()
            stripe_path.addRoundedRect(0, 10, 3, h - 20, 1.5, 1.5)
            painter.fillPath(stripe_path, accent_color)

        # Top gradient
        if self._is_featured:
            top_grad = QLinearGradient(0, 0, w, 0)
            top_grad.setColorAt(0.0, QColor(0, 229, 255, int(t * 18)))
            top_grad.setColorAt(1.0, QColor(0, 229, 255, 0))
            painter.fillPath(path, top_grad)

        # Border
        border_alpha = int(40 + t * 120)
        border_color = QColor(C["accent_cyan"] if self._is_featured else C["border"])
        border_color.setAlpha(border_alpha)
        painter.setPen(border_color)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(0, 0, w - 1, h - 1, r, r)

        painter.end()
