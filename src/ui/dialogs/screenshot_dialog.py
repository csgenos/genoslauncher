"""Screenshot gallery — shows thumbnails from an instance's screenshots folder."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QObject, QThread, QUrl
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..styles import COLORS as C, FONT


THUMB_SIZE = 180
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_DIMENSION = 8192


class _ThumbLoader(QObject):
    loaded = Signal(str, QImage)
    finished = Signal()

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def run(self) -> None:
        try:
            path = Path(self._path)
            if path.stat().st_size > MAX_IMAGE_BYTES:
                return
            img = QImage(self._path)
            if not img.isNull() and img.width() <= MAX_IMAGE_DIMENSION and img.height() <= MAX_IMAGE_DIMENSION:
                img = img.scaled(THUMB_SIZE, THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.loaded.emit(self._path, img)
        finally:
            self.finished.emit()


class ScreenshotTile(QFrame):
    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self.setFixedSize(THUMB_SIZE + 8, THUMB_SIZE + 30)
        self.setObjectName("SSTile")
        self.setStyleSheet(f"""
            #SSTile {{
                background: {C["bg_primary"]};
                border: 1px solid {C["border"]};
                border-radius: 8px;
            }}
            #SSTile:hover {{ border-color: {C["border_strong"]}; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._img = QLabel()
        self._img.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self._img.setAlignment(Qt.AlignCenter)
        self._img.setStyleSheet(f"background: {C['bg_tertiary']}; border-radius: 4px;")
        self._img.setText("…")
        layout.addWidget(self._img)

        name = QLabel(path.name[:22])
        name.setAlignment(Qt.AlignCenter)
        name.setStyleSheet(f"font-size: {FONT['xs']}; color: {C['text_secondary']};")
        layout.addWidget(name)

    def set_pixmap(self, px: QPixmap) -> None:
        self._img.setPixmap(px)
        self._img.setText("")

    def mouseDoubleClickEvent(self, _event) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._path)))


class ScreenshotGalleryDialog(QDialog):
    def __init__(self, instance: dict, parent=None) -> None:
        super().__init__(parent)
        self._instance = instance
        self._screenshots_dir = Path(instance.get("directory", "")) / "screenshots"
        self._thumb_threads: list[QThread] = []
        self._thumb_workers: list[_ThumbLoader] = []
        self._tiles_by_path: dict[str, ScreenshotTile] = {}
        self.setWindowTitle(f"Screenshots — {instance.get('name', 'Instance')}")
        self.resize(860, 580)
        self._build_ui()
        self._load_screenshots()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        hdr = QHBoxLayout()
        title = QLabel("Screenshots")
        title.setStyleSheet(f"font-size: {FONT['lg']}; font-weight: 700; color: {C['text_primary']};")
        hdr.addWidget(title)
        hdr.addStretch()
        open_btn = QPushButton("Open Folder")
        open_btn.setFixedHeight(32)
        open_btn.clicked.connect(self._open_folder)
        hdr.addWidget(open_btn)
        layout.addLayout(hdr)

        self._status = QLabel("")
        self._status.setStyleSheet(f"font-size: {FONT['sm']}; color: {C['text_secondary']};")
        layout.addWidget(self._status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(10)
        self._grid.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._grid_widget)
        layout.addWidget(scroll, 1)

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)

    def _load_screenshots(self) -> None:
        if not self._screenshots_dir.exists():
            self._status.setText("No screenshots folder found. Take some screenshots in Minecraft first (F2).")
            return

        imgs = sorted(
            [f for f in self._screenshots_dir.iterdir()
             if f.suffix.lower() in (".png", ".jpg", ".jpeg")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:60]

        if not imgs:
            self._status.setText("No screenshots found in this instance.")
            return

        self._status.setText(f"{len(imgs)} screenshot(s) — double-click to open")
        cols = 4
        self._tiles: list[ScreenshotTile] = []
        for i, path in enumerate(imgs):
            tile = ScreenshotTile(path, self._grid_widget)
            self._grid.addWidget(tile, i // cols, i % cols)
            self._tiles.append(tile)
            self._tiles_by_path[str(path)] = tile
            self._load_thumb_async(tile, path)

    def _load_thumb_async(self, _tile: ScreenshotTile, path: Path) -> None:
        loader = _ThumbLoader(str(path))
        thread = QThread(self)
        loader.moveToThread(thread)
        thread.started.connect(loader.run)
        loader.loaded.connect(self._on_thumb_loaded)
        loader.finished.connect(thread.quit)
        loader.finished.connect(loader.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=loader: self._cleanup_thumb_worker(t, w))
        self._thumb_threads.append(thread)
        self._thumb_workers.append(loader)
        thread.start()

    def _on_thumb_loaded(self, path: str, image: QImage) -> None:
        tile = self._tiles_by_path.get(path)
        if tile is not None:
            tile.set_pixmap(QPixmap.fromImage(image))

    def _cleanup_thumb_worker(self, thread: QThread, worker: _ThumbLoader) -> None:
        if thread in self._thumb_threads:
            self._thumb_threads.remove(thread)
        if worker in self._thumb_workers:
            self._thumb_workers.remove(worker)

    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._screenshots_dir)))
