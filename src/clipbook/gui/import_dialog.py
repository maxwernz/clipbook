"""Add a Word file to the library: either a new version/translation of a building block, or a new one.

Three simple steps: choose the file → say what it is → the automatic check shows the result.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from ..importer import check, import_file, is_word_file, machines_using
from ..library import Library, slugify
from .style import ERROR, MUTED, OK, WARN

LANG_LABELS = {"de": "Deutsch", "en": "English", "it": "Italiano", "fr": "Français", "es": "Español"}
MULTI_CHAPTER_SLOTS = {"general", "service"}


def _differs(a: str, b: str) -> bool:
    norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())  # noqa: E731
    a, b = norm(a), norm(b)
    return not (a in b or b in a)


def _label(text: str, name: str | None = None, wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def _card() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 14, 18, 16)
    lay.setSpacing(10)
    return f, lay


def _step(num: str, title: str) -> QHBoxLayout:
    row = QHBoxLayout()
    n = _label(num, "stepNumber", wrap=False)
    n.setAlignment(Qt.AlignmentFlag.AlignCenter)
    row.addWidget(n)
    row.addWidget(_label(title, "sectionTitle", wrap=False))
    row.addStretch()
    return row


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFixedWidth(90)
    return lbl


class DropZone(QLabel):
    file_dropped = Signal(Path)

    EMPTY = ("<b>Word-Datei hierher ziehen</b><br>"
             f"<span style='color:{MUTED}'>oder klicken, um eine Datei auszuwählen (.docx)</span>")

    def __init__(self):
        super().__init__(self.EMPTY)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(84)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style(False)

    def _style(self, active: bool) -> None:
        color = "#0160b2" if active else "#c3cbd8"
        bg = "#ebf3fb" if active else "#fafbfd"
        self.setStyleSheet(f"QLabel{{border:2px dashed {color};border-radius:10px;background:{bg};padding:10px;}}")

    def mouseReleaseEvent(self, e):
        f, _ = QFileDialog.getOpenFileName(self, "Word-Datei wählen", "", "Word (*.docx)")
        if f:
            self.file_dropped.emit(Path(f))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self._style(True)
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._style(False)

    def dropEvent(self, e):
        self._style(False)
        urls = e.mimeData().urls()
        if urls:
            self.file_dropped.emit(Path(urls[0].toLocalFile()))


class ImportDialog(QDialog):
    def __init__(self, lib: Library, parent=None, module_id: str | None = None,
                 file: Path | None = None):
        super().__init__(parent)
        self.lib = lib
        self.file: Path | None = None
        self.ok_to_import = False
        self.imported_module: str | None = None
        self.setWindowTitle("Word-Datei hinzufügen")
        self.resize(720, 820)
        self.check_timer = QTimer(self, singleShot=True, interval=250, timeout=self.run_check)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)
        lay.addWidget(_label("Word-Datei hinzufügen", "title"))
        lay.addWidget(_label("Neue oder geänderte Texte kommen als Word-Datei in die Bibliothek. "
                             "Die Datei wird geprüft und für die Anleitungen vorbereitet – "
                             "Ihr Original bleibt unverändert.", "subtitle"))

        # step 1: file
        c1, l1 = _card()
        l1.addLayout(_step("1", "Datei"))
        self.drop = DropZone()
        self.drop.file_dropped.connect(self.set_file)
        l1.addWidget(self.drop)
        lay.addWidget(c1)

        # step 2: what is it?
        c2, l2 = _card()
        l2.addLayout(_step("2", "Was ist das für eine Datei?"))
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.mode = QButtonGroup(self)
        self.btn_update = QPushButton("Neue Fassung / Übersetzung eines Bausteins")
        self.btn_update.setObjectName("segFirst")
        self.btn_new = QPushButton("Ganz neuer Baustein")
        self.btn_new.setObjectName("segLast")
        for i, b in enumerate((self.btn_update, self.btn_new)):
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.mode.addButton(b, i)
            seg.addWidget(b)
        seg.addStretch()
        l2.addLayout(seg)
        self.mode.idClicked.connect(self._mode_changed)

        self.pages = []
        upd = QWidget()
        fu = QFormLayout(upd)
        fu.setContentsMargins(0, 6, 0, 0)
        self.module_box = QComboBox()
        for slot in lib.slots:
            for m in sorted(lib.modules_in_slot(slot.id), key=lambda m: m.label()):
                self.module_box.addItem(f"{m.label()}   ·   {slot.label('de')}", m.id)
        fu.addRow(_field_label("Baustein"), self.module_box)
        new = QWidget()
        fn = QFormLayout(new)
        fn.setContentsMargins(0, 6, 0, 0)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("z. B. „Clipper DCX7“")
        self.slot_box = QComboBox()
        for s in lib.slots:
            self.slot_box.addItem(s.label("de"), s.id)
        fn.addRow(_field_label("Name"), self.title_edit)
        fn.addRow(_field_label("Baugruppe"), self.slot_box)
        self.pages = [upd, new]
        l2.addWidget(upd)
        l2.addWidget(new)

        lang_row = QFormLayout()
        lang_row.setContentsMargins(0, 0, 0, 0)
        self.lang_box = QComboBox()
        for code in lib.languages:
            self.lang_box.addItem(LANG_LABELS.get(code, code), code)
        lang_row.addRow(_field_label("Sprache"), self.lang_box)
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("optional, z. B. „Neue Fotos Drahtvorschub“")
        lang_row.addRow(_field_label("Änderung"), self.note_edit)
        l2.addLayout(lang_row)
        lay.addWidget(c2)

        # step 3: automatic check
        c3, l3 = _card()
        l3.addLayout(_step("3", "Prüfung"))
        self.result = _label(f"<span style='color:{MUTED}'>Wählen Sie zuerst eine Datei.</span>")
        self.result.setTextFormat(Qt.TextFormat.RichText)
        res_host = QWidget()
        rl = QVBoxLayout(res_host)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.result)
        self.outline_btn = QPushButton("Gliederung anzeigen")
        self.outline_btn.setObjectName("link")
        self.outline_btn.setVisible(False)
        self.outline_btn.clicked.connect(self._toggle_outline)
        rl.addWidget(self.outline_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.outline = _label("")
        self.outline.setVisible(False)
        self.outline.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rl.addWidget(self.outline)
        rl.addStretch()
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(res_host)
        l3.addWidget(sc, 1)
        lay.addWidget(c3, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        self.import_btn = QPushButton("Hinzufügen")
        self.import_btn.setObjectName("primary")
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self.run_import)
        buttons.addWidget(cancel)
        buttons.addWidget(self.import_btn)
        lay.addLayout(buttons)

        for w in (self.module_box, self.slot_box, self.lang_box):
            w.currentIndexChanged.connect(lambda *_: self.check_timer.start())
        self.title_edit.textChanged.connect(lambda *_: self.check_timer.start())

        if module_id and self.module_box.findData(module_id) >= 0:
            self.module_box.setCurrentIndex(self.module_box.findData(module_id))
        start = 0 if (module_id or lib.modules) else 1
        self.mode.button(start).setChecked(True)
        self._mode_changed(start)
        if file:
            self.set_file(file)

    # ---------------------------------------------------------------- state
    def _mode_changed(self, idx: int) -> None:
        for i, page in enumerate(self.pages):
            page.setVisible(i == idx)
        self.check_timer.start()

    def _toggle_outline(self) -> None:
        vis = not self.outline.isVisible()
        self.outline.setVisible(vis)
        self.outline_btn.setText("Gliederung ausblenden" if vis else "Gliederung anzeigen")

    def set_file(self, path: Path) -> None:
        if not is_word_file(path):
            QMessageBox.warning(self, "Keine Word-Datei",
                                f"„{path.name}“ ist keine .docx-Datei (oder eine Word-Sperrdatei ~$…).")
            return
        self.file = path
        self.drop.setText(f"<b>{path.name}</b><br><span style='color:{MUTED}'>{path.parent}</span>"
                          f"<br><span style='color:{MUTED}'>Andere Datei: hierher ziehen oder klicken</span>")
        if not self.title_edit.text():
            self.title_edit.setText(path.stem)
        self.run_check()

    def _target(self):
        lang = self.lang_box.currentData()
        if self.mode.checkedId() == 0:
            m = self.lib.modules.get(self.module_box.currentData())
            return m, (m.kind if m else "component"), (m.label(lang) if m else "")
        slot = self.slot_box.currentData()
        kind = "chapters" if slot in MULTI_CHAPTER_SLOTS else "component"
        return None, kind, self.title_edit.text().strip()

    # ---------------------------------------------------------------- check / import
    def run_check(self) -> None:
        self.ok_to_import = False
        self.import_btn.setEnabled(False)
        if not self.file:
            return
        module, kind, title = self._target()
        lang = self.lang_box.currentData()
        rep = check(self.lib, self.file, kind=kind, title=title)
        good, warn, bad = [], [], []
        good.append(f"{len(rep.headings)} Überschriften und {rep.images} Bilder erkannt")
        removed = [h for h in rep.headings if h.removed_number]
        if removed:
            good.append(f"{len(removed)} getippte Kapitelnummern entfernt – die Nummern vergibt die Anleitung")
        for i in rep.issues:
            if i.level == "error":
                bad.append(i.message)
            elif i.level == "warning":
                warn.append(i.message)
        if module is not None:
            first = rep.headings[0].text if rep.headings else ""
            if module.kind == "component" and first and _differs(first, module.label(lang)) \
                    and _differs(first, module.label()):
                warn.append(f"Die erste Überschrift „{first}“ passt nicht zu „{module.label()}“ – "
                            f"richtigen Baustein gewählt?")
            if module.docx_path(lang).exists():
                good.append(f"Ersetzt die bisherige {LANG_LABELS.get(lang, lang)}-Fassung "
                            f"(wird archiviert, Version {module.version} → {module.version + 1})")
            else:
                good.append(f"Neue Sprache {LANG_LABELS.get(lang, lang)} für „{module.label()}“")
            used = machines_using(self.lib, module.id)
            if used:
                good.append("Wird beim nächsten Erstellen übernommen in: " + ", ".join(used))
        else:
            if not title:
                bad.append("Bitte einen Namen eingeben.")
            elif slugify(title) in self.lib.modules:
                bad.append(f"Einen Baustein „{title}“ gibt es schon – dann bitte "
                           f"„Neue Fassung“ wählen.")
        lines = [f"<span style='color:{OK}'>✓</span> {t}" for t in good]
        lines += [f"<span style='color:{WARN}'>▲</span> {t}" for t in warn]
        lines += [f"<span style='color:{ERROR}'>●</span> {t}" for t in bad]
        if warn and not bad:
            lines.append(f"<br><span style='color:{MUTED}'>Hinweise sind kein Hindernis – die Datei kann "
                         f"trotzdem hinzugefügt werden.</span>")
        self.result.setText("<br>".join(lines))
        self.outline.setText("<br>".join(
            ("&nbsp;" * 6 * (h.level - 1)) + (f"<b>{h.text}</b>" if h.level == 1 else h.text)
            for h in rep.headings))
        self.outline_btn.setVisible(bool(rep.headings))
        self.ok_to_import = not bad
        self.import_btn.setEnabled(self.ok_to_import)

    def run_import(self) -> None:
        self.run_check()
        if not self.ok_to_import or not self.file:
            return
        lang = self.lang_box.currentData()
        module, kind, title = self._target()
        if module is None:
            module = self.lib.new_module(slugify(title), {lang: title}, self.slot_box.currentData(), kind)
        rep = import_file(self.lib, self.file, module, lang, note=self.note_edit.text().strip())
        if rep.errors:
            self.result.setText("<br>".join(i.message for i in rep.errors))
            return
        self.imported_module = module.id
        self.accept()
