"""
GenosLauncher main window — light theme.

Frameless window with custom title bar, 200px sidebar, and stacked content area.
Routes sidebar navigation, orchestrates launch/install workers.
"""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizeGrip,
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
from .tabs.modpacks_tab import ModpacksTab
from .tabs.shaders_tab import ShadersTab
from .tabs.settings_tab import SettingsTab
from .tabs.accounts_tab import AccountsTab
from .tabs.servers_tab import ServersTab
from .login_dialog import LoginDialog
from .qt_dispatch import run_on_ui_thread
from ..core.auth import auth_manager
from ..core.config import config
from ..core.launcher import InstallWorker, LaunchWorker
from ..core.updater import check_async

_RESIZE_MARGIN = 6


class ContentArea(QWidget):
    """Right pane — stacked tabs on a light background."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ContentArea")
        self.setStyleSheet(f"#ContentArea {{ background-color: {C['bg_secondary']}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget(self)
        self.stack.setStyleSheet("background: transparent;")
        layout.addWidget(self.stack)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(C["bg_secondary"]))
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
        self._last_cursor_edge: str = ""   # O-X-008: only call setCursor on change

        self._setup_window()
        self._build_ui()
        self._connect_signals()
        self._load_auth()
        QTimer.singleShot(3000, self._check_for_update)

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle("GenosLauncher")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        w = config.get("window_width", 1280)
        h = config.get("window_height", 780)
        self.resize(w, h)
        self.setMinimumSize(960, 620)

        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - w) // 2, (screen.height() - h) // 2)
        self.setStyleSheet(get_stylesheet())

    # ------------------------------------------------------------------
    # UI
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

        # Update notification bar (hidden until an update is found)
        self._update_bar = self._build_update_bar()
        self._update_bar.setVisible(False)
        root_layout.addWidget(self._update_bar)

        # Body: sidebar | content
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._sidebar = Sidebar(root)
        body.addWidget(self._sidebar)

        self._content = ContentArea(root)
        body.addWidget(self._content, 1)

        root_layout.addLayout(body, 1)

        # Instantiate all tabs
        self._home_tab      = HomeTab()
        self._instances_tab = InstancesTab()
        self._mods_tab      = ModsTab()
        self._modpacks_tab  = ModpacksTab()
        self._shaders_tab   = ShadersTab()
        self._accounts_tab  = AccountsTab()
        self._settings_tab  = SettingsTab()
        self._servers_tab   = ServersTab()

        self._tabs: dict[str, QWidget] = {
            "home":      self._home_tab,
            "instances": self._instances_tab,
            "mods":      self._mods_tab,
            "modpacks":  self._modpacks_tab,
            "shaders":   self._shaders_tab,
            "servers":   self._servers_tab,
            "accounts":  self._accounts_tab,
            "settings":  self._settings_tab,
        }

        for tab in self._tabs.values():
            tab.setVisible(True)
            tab.setGraphicsEffect(None)
            self._content.stack.addWidget(tab)

        self._switch_tab("home")

        # Resize grip
        grip = QSizeGrip(root)
        grip.setStyleSheet("background: transparent;")
        root_layout.addWidget(grip, 0, Qt.AlignBottom | Qt.AlignRight)

    def _build_update_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(38)
        bar.setStyleSheet(f"""
            background: {C["accent_blue_soft"]};
            border-bottom: 1px solid {C["border_focus"]};
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 12, 0)
        layout.setSpacing(10)

        self._update_label = QLabel()
        self._update_label.setStyleSheet(f"font-size: 12px; color: {C['text_primary']}; font-weight: 600;")
        layout.addWidget(self._update_label)

        self._update_url = ""
        dl_btn = QPushButton("Download")
        dl_btn.setFixedSize(90, 26)
        dl_btn.setCursor(Qt.PointingHandCursor)
        dl_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C["accent"]};
                color: {C["text_inverse"]};
                border: none;
                border-radius: 5px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton:hover {{ background: #1F2937; }}
        """)
        dl_btn.clicked.connect(lambda: webbrowser.open(self._update_url) if self._update_url else None)
        layout.addWidget(dl_btn)

        dismiss = QPushButton("✕")
        dismiss.setFixedSize(26, 26)
        dismiss.setCursor(Qt.PointingHandCursor)
        dismiss.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C["text_secondary"]};
                border: none;
                font-size: 13px;
            }}
            QPushButton:hover {{ color: {C["text_primary"]}; }}
        """)
        dismiss.clicked.connect(lambda: self._update_bar.setVisible(False))
        layout.addWidget(dismiss)

        return bar

    def _check_for_update(self) -> None:
        def _on_result(result):
            if result:
                run_on_ui_thread(lambda: self._show_update_bar(result))
        check_async(_on_result)

    def _show_update_bar(self, result: dict) -> None:
        self._update_url = result.get("url", "")
        self._update_label.setText(
            f"⬆  GenosLauncher {result['version']} is available"
        )
        self._update_bar.setVisible(True)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._sidebar.tab_changed.connect(self._switch_tab)
        self._sidebar.login_requested.connect(self._open_login_dialog)
        self._sidebar.logout_requested.connect(self._logout)
        self._home_tab.launch_requested.connect(self._on_launch_requested)
        self._home_tab.install_requested.connect(self._on_install_requested)
        self._home_tab.view_all_requested.connect(lambda: self._switch_tab("instances"))
        self._instances_tab.launch_requested.connect(self._on_launch_requested)
        self._instances_tab.instance_launch_requested.connect(self._on_instance_launch_requested)
        self._instances_tab.install_requested.connect(self._on_install_requested)
        self._servers_tab.server_launch_requested.connect(self._on_server_launch_requested)

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _load_auth(self) -> None:
        """Restore saved session and refresh token silently."""
        if auth_manager.load_stored():
            self._update_sidebar_account()
            auth_manager.refresh_async()

    def _open_login_dialog(self) -> None:
        dlg = LoginDialog(self)
        dlg.login_succeeded.connect(self._on_login_success)
        dlg.exec()

    def _on_login_success(self, account: dict) -> None:
        config.update({"last_account": account.get("name", "")})
        self._update_sidebar_account()
        self._accounts_tab._refresh_state()

    def _logout(self) -> None:
        auth_manager.logout()
        config.update({"last_account": ""})
        self._update_sidebar_account()
        self._accounts_tab._refresh_state()

    def _update_sidebar_account(self) -> None:
        if auth_manager.is_logged_in:
            self._sidebar.account_widget.set_logged_in(
                auth_manager.username, "Microsoft · Online"
            )
        else:
            self._sidebar.account_widget.set_logged_out()

    # ------------------------------------------------------------------
    # Tab switching (200ms fade-in)
    # ------------------------------------------------------------------

    def _switch_tab(self, key: str) -> None:
        widget = self._tabs.get(key)
        if widget is None or widget is self._content.stack.currentWidget():
            return

        self._content.stack.setCurrentWidget(widget)

        widget.setVisible(True)
        widget.setGraphicsEffect(None)
        if key == "mods":
            self._mods_tab.refresh_instances()
        elif key == "shaders":
            self._shaders_tab._reload_instances()
        widget.update()

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    def _on_launch_requested(self, version_id: str) -> None:
        self._start_launch(version_id, "")

    def _on_instance_launch_requested(self, version_id: str, instance_id: str) -> None:
        self._start_launch(version_id, instance_id)

    def _on_server_launch_requested(self, version_id: str, instance_id: str, server_ip: str, server_port: str) -> None:
        self._start_launch(version_id, instance_id, server_ip=server_ip, server_port=server_port)

    def _start_launch(self, version_id: str, instance_id: str, server_ip: str = "", server_port: str = "") -> None:
        if self._launch_worker is not None:
            return

        self._home_tab.set_launch_state(True)
        self._home_tab.update_progress(0, 100, f"Preparing {version_id}…")

        if auth_manager.is_logged_in:
            username = auth_manager.username
        else:
            username = config.get("last_account") or "Player"
        self._launch_worker = LaunchWorker(
            version_id, username, self,
            instance_id=instance_id,
            server_ip=server_ip,
            server_port=server_port,
        )
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

    def _on_process_ended(self, _exit_code: int) -> None:
        self._launch_worker = None
        self._home_tab.set_launch_state(False)
        if self.isHidden():
            self.show()

    def _on_launch_error(self, message: str) -> None:
        self._launch_worker = None
        self._home_tab.set_launch_state(False)
        self._home_tab.update_progress(0, 100, "Launch failed.")
        QMessageBox.critical(self, "Launch Error", f"Failed to start Minecraft:\n\n{message}")

    def _on_install_requested(self, version_id: str) -> None:
        if self._install_worker is not None:
            return
        self._home_tab.set_launch_state(True)
        self._home_tab.update_progress(0, 100, f"Installing {version_id}...")
        self._install_worker = InstallWorker(version_id, self)
        self._install_worker.progress_changed.connect(self._home_tab.update_progress)
        self._install_worker.finished.connect(self._on_install_finished)
        self._install_worker.start()

    def _on_install_finished(self, ok: bool, message: str) -> None:
        self._install_worker = None
        self._home_tab.set_launch_state(False)
        if ok:
            self._home_tab.update_progress(100, 100, message)
            self._instances_tab._load_versions()
            self._instances_tab._render_instances()
        else:
            QMessageBox.critical(self, "Install Error", message)

    # ------------------------------------------------------------------
    # Frameless resize (edge detection + drag)
    # ------------------------------------------------------------------

    def _edge_at(self, pos) -> str:
        m = _RESIZE_MARGIN
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        on_l, on_r = x <= m, x >= w - m
        on_t, on_b = y <= m, y >= h - m
        if on_l and on_t: return "tl"
        if on_r and on_t: return "tr"
        if on_l and on_b: return "bl"
        if on_r and on_b: return "br"
        if on_l: return "l"
        if on_r: return "r"
        if on_b: return "b"
        if on_t: return "t"
        return ""

    _CURSORS = {
        "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
        "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
        "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
        "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
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
            if "r" in edge: geom.setRight(geom.right() + dx)
            if "b" in edge: geom.setBottom(geom.bottom() + dy)
            if "l" in edge:
                nl = geom.left() + dx
                if geom.right() - nl >= min_w: geom.setLeft(nl)
            if "t" in edge:
                nt = geom.top() + dy
                if geom.bottom() - nt >= min_h: geom.setTop(nt)
            if geom.width() >= min_w and geom.height() >= min_h:
                self.setGeometry(geom)
        else:
            edge = self._edge_at(event.pos())
            if edge != self._last_cursor_edge:
                self._last_cursor_edge = edge
                self.setCursor(self._CURSORS.get(edge, Qt.ArrowCursor))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._resize_edge = ""
        self._drag_start_pos = None
        self._drag_start_geom = None
        self._last_cursor_edge = ""
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Close — persist size
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        config.update({"window_width": self.width(), "window_height": self.height()})
        if self._launch_worker:
            box = QMessageBox(self)
            box.setWindowTitle("Minecraft is running")
            box.setText("Minecraft is still running. What would you like to do?")
            leave_running = box.addButton("Close Launcher", QMessageBox.AcceptRole)
            stop_game = box.addButton("Stop Minecraft", QMessageBox.DestructiveRole)
            cancel = box.addButton("Cancel", QMessageBox.RejectRole)
            box.setDefaultButton(leave_running)
            box.exec()
            clicked = box.clickedButton()
            if clicked == cancel:
                event.ignore()
                return
            if clicked == stop_game:
                if not self._launch_worker.terminate():
                    QMessageBox.warning(
                        self,
                        "Minecraft is still running",
                        "GenosLauncher could not stop Minecraft. It may still be running.",
                    )
        super().closeEvent(event)
