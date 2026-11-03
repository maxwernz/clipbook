"""GUI smoke test: drag & drop with simulated mouse events (offscreen, skipped on CI)."""

import os
import shutil
from pathlib import Path

import pytest

LIB = Path.home() / "ProfilClip" / "Anleitungs-Bibliothek"
pytestmark = pytest.mark.skipif(bool(os.environ.get("CI")) or not LIB.exists(),
                                reason="needs the real library and a Qt platform")


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["MANUAL_BUILDER_SETTINGS"] = "ManualBuilderTest"
    from PySide6.QtWidgets import QApplication
    from manual_builder.gui import style
    a = QApplication.instance() or QApplication([])
    style.apply(a)
    return a


def _mouse(widget, kind, local, buttons):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    types = {"press": QEvent.Type.MouseButtonPress, "move": QEvent.Type.MouseMove,
             "release": QEvent.Type.MouseButtonRelease}
    g = widget.mapToGlobal(local)
    btn = Qt.MouseButton.NoButton if kind == "move" else Qt.MouseButton.LeftButton
    ev = QMouseEvent(types[kind], QPointF(local), QPointF(g), btn, buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, ev)


def drag(app, source, target, target_local):
    """Press on source, move onto target (in target coordinates), release."""
    from PySide6.QtCore import QPoint, Qt
    left = Qt.MouseButton.LeftButton
    start = QPoint(20, 20)
    _mouse(source, "press", start, left)
    _mouse(source, "move", start + QPoint(30, 0), left)
    dst = source.mapFromGlobal(target.mapToGlobal(target_local))
    _mouse(source, "move", dst, left)
    _mouse(source, "release", dst, Qt.MouseButton.NoButton)
    for _ in range(3):
        app.processEvents()


def test_drag_and_drop_flow(app, tmp_path):
    from PySide6.QtCore import QPoint
    from manual_builder.gui.main_window import ChapterTile, LibraryTile, MainWindow
    from manual_builder.library import Library, Machine

    lib_dir = tmp_path / "lib"
    shutil.copytree(LIB, lib_dir, ignore=shutil.ignore_patterns("archive"))
    win = MainWindow(Library(lib_dir))
    win.resize(1480, 1500)   # all chapter tiles visible without scrolling
    win.show()
    app.processEvents()
    ws = win.workspace
    start = list(ws.machine.modules)

    def lib_tile(mid):
        return next(t for t in win.findChildren(LibraryTile) if t.module.id == mid and t.isVisible())

    chapters = ws.manual.chapters
    viewport = ws.manual.chapter_scroll.viewport()
    bottom = QPoint(50, viewport.height() - 5)

    # library tile → end of the manual
    new = next(m for m in ("option-drucker", "option-sammelpacker", "option-waage") if m not in start)
    drag(app, lib_tile(new), viewport, bottom)
    assert ws.machine.modules[-1] == new
    assert not ws.drag.active and ws.drag.ghost is None

    # another clipper variant replaces the current one
    other = "clipper-dcx5fc" if "clipper-dcx5s" in ws.machine.modules else "clipper-dcx5s"
    drag(app, lib_tile(other), chapters, QPoint(50, 5))
    assert other in ws.machine.modules
    assert len([m for m in ws.machine.modules if m.startswith("clipper")]) == 1

    # reorder: first chapter tile → end
    first = ws.machine.modules[0]
    tiles = [t for t in win.findChildren(ChapterTile) if t.isVisible()]
    drag(app, min(tiles, key=lambda t: t.index), viewport, bottom)
    assert ws.machine.modules[-1] == first

    # chapter tile dragged onto the library is removed
    n = len(ws.machine.modules)
    tiles = [t for t in win.findChildren(ChapterTile) if t.isVisible()]
    drag(app, max(tiles, key=lambda t: t.index), ws.library, QPoint(200, 200))
    assert len(ws.machine.modules) == n - 1

    # releasing somewhere else does nothing
    before = list(ws.machine.modules)
    drag(app, lib_tile("option-beutelkontrolle"), win.machines, QPoint(50, 300))
    assert ws.machine.modules == before

    for _ in range(4):
        ws.undo()
    assert ws.machine.modules == start
    ws.save()
    assert Machine.load(ws.machine.path).modules == start
    win.close()


def test_update_dialog_flow(app, tmp_path, monkeypatch):
    """Banner → dialog → download + checksum → install() is called → app quits."""
    import hashlib
    import json
    from PySide6.QtWidgets import QApplication
    from manual_builder import updater
    from manual_builder.gui import update_ui
    from manual_builder.gui.main_window import MainWindow
    from manual_builder.library import Library

    feed = tmp_path / "feed"
    feed.mkdir()
    payload = b"neue Version"
    (feed / "pkg.zip").write_bytes(payload)
    (feed / "latest.json").write_text(json.dumps({"version": "99.0.0", "notes": "- Test", "assets": {
        updater.platform_key(): {"file": "pkg.zip", "sha256": hashlib.sha256(payload).hexdigest(),
                                 "size": len(payload)}}}), encoding="utf-8")
    installed, quit_called = [], []
    monkeypatch.setattr(updater, "can_self_update", lambda: (True, ""))
    monkeypatch.setattr(updater, "install", lambda path, relaunch=True: installed.append(path))
    monkeypatch.setattr(QApplication, "quit", lambda *a: quit_called.append(True))

    lib_dir = tmp_path / "lib"
    shutil.copytree(LIB, lib_dir, ignore=shutil.ignore_patterns("archive", "updates"))
    win = MainWindow(Library(lib_dir))
    win.settings.setValue("update_feed", str(feed))
    win.settings.remove("skipped_version")
    win.show()
    win.updates.check()
    for _ in range(200):
        app.processEvents()
        if win.update_banner.isVisible():
            break
        import time
        time.sleep(0.02)
    assert win.update_banner.isVisible() and win.update_banner.release.version == "99.0.0"

    dlg = update_ui.UpdateDialog(win, win.update_banner.release)
    dlg.show()
    dlg.go_btn.click()
    for _ in range(300):
        app.processEvents()
        if installed and quit_called:
            break
        import time
        time.sleep(0.02)
    assert installed and installed[0].read_bytes() == payload
    assert quit_called
    win.settings.remove("update_feed")
    dlg.close()
    win.close()


def test_find_library_root_tolerates_one_level_off(tmp_path):
    from manual_builder.gui.app import find_library_root
    lib = tmp_path / "Anleitungs-Bibliothek"
    (lib / "modules").mkdir(parents=True)
    (lib / "library.yaml").write_text("slots: []\n")
    assert find_library_root(lib) == lib
    assert find_library_root(lib / "modules") == lib      # picked a subfolder
    assert find_library_root(tmp_path) == lib             # picked the folder around it
    assert find_library_root(tmp_path / "Anleitungs-Bibliothek" / "modules" / "..") is not None
    (tmp_path / "other").mkdir()
    assert find_library_root(tmp_path / "other") is None


def test_new_library_target_uses_subfolder_when_not_empty(tmp_path):
    from manual_builder.gui.app import new_library_target
    assert new_library_target(tmp_path) == tmp_path
    (tmp_path / "something.txt").write_text("x")
    assert new_library_target(tmp_path) == tmp_path / "Anleitungs-Bibliothek"
