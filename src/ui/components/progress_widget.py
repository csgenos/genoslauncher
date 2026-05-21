"""
Clean progress widgets for GenosLauncher — light / white theme.

CleanProgressBar   — 6px tall bar, light gray track, navy fill, animated
LaunchProgressPanel — status label + bar + percentage, hidden by default
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..styles import COLORS as C, FONT


class CleanProgressBar(QWidget):
    """
    A 6px tall progress bar.
    Track: #E5E7EB (light gray).
    Fill:  #111827 (navy accent).
    Rounded ends. Animated fill via QPropertyAnimation on progress_val.
    No shimmer, no gradient — purely clean.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(6)
        self._value: float = 0.0

        self._anim = QPropertyAnimation(self, b"progress_val", self)
        self._anim.setDuration(400)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # --- Qt property -------------------------------------------------------

    def _get_val(self) -> float:
        return self._value

    def _set_val(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self.update()

    progress_val = Property(float, _get_val, _set_val)

    # --- Public API --------------------------------------------------------

    def set_progress(self, value: float) -> None:
        """Animate progress to value (0.0 to 1.0)."""
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(max(0.0, min(1.0, value)))
        self._anim.start()

    def reset(self) -> None:
        """Instantly reset to zero."""
        self._anim.stop()
        self._value = 0.0
        self.update()

    # --- Paint -------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = h / 2.0

        # Track
        track = QPainterPath()
        track.addRoundedRect(0, 0, w, h, r, r)
        painter.fillPath(track, QColor(C['border']))

        # Fill
        if self._value > 0.0:
            fill_w = max(r * 2, w * self._value)
            fill = QPainterPath()
            fill.addRoundedRect(0, 0, fill_w, h, r, r)
            painter.fillPath(fill, QColor(C['accent']))

        painter.end()


class LaunchProgressPanel(QWidget):
    """
    Progress panel shown during launch sequence.

    Layout (top to bottom):
      - Status label       (gray 12px, left-aligned)
      - CleanProgressBar   (6px)
      - Percentage label   (blue 11px bold, right-aligned)

    Hidden by default. Use show_panel() / hide_panel() to toggle.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(6)

        # Top row: status + percentage
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(0)

        self._status_label = QLabel("Preparing...", self)
        self._status_label.setStyleSheet(
            f"color: {C['text_secondary']}; font-size: {FONT['sm']};"
        )
        top_row.addWidget(self._status_label)
        top_row.addStretch()

        self._pct_label = QLabel("0%", self)
        self._pct_label.setStyleSheet(
            f"color: {C['accent_blue']}; font-size: {FONT['xs']}; font-weight: 700;"
        )
        self._pct_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top_row.addWidget(self._pct_label)

        layout.addLayout(top_row)

        # Progress bar
        self._bar = CleanProgressBar(self)
        layout.addWidget(self._bar)

    # --- Public API --------------------------------------------------------

    def set_status(self, text: str) -> None:
        """Update the status description text."""
        self._status_label.setText(text)

    def set_progress(self, current: int, maximum: int) -> None:
        """Update progress from integer current/maximum values."""
        if maximum <= 0:
            return
        pct = current / maximum
        self._bar.set_progress(pct)
        self._pct_label.setText(f"{int(pct * 100)}%")

    def show_panel(self) -> None:
        """Make the panel visible and reset to zero."""
        self._bar.reset()
        self._pct_label.setText("0%")
        self._status_label.setText("Preparing...")
        self.setVisible(True)

    def hide_panel(self) -> None:
        """Hide the panel."""
        self.setVisible(False)
