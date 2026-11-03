"""Update user interface: background check, banner, download & install dialog."""

from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
                               QProgressBar, QPushButton, QTextBrowser, QVBoxLayout)

from .. import __version__, updater
from .icons import icon, pixmap
from .style import ACCENT, ERROR, MUTED

log = logging.getLogger("clipbook.update")
CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000      # every 6 hours while the app is open


class _CheckWorker(QObject):
    done = Signal(object)          # CheckResult

    def __init__(self, feeds):
        super().__init__()
        self.feeds = feeds

    def run(self):
        try:
            self.done.emit(updater.check(self.feeds))
        except Exception as e:   # pragma: no cover - never crash because of an update check
            log.exception("Update-Prüfung fehlgeschlagen")
            self.done.emit(updater.CheckResult(None, None, None, [str(e)]))


class UpdateManager(QObject):
    """Owns the checks. Emits `available` when a newer version for this computer exists."""
    available = Signal(object)        # Release
    checked = Signal(object)          # CheckResult (every check)

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self._thread: QThread | None = None
        self.last = None
        self.timer = QTimer(self, interval=CHECK_INTERVAL_MS, timeout=lambda: self.check(silent=True))

    def feeds(self) -> list[str]:
        return updater.feed_candidates(self.win.settings.value("update_feed", "") or "", self.win.lib)

    def start(self) -> None:
        if str(self.win.settings.value("auto_update_check", "true")) == "true":
            QTimer.singleShot(2500, lambda: self.check(silent=True))
            self.timer.start()

    def check(self, silent: bool = True) -> None:
        if self._thread is not None:
            return
        self._thread = QThread()
        self._worker = _CheckWorker(self.feeds())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._done)
        self._thread.start()

    def _done(self, res) -> None:
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self.last = res
        self.checked.emit(res)
        skipped = self.win.settings.value("skipped_version", "")
        if res.release and res.release.version != skipped:
            self.available.emit(res.release)


class UpdateBanner(QFrame):
    """Slim bar at the top of the window: 'Version x is available'."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.release = None
        self.setObjectName("updateBanner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 10, 8)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(pixmap("upload", "#ffffff", 18))
        lay.addWidget(ic)
        self.text = QLabel()
        self.text.setObjectName("bannerText")
        lay.addWidget(self.text, 1)
        self.notes_btn = QPushButton("Was ist neu?")
        self.notes_btn.setObjectName("bannerLink")
        self.notes_btn.clicked.connect(self.show_dialog)
        self.install_btn = QPushButton("Jetzt aktualisieren")
        self.install_btn.setObjectName("bannerPrimary")
        self.install_btn.clicked.connect(self.show_dialog)
        later = QPushButton("Später")
        later.setObjectName("bannerLink")
        later.clicked.connect(self.hide)
        skip = QPushButton("Diese Version überspringen")
        skip.setObjectName("bannerLink")
        skip.clicked.connect(self.skip)
        for b in (self.notes_btn, self.install_btn, later, skip):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(b)
        self.hide()

    def show_release(self, rel) -> None:
        self.release = rel
        self.text.setText(f"<b>Version {rel.version}</b> ist verfügbar (installiert: {__version__}).")
        self.show()

    def skip(self) -> None:
        if self.release:
            self.win.settings.setValue("skipped_version", self.release.version)
        self.hide()

    def show_dialog(self) -> None:
        if self.release:
            UpdateDialog(self.win, self.release).exec()


class _DownloadWorker(QObject):
    progress = Signal(int, int)
    done = Signal(object)          # Path
    failed = Signal(str)

    def __init__(self, rel):
        super().__init__()
        self.rel = rel
        self.cancel = threading.Event()

    def run(self):
        try:
            target = Path(tempfile.mkdtemp(prefix="clipbook-update-dl-"))
            path = updater.download(self.rel, target, progress=lambda d, t: self.progress.emit(d, t),
                                    cancelled=self.cancel.is_set)
            self.done.emit(path)
        except updater.UpdateError as e:
            self.failed.emit(str(e))
        except Exception as e:  # pragma: no cover
            log.exception("Download fehlgeschlagen")
            self.failed.emit(f"Download fehlgeschlagen: {e}")


class UpdateDialog(QDialog):
    def __init__(self, win, rel):
        super().__init__(win)
        self.win = win
        self.rel = rel
        self.thread: QThread | None = None
        self.setWindowTitle("Update")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(12)
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(pixmap("upload", ACCENT, 28))
        head.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(f"Version {rel.version}")
        t.setObjectName("title")
        col.addWidget(t)
        sub = QLabel(f"Installiert ist {__version__}" + (f" · erschienen am {rel.released}" if rel.released else ""))
        sub.setObjectName("subtitle")
        col.addWidget(sub)
        head.addLayout(col, 1)
        lay.addLayout(head)
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(rel.notes or "_Keine Beschreibung vorhanden._")
        notes.setMinimumHeight(160)
        lay.addWidget(notes, 1)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        ok, reason = updater.can_self_update()
        if not ok:
            self.status.setText(f"<span style='color:{ERROR}'>{reason}</span>")
        row = QHBoxLayout()
        row.addStretch()
        self.cancel_btn = QPushButton("Später")
        self.cancel_btn.clicked.connect(self._cancel)
        self.go_btn = QPushButton("Herunterladen und installieren")
        self.go_btn.setObjectName("primary")
        self.go_btn.setIcon(icon("upload", "#ffffff"))
        self.go_btn.setEnabled(ok)
        self.go_btn.clicked.connect(self._start)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.go_btn)
        lay.addLayout(row)

    def _start(self) -> None:
        ws = self.win.workspace
        if ws.thread is not None:
            QMessageBox.information(self, "Bitte warten", "Es wird gerade eine Anleitung erstellt. "
                                    "Bitte danach aktualisieren.")
            return
        self.go_btn.setEnabled(False)
        self.cancel_btn.setText("Abbrechen")
        self.progress.show()
        self.progress.setRange(0, 0)
        self.status.setText("Update wird geladen …")
        self.thread = QThread()
        self.worker = _DownloadWorker(self.rel)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._progress)
        self.worker.done.connect(self._downloaded)
        self.worker.failed.connect(self._failed)
        self.thread.start()

    def _progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(done * 1000 / total))
            self.status.setText(f"Update wird geladen … {done / 1e6:.1f} von {total / 1e6:.1f} MB")

    def _stop_thread(self) -> None:
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None

    def _downloaded(self, path) -> None:
        self._stop_thread()
        self.progress.setRange(0, 1000)
        self.progress.setValue(1000)
        self.status.setText("Geprüft ✓ – Installation wird gestartet. Die App startet gleich neu.")
        QApplication.processEvents()
        try:
            self.win.workspace.save_timer.stop()
            self.win.workspace.save()
            updater.install(path)
        except updater.UpdateError as e:
            self._failed(str(e))
            return
        except Exception as e:  # pragma: no cover
            log.exception("Installation fehlgeschlagen")
            self._failed(f"Installation fehlgeschlagen: {e}")
            return
        log.info("Beende App für das Update auf %s", self.rel.version)
        QTimer.singleShot(600, QApplication.quit)

    def _failed(self, msg: str) -> None:
        self._stop_thread()
        self.progress.hide()
        self.go_btn.setEnabled(True)
        self.go_btn.setText("Erneut versuchen")
        self.cancel_btn.setText("Schließen")
        self.status.setText(f"<span style='color:{ERROR}'>{msg}</span>")
        log.warning("Update fehlgeschlagen: %s", msg)

    def _cancel(self) -> None:
        if self.thread is not None:
            self.worker.cancel.set()
            self._stop_thread()
        self.reject()


def describe(res) -> str:
    """One line for the settings dialog."""
    if res is None:
        return ""
    if res.release:
        return f"Version {res.release.version} ist verfügbar."
    if res.latest:
        return f"<span style='color:{MUTED}'>Aktuell – neueste Version ist {res.latest}.</span>"
    return f"<span style='color:{ERROR}'>Keine Update-Quelle erreichbar.</span>"
