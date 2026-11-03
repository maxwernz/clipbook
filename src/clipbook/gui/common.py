"""Small shared GUI helpers."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QStyle

MODULE_MIME = "application/x-clipbook-module"

OLD_SETTINGS_NAME = "ManualBuilder"   # name before the rename to Clipbook


def app_settings() -> QSettings:
    """The app's settings. Tests set CLIPBOOK_SETTINGS so they never touch the user's.
    Settings saved under the old app name are copied over once."""
    name = os.environ.get("CLIPBOOK_SETTINGS", "Clipbook")
    s = QSettings("ProfilClip", name)
    s.setFallbacksEnabled(False)          # macOS would otherwise list system-wide keys too
    if name == "Clipbook" and not s.allKeys():
        old = QSettings("ProfilClip", OLD_SETTINGS_NAME)
        old.setFallbacksEnabled(False)
        for key in old.allKeys():
            s.setValue(key, old.value(key))
        s.sync()
    return s

LANGUAGE_NAMES = {"de": "Deutsch", "en": "Englisch", "it": "Italienisch", "fr": "Französisch",
                  "es": "Spanisch", "nl": "Niederländisch", "pl": "Polnisch"}


def lang_name(code: str) -> str:
    return f"{LANGUAGE_NAMES.get(code, code)} ({code})"


def open_path(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def std_icon(name: str):
    return QApplication.style().standardIcon(getattr(QStyle.StandardPixmap, name))


ISSUE_ICONS = {"error": "SP_MessageBoxCritical", "warning": "SP_MessageBoxWarning",
               "info": "SP_MessageBoxInformation"}
