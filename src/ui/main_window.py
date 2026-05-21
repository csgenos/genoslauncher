"""
GenosLauncher main window.

Frameless, custom-titled, sidebar + stacked content area.
Handles tab navigation, launch orchestration, and window resize/drag.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QRect
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizeGrip,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .styles import COLORS as C, get_stylesheet
from .titlebar import TitleBar
from .components.sidebar import Sidebar
from .tabs.home_tab import HomeTab
from .tabs.instances_tab import InstancesTab
from .tabs.mods_tab import ModsTab
from .tabs.accounts_tab import AccountsTab
from .tabs.settings_tab import SettingsTab
from ..core.config import config
from ..core.launcher import LaunchWorker, InstallWorker

_RESIZE_MARGIN = 6  # px — drag-to-resize border thickness


class ContentArea(QWidget):
    """The right-hand pane that holds all tabs in a QStackedWidget."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ContentArea")
        self.setStyleSheet(f"#ContentArea {{ background-color: {C['bg_primary']}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget(self)
        self.stack.setStyleSheet("background: transparent;")
        layout.addWidget(self.stack)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(C["bg_primary"]))
        grad.setColorAt(1.0, QColor(C["bg_deep"]))
        painter.fillRect(self.rect(), grad)
        painter.end()


class MainWindow(QMainWindow):
    """Root application window."""

    def __init__(self) -> None:
        super().__init__()
        self._launch_worker: LaunchWorker | None = None
        self._install_worker: InstallWorker | None = None
        self._resize_edge: str = ""
        self._drag_start_pos = None
        self._drag_start_geom: QRect | None = None

        self._setup_window()
        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle("GenosLauncher")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        w = config.get("window_width", 1280)
        h = config.get("window_height", 760)
        self.resize(w, h)
        self.setMinimumSize(900, 600)

        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - w) // 2,
            (screen.height() - h) // 2,
        )

        # Apply global stylesheet
        self.setStyleSheet(get_stylesheet())

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("RootWidget")
        root.setStyleSheet(f"#RootWidget {{ background-color: {C['bg_primary']}; }}")
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Title bar
        self._title_bar = TitleBar(root)
        root_layout.addWidget(self._title_bar)

        # Main body: sidebar + content
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._sidebar = Sidebar(root)
        body.addWidget(self._sidebar)

        self._content = ContentArea(root)
        body.addWidget(self._content, 1)

        root_layout.addLayout(body, 1)

        # Build all tabs
        self._home_tab = HomeTab()
        self._instances_tab = InstancesTab()
        self._mods_tab = ModsTab()
        self._accounts_tab = AccountsTab()
        self._settings_tab = SettingsTab()

        self._tabs: dict[str, QWidget] = {
            "home":      self._home_tab,
            "instances": self._instances_tab,
            "mods":      self._mods_tab,
            "accounts":  self._accounts_tab,
            "settings":  self._settings_tab,
        }

        for tab in self._tabs.values():
            self._content.stack.addWidget(tab)

        # Show home by default
        self._switch_tab("home")

        # Resize grip (bottom-right corner)
        grip = QSizeGrip(root)
        grip.setStyleSheet("background: transparent;")
        root_layout.addWidget(grip, 0, Qt.AlignBottom | Qt.AlignRight)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._sidebar.tab_changed.connect(self._switch_tab)
        self._home_tab.launch_requested.connect(self._on_launch_requested)
        self._instances_tab.launch_requested.connect(self._on_launch_requested)

    # ------------------------------------------------------------------
    # Tab switching with fade
    # ------------------------------------------------------------------

    def _switch_tab(self, key: str) -> None:
        widget = self._tabs.get(key)
        if widget is None:
            return

        current = self._content.stack.currentWidget()
        if current is widget:
            return

        self._content.stack.setCurrentWidget(widget)

        # Fade-in via opacity effect
        effect = widget.graphicsEffect()
        if effect is None:
            from PySide6.QtWidgets import QGraphicsOpacityEffect
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    # ------------------------------------------------------------------
    # Launch orchestration
    # ------------------------------------------------------------------

    def _on_launch_requested(self, version_id: str) -> None:
        if self._launch_worker is not None:
            return

        self._home_tab.set_launch_state(True)
        self._home_tab.update_progress(0, 100, f"Launching {version_id}...")

        # Use offline "Player" unless an account is configured
        username = config.get("last_account") or "Player"

        self._launch_worker = LaunchWorker(version_id, username, self)
        self._launch_worker.status_changed.connect(self._on_launch_status)
        self._launch_worker.process_started.connect(self._on_process_started)
        self._launch_worker.process_ended.connect(self._on_process_ended)
        self._launch_worker.error.connect(self._on_launch_error)
        self._launch_worker.start()

    def _on_launch_status(self, status: str) -> None:
        self._home_tab.update_progress(0, 100, status)

    def _on_process_started(self) -> None:
        self._home_tab.update_progress(100, 100, "Minecraft is running!")
        if config.get("close_on_launch", False):
            self.hide()

    def _on_process_ended(self, exit_code: int) -> None:
        self._launch_worker = None
        self._home_tab.set_launch_state(False)
        if self.isHidden():
            self.show()

    def _on_launch_error(self, message: str) -> None:
        self._launch_worker = None
        self._home_tab.set_launch_state(False)
        self._home_tab.update_progress(0, 100, "Launch failed.")
        QMessageBox.critical(
            self,
            "Launch Error",
            f"Failed to start Minecraft:\n\n{message}",
        )

    # ------------------------------------------------------------------
    # Frameless resize via mouse events
    # ------------------------------------------------------------------

    def _edge_at(self, pos) -> str:
        m = _RESIZE_MARGIN
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        on_left = x <= m
        on_right = x >= w - m
        on_top = y <= m
        on_bottom = y >= h - m
        if on_left and on_top:
            return "tl"
        if on_right and on_top:
            return "tr"
        if on_left and on_bottom:
            return "bl"
        if on_right and on_bottom:
            return "br"
        if on_left:
            return "l"
        if on_right:
            return "r"
        if on_bottom:
            return "b"
        if on_top:
            return "t"
        return ""

    _CURSORS = {
        "l":  Qt.SizeHorCursor,
        "r":  Qt.SizeHorCursor,
        "t":  Qt.SizeVerCursor,
        "b":  Qt.SizeVerCursor,
        "tl": Qt.SizeFDiagCursor,
        "br": Qt.SizeFDiagCursor,
        "tr": Qt.SizeBDiagCursor,
        "bl": Qt.SizeBDiagCursor,
    }

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            edge = self._edge_at(event.pos())
            if edge:
                self._resize_edge = edge
                self._drag_start_pos = event.globalPosition().toPoint()
                self._drag_start_geom = self.geometry()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._resize_edge and self._drag_start_pos and self._drag_start_geom:
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            geom = QRect(self._drag_start_geom)
            dx, dy = delta.x(), delta.y()
            edge = self._resize_edge
            min_w, min_h = self.minimumWidth(), self.minimumHeight()

            if "r" in edge:
                geom.setRight(geom.right() + dx)
            if "b" in edge:
                geom.setBottom(geom.bottom() + dy)
            if "l" in edge:
                new_left = geom.left() + dx
                if geom.right() - new_left >= min_w:
                    geom.setLeft(new_left)
            if "t" in edge:
                new_top = geom.top() + dy
                if geom.bottom() - new_top >= min_h:
                    geom.setTop(new_top)

            if geom.width() >= min_w and geom.height() >= min_h:
                self.setGeometry(geom)
        else:
            edge = self._edge_at(event.pos())
            cursor = self._CURSORS.get(edge, Qt.ArrowCursor)
            self.setCursor(cursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._resize_edge = ""
        self._drag_start_pos = None
        self._drag_start_geom = None
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Close — persist window size
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        config.update({
            "window_width": self.width(),
            "window_height": self.height(),
        })
        if self._launch_worker:
            self._launch_worker.terminate()
        super().closeEvent(event)
