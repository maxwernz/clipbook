"""Start the GUI and find (or create) the module library."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from .. import __version__
from ..library import Library
from .common import app_settings


def _candidates(explicit: Path | None) -> list[Path]:
    out = []
    if explicit:
        out.append(explicit)
    stored = app_settings().value("library", "")
    if stored:
        out.append(Path(stored))
    exe_dir = Path(sys.executable).resolve().parent
    out += [Path.cwd() / "library", exe_dir / "library", exe_dir.parent / "library"]
    return out


NEW_LIBRARY_NAME = "Anleitungs-Bibliothek"


def find_library_root(d: Path) -> Path | None:
    """The folder with library.yaml: `d` itself, its parent (a subfolder like modules/ was picked)
    or a direct subfolder (the folder that contains the library was picked)."""
    if (d / "library.yaml").exists():
        return d
    if (d.parent / "library.yaml").exists():
        return d.parent
    try:
        subs = sorted(p for p in d.iterdir() if p.is_dir() and (p / "library.yaml").exists())
    except OSError:
        return None
    return subs[0] if len(subs) == 1 else None


def new_library_target(d: Path) -> Path:
    """Where a new library goes: `d` if it is empty, otherwise a fresh subfolder inside it."""
    if not any(d.iterdir()):
        return d
    target, n = d / NEW_LIBRARY_NAME, 2
    while target.exists() and any(target.iterdir()):
        target, n = d / f"{NEW_LIBRARY_NAME} {n}", n + 1
    return target


def choose_library(parent=None) -> Library | None:
    while True:
        box = QMessageBox(parent)
        box.setWindowTitle("Bibliothek wählen")
        box.setText("<b>Keine Modul-Bibliothek gefunden</b>")
        box.setInformativeText(
            "Clipbook arbeitet mit einer Bibliothek: einem Ordner mit der Datei "
            "<i>library.yaml</i>, den Bausteinen (modules) und den gespeicherten Maschinen. "
            "Normalerweise liegt sie auf dem Netzlaufwerk.<br><br>"
            "<b>Bibliothek öffnen</b>: Ordner einer vorhandenen Bibliothek auswählen "
            "(Netzlaufwerk oder eine lokale Kopie, z. B. zum Testen).<br><br>"
            "<b>Neue Bibliothek anlegen</b>: nur einmalig nötig. Baut eine neue Bibliothek aus dem "
            "Ordner mit den bisherigen Word-Anleitungen („Bedienungsanleitungen“).")
        open_btn = box.addButton("Bibliothek öffnen …", QMessageBox.ButtonRole.AcceptRole)
        seed_btn = box.addButton("Neue Bibliothek anlegen …", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Beenden", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(open_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is open_btn:
            d = QFileDialog.getExistingDirectory(parent, "Bibliotheksordner wählen (enthält library.yaml)")
            if not d:
                continue
            root = find_library_root(Path(d))
            if root is None:
                QMessageBox.warning(
                    parent, "Keine Bibliothek",
                    f"In „{d}“ gibt es keine library.yaml.\n\n"
                    "Bitte den Ordner der Bibliothek wählen, in dem library.yaml direkt liegt "
                    "(neben den Ordnern modules, machines und templates).")
                continue
            try:
                return Library(root)
            except Exception as e:  # broken library.yaml etc.
                QMessageBox.warning(parent, "Bibliothek fehlerhaft",
                                    f"Die Bibliothek in „{root}“ lässt sich nicht öffnen:\n{e}")
        elif clicked is seed_btn:
            legacy = QFileDialog.getExistingDirectory(
                parent, "Schritt 1 von 2: Ordner mit den bisherigen Anleitungen („Bedienungsanleitungen“) wählen")
            if not legacy:
                continue
            from ..seed import LEGACY_MODULES, seed_from_legacy
            if not (Path(legacy) / LEGACY_MODULES[0][1]["de"]).exists():
                QMessageBox.warning(
                    parent, "Falscher Ordner",
                    f"„{legacy}“ enthält nicht die bisherigen Anleitungen "
                    f"(erwartet z. B. {LEGACY_MODULES[0][1]['de']}).\n\n"
                    "Zum Testen ohne Netzlaufwerk besser eine Kopie der Bibliothek über "
                    "„Bibliothek öffnen“ verwenden.")
                continue
            target = QFileDialog.getExistingDirectory(
                parent, "Schritt 2 von 2: Speicherort für die neue Bibliothek wählen")
            if not target:
                continue
            target = new_library_target(Path(target))
            target.mkdir(parents=True, exist_ok=True)
            try:
                return seed_from_legacy(Path(legacy), Path(target), log=lambda *_: None)
            except Exception as e:  # pragma: no cover
                QMessageBox.critical(parent, "Fehler", f"Import fehlgeschlagen:\n{e}")
        else:
            return None


def run(library: Path | None = None) -> int:
    from .. import logsetup
    logsetup.setup()
    app = QApplication.instance() or QApplication(sys.argv)
    logsetup.install_qt_handlers()
    app.setApplicationName("Clipbook")
    app.setOrganizationName("ProfilClip")
    app.setApplicationVersion(__version__)
    from PySide6.QtGui import QIcon
    from . import style
    style.apply(app)
    app.setWindowIcon(QIcon(str(style.ASSETS / "app_icon.png")))
    translator = QTranslator(app)   # German texts for standard buttons (Speichern, Abbrechen …)
    if translator.load(QLocale(QLocale.Language.German), "qtbase", "_",
                       QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)

    lib = None
    for c in _candidates(library):
        if (c / "library.yaml").exists():
            lib = Library(c)
            break
    if lib is None:
        lib = choose_library()
        if lib is None:
            return 0
    app_settings().setValue("library", str(lib.root))

    from .main_window import MainWindow
    win = MainWindow(lib)
    win.show()
    return app.exec()
