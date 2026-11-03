"""Edit a module: metadata, Word files and the structured tables (maintenance, parts, faults)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QGridLayout,
                               QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QPushButton,
                               QStyledItemDelegate, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from ..library import DATA_SECTIONS, DRAFT_KEY, Library, Module, is_draft, tr
from .common import lang_name, open_path

# (key, header, translated?, numeric?)
COLUMNS = {
    "maintenance": [("interval", "Intervall (Text)", True, False),
                    ("interval_days", "Tage (Sortierung)", False, True),
                    ("task", "Tätigkeit", True, False),
                    ("parts", "Teile / Ort", True, False)],
    "spare_parts": [("part_no", "Teilenummer", False, False),
                    ("description", "Bezeichnung", True, False),
                    ("interval", "Intervall (Text)", True, False),
                    ("interval_days", "Tage (Sortierung)", False, True)],
    "faults": [("code", "Nr.", False, True),
               ("message", "Meldung", True, False),
               ("cause", "Ursache", True, False),
               ("remedy", "Behebung", True, False)],
}
SECTION_TITLES = {"maintenance": "Wartung", "spare_parts": "Ersatzteile", "faults": "Störungen"}
DRAFT_BG = QColor("#fce4c4")
DRAFT_BANNER_STYLE = ("background:#fff4e5; border:1px solid #f0b46a; border-radius:6px; padding:8px 10px;"
                      "color:#7a4500;")


class MultiLineDelegate(QStyledItemDelegate):
    """Table cells with line breaks (Shift+Enter not needed: Enter = new line, click away = done)."""

    def createEditor(self, parent, option, index):
        ed = QPlainTextEdit(parent)
        ed.setTabChangesFocus(True)
        return ed

    def setEditorData(self, editor, index):
        editor.setPlainText(index.data(Qt.ItemDataRole.EditRole) or "")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.toPlainText(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        r = option.rect
        r.setHeight(max(r.height(), 90))
        editor.setGeometry(r)


class DataTable(QWidget):
    def __init__(self, section: str, dialog: "ModuleDialog"):
        super().__init__()
        self.section = section
        self.dialog = dialog
        self.cols = COLUMNS[section]
        lay = QVBoxLayout(self)
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(DRAFT_BANNER_STYLE)
        lay.addWidget(self.banner)
        self.table = QTableWidget(0, len(self.cols))
        self.table.setHorizontalHeaderLabels([c[1] for c in self.cols])
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setItemDelegate(MultiLineDelegate(self.table))
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        for i, (key, _, translated, numeric) in enumerate(self.cols):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch if translated
                                    else QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        for text, slot in (("Zeile hinzufügen", self.add_row), ("Zeilen löschen", self.delete_rows),
                           ("In anderen Baustein verschieben …", self.move_rows),
                           ("Als geprüft markieren …", self.mark_checked),
                           ("Als Entwurf markieren …", self.mark_draft)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.entries: list[dict] = [dict(e) for e in dialog.module.entries(section)]

    # table <-> entries for one language
    def load(self, lang: str) -> None:
        self.table.setRowCount(0)
        for e in self.entries:
            self._append(e, lang)
        self.table.resizeRowsToContents()
        self._update_banner()

    def draft_count(self) -> int:
        return sum(1 for e in self.entries if is_draft(e))

    def tab_title(self) -> str:
        n = self.draft_count()
        return f"{SECTION_TITLES[self.section]}  {len(self.entries)}" + ("  · Entwurf" if n else "")

    def _update_banner(self) -> None:
        n = self.draft_count()
        self.banner.setVisible(bool(n))
        if n:
            self.banner.setText(
                f"<b>Entwurf – nicht geprüft.</b> {n} von {len(self.entries)} Zeilen (orange) wurden "
                "automatisch diesem Baustein zugeordnet. Das ist ein Vorschlag, kein geprüfter Stand: "
                "Zuordnung und Inhalt muss die zuständige Person klären. Maus auf eine Zeile zeigt die "
                "offene Frage. In der Anleitung werden diese Zeilen ebenfalls als Entwurf markiert.")
        idx = self.dialog.tabs.indexOf(self) if hasattr(self.dialog, "tabs") else -1
        if idx >= 0:
            self.dialog.tabs.setTabText(idx, self.tab_title())

    def _append(self, e: dict, lang: str) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, (key, _, translated, _) in enumerate(self.cols):
            if translated:
                val = e.get(key)
                text = (val or {}).get(lang, "") if isinstance(val, dict) else (val or "")
                item = QTableWidgetItem(text)
                if not text and isinstance(val, dict) and val.get("de") and lang != "de":
                    item.setToolTip("Deutsch: " + val["de"])
                    item.setBackground(Qt.GlobalColor.yellow)
            else:
                v = e.get(key)
                item = QTableWidgetItem("" if v is None else str(v))
            if is_draft(e):
                if item.background().style() == Qt.BrushStyle.NoBrush:   # keep "translation missing" yellow
                    item.setBackground(DRAFT_BG)
                item.setToolTip("\n".join(x for x in (str(e[DRAFT_KEY]), item.toolTip()) if x))
            self.table.setItem(r, c, item)

    def store(self, lang: str) -> None:
        for r, e in enumerate(self.entries):
            for c, (key, _, translated, numeric) in enumerate(self.cols):
                item = self.table.item(r, c)
                text = item.text().strip() if item else ""
                if translated:
                    val = e.get(key)
                    val = dict(val) if isinstance(val, dict) else ({"de": val} if val else {})
                    if text:
                        val[lang] = text
                    else:
                        val.pop(lang, None)
                    e[key] = val
                elif numeric:
                    try:
                        e[key] = int(text) if text else None
                    except ValueError:
                        e[key] = text
                else:
                    e[key] = text

    def add_row(self) -> None:
        self.store(self.dialog.lang)
        self.entries.append({})
        self.load(self.dialog.lang)
        self.table.scrollToBottom()

    def selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def delete_rows(self) -> None:
        rows = self.selected_rows()
        if not rows:
            return
        self.store(self.dialog.lang)
        for r in reversed(rows):
            del self.entries[r]
        self.load(self.dialog.lang)

    def mark_checked(self) -> None:
        rows = [r for r in self.selected_rows() if is_draft(self.entries[r])]
        if not rows:
            QMessageBox.information(self, "Als geprüft markieren",
                                    "Bitte zuerst orange markierte Zeilen (Entwurf) auswählen.")
            return
        answer = QMessageBox.question(
            self, "Als geprüft markieren",
            f"{len(rows)} Zeilen als geprüft markieren?\n\nBitte nur, wenn die zuständige Person Zuordnung "
            "und Inhalt bestätigt hat. Danach erscheinen die Zeilen in der Anleitung ohne Entwurfs-Hinweis.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store(self.dialog.lang)
        for r in rows:
            self.entries[r].pop(DRAFT_KEY, None)
        self.dialog.checked_notes.append(f"{len(rows)} {SECTION_TITLES[self.section]}-Zeilen als geprüft markiert")
        self.load(self.dialog.lang)

    def mark_draft(self) -> None:
        rows = self.selected_rows()
        if not rows:
            QMessageBox.information(self, "Als Entwurf markieren", "Bitte zuerst Zeilen auswählen.")
            return
        note, ok = QInputDialog.getText(self, "Als Entwurf markieren",
                                        "Was ist offen oder muss geklärt werden?",
                                        text="Entwurf: Vorschlag, nicht fachlich geprüft.")
        if not ok:
            return
        self.store(self.dialog.lang)
        for r in rows:
            self.entries[r][DRAFT_KEY] = note.strip() or "Entwurf: Vorschlag, nicht fachlich geprüft."
        self.load(self.dialog.lang)

    def move_rows(self) -> None:
        rows = self.selected_rows()
        if not rows:
            QMessageBox.information(self, "Verschieben", "Bitte zuerst Zeilen markieren.")
            return
        lib = self.dialog.lib
        others = [m for m in lib.modules.values() if m.id != self.dialog.module.id]
        names = [f"{m.label()}  [{m.id}]" for m in others]
        choice, ok = QInputDialog.getItem(self, "In anderen Baustein verschieben",
                                          "Ziel-Baustein:", names, 0, False)
        if not ok:
            return
        target = others[names.index(choice)]
        self.store(self.dialog.lang)
        moved = [self.entries[r] for r in rows]
        target.data.setdefault(self.section, [])
        target.data[self.section] = list(target.data[self.section]) + moved
        target.add_history(f"{len(moved)} {SECTION_TITLES[self.section]}-Einträge "
                           f"von '{self.dialog.module.id}' übernommen")
        target.save_data()
        target.save_meta()
        for r in reversed(rows):
            del self.entries[r]
        # save both sides right away so nothing is lost or duplicated on "Abbrechen"
        source = self.dialog.module
        source.data[self.section] = list(self.entries)
        source.save_data()
        self.load(self.dialog.lang)
        self.dialog.changed_other = True
        QMessageBox.information(self, "Verschoben",
                                f"{len(moved)} Einträge nach '{target.label()}' verschoben "
                                f"(dort bereits gespeichert).")


class ModuleDialog(QDialog):
    def __init__(self, lib: Library, module: Module, parent=None, lang: str = "de"):
        super().__init__(parent)
        self.lib = lib
        self.module = module
        self.lang = lang
        self.changed_other = False
        self.checked_notes: list[str] = []
        self.setWindowTitle(f"Baustein: {module.label(lang)}")
        self.resize(1100, 760)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        top = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(4)
        t = QLabel(module.label(lang))
        t.setObjectName("title")
        col.addWidget(t)
        sub = QLabel("Wartung, Ersatzteile und Störungen werden als Tabellen ans Ende des Kapitels gesetzt "
                     "und in die Gesamtübersichten der Anleitung übernommen. Doppelklick auf eine Zelle "
                     "zum Bearbeiten.")
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        col.addWidget(sub)
        top.addLayout(col, 1)
        top.addSpacing(16)
        top.addWidget(QLabel("Sprache:"))
        self.lang_box = QComboBox()
        for code in lib.languages:
            self.lang_box.addItem(lang_name(code), code)
        self.lang_box.setCurrentIndex(max(0, lib.languages.index(lang) if lang in lib.languages else 0))
        self.lang_box.currentIndexChanged.connect(self._lang_changed)
        top.addWidget(self.lang_box)
        top.addStretch()
        lay.addLayout(top)

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self._build_info_tab()
        self.tables: dict[str, DataTable] = {}
        for section in DATA_SECTIONS:
            t = DataTable(section, self)
            self.tables[section] = t
            self.tabs.addTab(t, t.tab_title())
            t.load(self.lang)

        bb = QHBoxLayout()
        bb.addStretch()
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Speichern")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        bb.addWidget(cancel)
        bb.addWidget(save)
        lay.addLayout(bb)
        self.tabs.setCurrentIndex(3 if self.module.entries("faults") else 0)

    # ---------------------------------------------------------------- info tab
    def _build_info_tab(self) -> None:
        m = self.module
        w = QWidget()
        outer = QVBoxLayout(w)
        form = QFormLayout()
        outer.addLayout(form)
        outer.addStretch()
        self.title_edit = QLineEdit()
        self.component_edit = QLineEdit()
        self.component_edit.setPlaceholderText("leer = Titel; Name in den Übersichtstabellen")
        self.slot_box = QComboBox()
        for s in self.lib.slots:
            self.slot_box.addItem(s.label("de"), s.id)
        self.slot_box.setCurrentIndex(max(0, self.slot_box.findData(m.slot)))
        self.kind_box = QComboBox()
        self.kind_box.addItem("Ein Kapitel (Baugruppe)", "component")
        self.kind_box.addItem("Mehrere Kapitel (z. B. Allgemeines)", "chapters")
        self.kind_box.setCurrentIndex(max(0, self.kind_box.findData(m.kind)))
        self.desc_edit = QPlainTextEdit(m.description)
        self.desc_edit.setFixedHeight(60)
        self.conflicts_edit = QLineEdit(", ".join(m.conflicts))
        self.requires_edit = QLineEdit(", ".join(m.requires))
        form.setContentsMargins(18, 16, 18, 16)
        form.setVerticalSpacing(10)
        form.addRow("Name:", self.title_edit)
        form.addRow("Baugruppe:", self.slot_box)
        form.addRow("Beschreibung:", self.desc_edit)

        files = QWidget()
        fl = QGridLayout(files)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setHorizontalSpacing(12)
        fl.setVerticalSpacing(4)
        for r, code in enumerate(self.lib.languages):
            p = m.docx_path(code)
            fl.addWidget(QLabel(lang_name(code)), r, 0)
            if p.exists():
                b = QPushButton("In Word öffnen")
                b.setObjectName("link")
                b.clicked.connect(lambda _=False, p=p: open_path(p))
                fl.addWidget(b, r, 1, Qt.AlignmentFlag.AlignLeft)
            else:
                miss = QLabel("noch nicht vorhanden – über „Word-Datei hinzufügen“ ergänzen")
                miss.setObjectName("hint")
                fl.addWidget(miss, r, 1)
        b = QPushButton("Ordner öffnen")
        b.setObjectName("link")
        b.clicked.connect(lambda: open_path(m.path))
        fl.addWidget(b, len(self.lib.languages), 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
        fl.setColumnStretch(1, 1)
        form.addRow("Word-Dateien:", files)

        hist = QListWidget()
        for h in reversed(m.history):
            hist.addItem(f"v{h.get('version')}  {h.get('date', '')}  "
                         f"{('[' + h['language'] + '] ') if h.get('language') else ''}{h.get('note', '')}")
        hist.setFixedHeight(90)
        form.addRow("Verlauf:", hist)
        adv_btn = QPushButton("Erweitert anzeigen")
        adv_btn.setObjectName("link")
        adv = QWidget()
        af = QFormLayout(adv)
        af.setContentsMargins(0, 0, 0, 0)
        af.addRow("Interne ID:", QLabel(f"{m.id}   (Version {m.version})"))
        af.addRow("Kurzname in Übersichten:", self.component_edit)
        af.addRow("Art:", self.kind_box)
        af.addRow("Schließt aus (IDs):", self.conflicts_edit)
        af.addRow("Benötigt (IDs):", self.requires_edit)
        adv.setVisible(False)
        adv_btn.clicked.connect(lambda: (adv.setVisible(not adv.isVisible()),
                                         adv_btn.setText("Erweitert ausblenden" if adv.isVisible()
                                                         else "Erweitert anzeigen")))
        adv_row = QHBoxLayout()
        adv_row.addWidget(adv_btn)
        adv_row.addStretch()
        form.addRow("", adv_row)
        form.addRow(adv)
        self.tabs.insertTab(0, w, "Allgemein")
        self._load_titles()

    def _load_titles(self) -> None:
        self.title_edit.setText(self.module.title.get(self.lang, ""))
        self.title_edit.setPlaceholderText(tr(self.module.title, self.lang)[0])
        self.component_edit.setText(self.module.component.get(self.lang, ""))

    def _store_titles(self) -> None:
        for field_, edit in ((self.module.title, self.title_edit),
                             (self.module.component, self.component_edit)):
            text = edit.text().strip()
            if text:
                field_[self.lang] = text
            else:
                field_.pop(self.lang, None)

    def _lang_changed(self) -> None:
        self._store_titles()
        for t in self.tables.values():
            t.store(self.lang)
        self.lang = self.lang_box.currentData()
        self._load_titles()
        for t in self.tables.values():
            t.load(self.lang)

    # ---------------------------------------------------------------- save
    def save(self) -> None:
        self._store_titles()
        if not self.module.title:
            QMessageBox.warning(self, "Titel fehlt", "Bitte einen Titel eingeben.")
            return
        m = self.module
        m.slot = self.slot_box.currentData()
        m.kind = self.kind_box.currentData()
        m.description = self.desc_edit.toPlainText().strip()
        m.conflicts = [x.strip() for x in self.conflicts_edit.text().split(",") if x.strip()]
        m.requires = [x.strip() for x in self.requires_edit.text().split(",") if x.strip()]
        changed_data = False
        for section, t in self.tables.items():
            t.store(self.lang)
            entries = [e for e in t.entries if any(v not in (None, "", {}) for v in e.values())]
            if entries != m.entries(section):
                changed_data = True
            m.data[section] = entries
        if changed_data:
            m.add_history("; ".join(self.checked_notes) if self.checked_notes else "Tabellen bearbeitet")
        m.save_meta()
        m.save_data()
        self.accept()
