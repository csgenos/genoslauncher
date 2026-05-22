"""Qt main-thread dispatch helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)


class _Dispatcher(QObject):
    dispatch = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.dispatch.connect(self._run, Qt.QueuedConnection)

    @Slot(object)
    def _run(self, callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            log.exception("Unhandled exception in Qt dispatcher callback")


_dispatcher: _Dispatcher | None = None


def init_dispatcher() -> _Dispatcher:
    """Create the process-wide dispatcher on the Qt application thread."""
    global _dispatcher
    if _dispatcher is None:
        app = QApplication.instance()
        _dispatcher = _Dispatcher()
        if app is not None:
            _dispatcher.moveToThread(app.thread())
    return _dispatcher


def run_on_ui_thread(callback: Callable[[], None]) -> None:
    """Schedule callback to run on the Qt application thread."""
    init_dispatcher().dispatch.emit(callback)
