# Clipbook

Desktop app (macOS + Windows) that assembles Profil-Clip operating manuals from Word modules
("Bausteine"). You pick the parts of a machine; the app merges the matching `.docx` files into one
manual, numbers all chapters, builds the table of contents and the page numbers, and exports DOCX + PDF.

Everything happens in one window:

- **Maschinen** (left): all machine configurations; click to switch, `+` to add, `⋯` to rename/duplicate/delete.
- **Bibliothek** (middle): the building blocks as tiles, grouped by component (Dosierung, Folie, Clipper …),
  each group with its own icon and color. A green check marks tiles that are already in the manual.
- **Anleitung** (right): the manual as chapter tiles with live chapter numbers. Drag tiles in from the
  library, drag to reorder, drag back to the library (or `×`) to remove. Only one variant per component
  (e.g. one clipper): dropping another one replaces it. `Ctrl+Z` undoes. Changes save automatically.
- Header: machine name, language (DE/EN/IT) and **PDF erstellen**.

Each module is self-contained: its text (Word) **plus** structured tables for maintenance, wear/spare
parts and fault codes. These tables are printed in the module's own chapter, and also combined into a
machine-wide maintenance plan, parts list and fault-code overview with page references. A machine
without a printer therefore doesn't list printer faults.

## Quick start (development)

```bash
uv sync
uv run clipbook                       # GUI (asks for the library on first start)
uv run clipbook -l ../Anleitungs-Bibliothek build skt-h10-beispiel -o ~/Desktop/out
uv run clipbook -l ../Anleitungs-Bibliothek panel skt-h10-beispiel -o ~/Desktop/out   # HMI panel (HTML)
uv run pytest
```

For TOC/page numbers and the PDF, one of these must be installed:

| Engine | Used for | Notes |
|---|---|---|
| Microsoft Word (Windows) | DOCX + PDF | best fidelity, COM automation via pywin32 |
| Microsoft Word (macOS) | DOCX + PDF | AppleScript; first run asks for permission to control Word |
| LibreOffice | PDF | DOCX is delivered as generated; Word refreshes TOC/page numbers on open |
| none | DOCX only | Word asks "update fields?" on open |

"Automatisch" (auto) tries Word first, then LibreOffice.

## Panel manual (HMI)

**Panel** (next to "PDF erstellen") writes `<machine>_Panel/`: an offline HTML manual for the 10" Siemens
Unified Comfort Panel, all languages in one folder. Each module becomes a tile, its Word chapters become
pages split at the headings and, on the panel, into screens that fit without scrolling (text left,
picture right), and faults, maintenance and spare parts come from the tables.
Pictures with text boxes and arrows from Word are rebuilt as one scalable figure (tap to enlarge).
A slot gets `panel: false` in `library.yaml` to leave it out (e.g. the CE declaration).
Details and the HMI jump addresses: [docs/Panel-HTML.md](docs/Panel-HTML.md). Code: `panel/`.

## The library

The library is a plain folder, kept **outside** this repo (e.g. on a network drive, or in its own git repo):

```
Anleitungs-Bibliothek/
  library.yaml               slots (chapter order), languages, labels, variables
  templates/master.docx      cover page, header/footer with logo, TOC, heading numbering
  modules/<id>/module.yaml   title, slot, version, change history
  modules/<id>/de.docx       text per language (en.docx, it.docx …)
  modules/<id>/data.yaml     maintenance / spare_parts / faults (translatable)
  modules/<id>/archive/      previous versions
  machines/<name>.yaml       saved machine configurations
```

It was created once from `../Bedienungsanleitungen` with `clipbook -l <dir> seed <legacy dir>`.
`SEED_REPORT.md` in the library lists how the old fault/maintenance tables were split up.

**The split is a draft, not a checked result.** The import assigned every maintenance, spare-part and
fault row to a module automatically (by fault number and keywords). Which row belongs to which assembly
has to be decided by the person responsible for the content. Until then every such row carries a
`draft:` text in `data.yaml` (what is unsure), and it is marked everywhere:

- App: orange sign on the tile; in the module dialog an "Entwurf" notice and orange rows (hover = open question)
- Check before building: a warning per module
- Word/PDF: orange rows plus the note "ENTWURF: …" below the table
- Panel: an "Entwurf" tag

Rows can be moved to another module ("In anderen Baustein verschieben"). The draft mark is only removed
with "Als geprüft markieren" once the responsible person has confirmed it; "Als Entwurf markieren"
marks any other row as an open proposal.

Rules for writing modules are in [docs/Word-Regeln.md](docs/Word-Regeln.md).

## How a build works

1. Validate the configuration (one clipper only, required chapters present, conflicts, missing translations).
2. Open `master.docx`. For each module: normalise the `.docx` (detect headings, remove typed numbers,
   fix levels) and append it with `docxcompose`, which keeps images, text boxes, lists and styles.
3. Insert the generated tables at the `{{ABSCHNITT_…}}` / `{{GESAMT_…}}` markers (or at the end of the
   module chapter), with bookmarks + `PAGEREF` fields for the fault overview.
4. Replace `{{Variablen}}` in body, header and footer.
5. Word/LibreOffice updates TOC and page fields and exports the PDF.

Code map: `normalize.py` (cleanup), `build.py` (assembly), `engines.py` (Word/LibreOffice),
`library.py` (data model), `importer.py`, `seed.py` (one-time legacy import), `gui/`.

## Reference: the old manual

`tools/render_reference.py` merges the original files in the old order without any changes
(typed chapter numbers, one big fault table), so new output can be compared with the old manual:

```bash
uv run python tools/render_reference.py ../Bedienungsanleitungen ~/ProfilClip/Referenz
```

## Releases & updates

Push a version tag; GitHub Actions builds, tests and publishes the Windows installer and the Mac apps.
Installed apps update themselves. See **[docs/Updates.md](docs/Updates.md)** (German).

```bash
uv run python tools/build_release.py                  # package for this computer (with self-test)
uv run python tools/publish_update.py --github v0.3.0 --to "<Bibliothek>/updates"
```

Icons: edit `packaging/icon/app_icon.svg`, then `uv run python tools/make_icons.py`.
