"""Logging to a file per user, and a friendly dialog instead of a crash.

Log folder:
  macOS    ~/Library/Logs/Clipbook/
  Windows  %LOCALAPPDATA%/Clipbook/Logs/
  other    ~/.local/state/Clipbook/
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import sys
import threading
import traceback
from pathlib import Path

from . import APP_NAME, __version__

log = logging.getLogger("clipbook")


def log_dir() -> Path:
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Logs" / APP_NAME
    elif sys.platform == "win32":
        d = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME / "Logs"
    else:
        d = Path.home() / ".local" / "state" / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup() -> Path:
    path = log_dir() / "app.log"
    root = logging.getLogger()
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        fh = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(fh)
        root.setLevel(logging.INFO)
    log.info("start %s %s · %s %s · Python %s · frozen=%s", APP_NAME, __version__, platform.system(),
             platform.machine(), platform.python_version(), getattr(sys, "frozen", False))
    return path


def install_qt_handlers() -> None:
    """Qt warnings go to the log file instead of the terminal; crashes show a dialog."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    def qt_handler(mode, context, message):
        level = {QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.INFO,
                 QtMsgType.QtWarningMsg: logging.DEBUG}.get(mode, logging.WARNING)
        logging.getLogger("qt").log(level, message)

    qInstallMessageHandler(qt_handler)

    def show_error(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("unerwarteter Fehler\n%s", text)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is None:
                return
            box = QMessageBox(QMessageBox.Icon.Warning, "Unerwarteter Fehler",
                              "Etwas ist schiefgelaufen. Ihre Arbeit ist gespeichert.\n\n"
                              f"{exc_type.__name__}: {exc}")
            box.setDetailedText(text)
            box.setInformativeText(f"Details stehen im Protokoll:\n{log_dir()}")
            open_btn = box.addButton("Protokollordner öffnen", QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Ok)
            box.exec()
            if box.clickedButton() is open_btn:
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir())))
        except Exception:  # never let the error handler itself crash
            pass

    sys.excepthook = show_error
    threading.excepthook = lambda args: log.error(
        "Fehler im Hintergrund\n%s", "".join(traceback.format_exception(args.exc_type, args.exc_value,
                                                                        args.exc_traceback)))
