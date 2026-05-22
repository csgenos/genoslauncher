"""Java Manager dialog — browse detected installations and download Eclipse Temurin JDKs."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT
from ...core import java_manager as jm
from ...core.config import config

_XS = FONT["xs"]
_SM = FONT["sm"]
_MD = FONT["md"]
_XL = FONT["xl"]


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

class _ReleaseCheckWorker(QObject):
    done = Signal(int, list)

    def __init__(self, major: int) -> None:
        super().__init__()
        self._major = major

    def run(self) -> None:
        releases = jm.list_adoptium_releases(self._major)
        self.done.emit(self._major, releases)


class _DownloadWorker(QObject):
    status   = Signal(str)
    progress = Signal(int, int)
    finished = Signal(bool, str, int)

    def __init__(self, major: int) -> None:
        super().__init__()
        self._major = major

    def run(self) -> None:
        result = jm.download_java(
            self._major,
            on_progress=lambda d, t: self.progress.emit(d, t),
            on_status=lambda s: self.status.emit(s),
        )
        if result:
            self.finished.emit(True, result, self._major)
        else:
            self.finished.emit(False, "Download or extraction failed.", self._major)


# ---------------------------------------------------------------------------
# Row widgets
# ---------------------------------------------------------------------------

class _InstalledRow(QFrame):
    use_requested    = Signal(str)
    remove_requested = Signal(int)

    def __init__(self, info: dict, parent=None) -> None:
        super().__init__(parent)
        self._info = info
        self.setObjectName("JRow")
        self.setFixedHeight(54)
        self.setStyleSheet(
            "#JRow { background: " + C["bg_primary"] + "; border: 1px solid " +
            C["border"] + "; border-radius: 8px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        badge = QLabel(f"Java {info['major']}")
        badge.setStyleSheet(
            "background: " + C["accent_blue_soft"] + "; color: " + C["accent_blue"] +
            "; border-radius: 5px; padding: 2px 8px; font-size: " + _XS + "; font-weight: 700;"
        )
        layout.addWidget(badge)

        path_lbl = QLabel(info["path"])
        path_lbl.setStyleSheet("font-size: " + _XS + "; color: " + C["text_secondary"] + ";")
        path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(path_lbl, 1)

        active = config.get("java_path", "") == info["path"]
        use_btn = QPushButton("Active" if active else "Use")
        use_btn.setFixedSize(60, 28)
        use_btn.setEnabled(not active)
        use_btn.setCursor(Qt.PointingHandCursor)
        bg = C["accent_blue"] if active else C["bg_tertiary"]
        fg = C["text_inverse"] if active else C["text_primary"]
        use_btn.setStyleSheet(
            "QPushButton { background: " + bg + "; color: " + fg +
            "; border: none; border-radius: 5px; font-size: " + _XS + "; font-weight: 600; }"
            "QPushButton:hover:!disabled { background: " + C["accent_blue"] + "; color: " + C["text_inverse"] + "; }"
        )
        use_btn.clicked.connect(lambda: self.use_requested.emit(info["path"]))
        layout.addWidget(use_btn)

        major = info["major"]
        if (jm.JAVA_INSTALLS_DIR / str(major)).exists():
            rm_btn = QPushButton("Remove")
            rm_btn.setFixedSize(68, 28)
            rm_btn.setCursor(Qt.PointingHandCursor)
            rm_btn.setStyleSheet(
                "QPushButton { background: transparent; color: " + C["danger"] +
                "; border: 1px solid " + C["danger"] + "; border-radius: 5px; font-size: " + _XS + "; }"
                "QPushButton:hover { background: " + C["danger"] + "; color: " + C["text_inverse"] + "; }"
            )
            rm_btn.clicked.connect(lambda: self.remove_requested.emit(major))
            layout.addWidget(rm_btn)


class _DownloadRow(QFrame):
    download_requested = Signal(int)

    def __init__(self, major: int, release: dict | None, parent=None) -> None:
        super().__init__(parent)
        self._major = major
        self.setObjectName("JRow")
        self.setFixedHeight(54)
        self.setStyleSheet(
            "#JRow { background: " + C["bg_primary"] + "; border: 1px solid " +
            C["border"] + "; border-radius: 8px; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        badge = QLabel(f"Java {major}")
        badge.setStyleSheet(
            "background: " + C["bg_tertiary"] + "; color: " + C["text_secondary"] +
            "; border-radius: 5px; padding: 2px 8px; font-size: " + _XS + "; font-weight: 700;"
        )
        layout.addWidget(badge)

        if release:
            v = release.get("version", {})
            size = release.get("binary", {}).get("package", {}).get("size", 0)
            size_str = f"  ·  {size // (1024 * 1024)} MB" if size else ""
            info_text = f"Eclipse Temurin JDK {major}{size_str}"
        else:
            info_text = "Checking availability…"
        info_lbl = QLabel(info_text)
        info_lbl.setStyleSheet("font-size: " + _XS + "; color: " + C["text_secondary"] + ";")
        layout.addWidget(info_lbl, 1)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(6)
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar { background: " + C["bg_tertiary"] + "; border-radius: 3px; border: none; }"
            "QProgressBar::chunk { background: " + C["accent_blue"] + "; border-radius: 3px; }"
        )
        layout.addWidget(self._progress, 1)

        self._btn = QPushButton("Download")
        self._btn.setFixedSize(84, 28)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setEnabled(release is not None)
        self._btn.setStyleSheet(
            "QPushButton { background: " + C["accent_blue"] + "; color: " + C["text_inverse"] +
            "; border: none; border-radius: 5px; font-size: " + _XS + "; font-weight: 700; }"
            "QPushButton:hover { background: " + C["accent"] + "; }"
            "QPushButton:disabled { background: " + C["bg_tertiary"] + "; color: " + C["text_disabled"] + "; }"
        )
        self._btn.clicked.connect(lambda: self.download_requested.emit(self._major))
        layout.addWidget(self._btn)

    def set_downloading(self, done: int, total: int) -> None:
        self._btn.setEnabled(False)
        self._btn.setText("…")
        self._progress.setVisible(True)
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(done)
        else:
            self._progress.setRange(0, 0)

    def set_done(self) -> None:
        self._btn.setText("Done")
        self._btn.setEnabled(False)
        self._progress.setVisible(False)

    def set_error(self) -> None:
        self._btn.setText("Retry")
        self._btn.setEnabled(True)
        self._progress.setVisible(False)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class JavaManagerDialog(QDialog):
    """Browse detected Java installations and download new ones via Adoptium."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Java Manager")
        self.setMinimumSize(660, 480)
        self.setModal(True)
        self.setStyleSheet("background: " + C["bg_secondary"] + ";")
        self._threads: list[QThread] = []
        self._workers: list[QObject] = []
        self._download_rows: dict[int, _DownloadRow] = {}
        self._build_ui()
        self._populate_installed()
        self._fetch_releases()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        title = QLabel("Java Manager")
        title.setStyleSheet(
            "font-size: " + _XL + "; font-weight: 800; color: " + C["text_primary"] + ";"
        )
        root.addWidget(title)

        sub = QLabel(
            "Manage Java used by GenosLauncher. "
            "Downloads are Eclipse Temurin JDK from Adoptium."
        )
        sub.setStyleSheet("font-size: " + _XS + "; color: " + C["text_secondary"] + ";")
        sub.setWordWrap(True)
        root.addWidget(sub)

        installed_lbl = QLabel("Detected Installations")
        installed_lbl.setStyleSheet(
            "font-size: " + _MD + "; font-weight: 700; color: " + C["text_primary"] +
            "; margin-top: 4px;"
        )
        root.addWidget(installed_lbl)

        installed_wrap = QWidget()
        installed_wrap.setStyleSheet("background: transparent;")
        self._installed_area = QVBoxLayout(installed_wrap)
        self._installed_area.setContentsMargins(0, 0, 0, 0)
        self._installed_area.setSpacing(6)
        root.addWidget(installed_wrap)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: " + C["border"] + "; border: none;")
        root.addWidget(sep)

        dl_lbl = QLabel("Download Eclipse Temurin JDK")
        dl_lbl.setStyleSheet(
            "font-size: " + _MD + "; font-weight: 700; color: " + C["text_primary"] + ";"
        )
        root.addWidget(dl_lbl)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            "font-size: " + _XS + "; color: " + C["text_secondary"] + ";"
        )
        root.addWidget(self._status_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        dl_content = QWidget()
        dl_content.setStyleSheet("background: transparent;")
        self._dl_area = QVBoxLayout(dl_content)
        self._dl_area.setContentsMargins(0, 0, 0, 0)
        self._dl_area.setSpacing(6)
        self._dl_area.addStretch()
        scroll.setWidget(dl_content)
        root.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedSize(80, 32)
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(
            "QPushButton { background: " + C["bg_tertiary"] + "; color: " + C["text_primary"] +
            "; border: 1px solid " + C["border"] + "; border-radius: 6px; font-size: " + _SM + "; }"
            "QPushButton:hover { border-color: " + C["border_strong"] + "; }"
        )
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

    def _populate_installed(self) -> None:
        while self._installed_area.count():
            item = self._installed_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        installs = jm.find_java_installations(force_refresh=True)
        if not installs:
            lbl = QLabel("No Java installations detected.")
            lbl.setStyleSheet(
                "font-size: " + _SM + "; color: " + C["text_tertiary"] + ";"
            )
            self._installed_area.addWidget(lbl)
            return

        for info in installs:
            row = _InstalledRow(info, self)
            row.use_requested.connect(self._on_use)
            row.remove_requested.connect(self._on_remove)
            self._installed_area.addWidget(row)

    def _fetch_releases(self) -> None:
        for major in jm._JAVA_MAJOR_VERSIONS:
            row = _DownloadRow(major, None, self)
            row.download_requested.connect(self._start_download)
            self._download_rows[major] = row
            self._dl_area.insertWidget(self._dl_area.count() - 1, row)

            thread = QThread(self)
            worker = _ReleaseCheckWorker(major)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.done.connect(lambda m, rels: self._on_releases(m, rels))
            worker.done.connect(thread.quit)
            self._threads.append(thread)
            self._workers.append(worker)
            thread.finished.connect(
                lambda t=thread: self._threads.remove(t) if t in self._threads else None
            )
            thread.finished.connect(
                lambda w=worker: self._workers.remove(w) if w in self._workers else None
            )
            thread.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.start()

    def _on_releases(self, major: int, releases: list) -> None:
        old_row = self._download_rows.get(major)
        if not old_row:
            return
        idx = self._dl_area.indexOf(old_row)
        if idx < 0:
            return
        release = releases[0] if releases else None
        new_row = _DownloadRow(major, release, self)
        new_row.download_requested.connect(self._start_download)
        self._download_rows[major] = new_row
        self._dl_area.insertWidget(idx, new_row)
        old_row.deleteLater()

    def _start_download(self, major: int) -> None:
        row = self._download_rows.get(major)
        if row:
            row.set_downloading(0, 0)
        self._status_lbl.setText(f"Downloading Java {major}…")

        thread = QThread(self)
        worker = _DownloadWorker(major)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.status.connect(self._status_lbl.setText)
        worker.progress.connect(lambda d, t, mj=major: self._on_dl_progress(mj, d, t))
        worker.finished.connect(lambda ok, msg, mj=major: self._on_dl_done(mj, ok, msg))
        worker.finished.connect(thread.quit)
        self._threads.append(thread)
        self._workers.append(worker)
        thread.finished.connect(
            lambda t=thread: self._threads.remove(t) if t in self._threads else None
        )
        thread.finished.connect(
            lambda w=worker: self._workers.remove(w) if w in self._workers else None
        )
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_dl_progress(self, major: int, done: int, total: int) -> None:
        row = self._download_rows.get(major)
        if row:
            row.set_downloading(done, total)

    def _on_dl_done(self, major: int, ok: bool, msg: str) -> None:
        row = self._download_rows.get(major)
        if row:
            if ok:
                row.set_done()
            else:
                row.set_error()
        if ok:
            self._status_lbl.setText(f"Java {major} installed.")
            self._populate_installed()
        else:
            self._status_lbl.setText(msg)

    def _on_use(self, path: str) -> None:
        config.set("java_path", path)
        self._populate_installed()
        self._status_lbl.setText(f"Active Java: {path}")

    def _on_remove(self, major: int) -> None:
        jm.remove_java_installation(major)
        self._populate_installed()
        self._status_lbl.setText(f"Removed managed Java {major}.")
