"""Command line: clipbook [gui|build|panel|check|import|seed|template] ..."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .library import Library, Machine


def _lib(args) -> Library:
    return Library(Path(args.library))


def cmd_build(args) -> int:
    from .build import BuildError, build_manual
    lib = _lib(args)
    machine_path = Path(args.machine)
    if not machine_path.exists():
        machine_path = lib.machines_dir / f"{args.machine}.yaml"
    machine = Machine.load(machine_path)
    if args.language:
        machine.language = args.language
    try:
        res = build_manual(lib, machine, Path(args.out), pdf=not args.no_pdf, engine=args.engine)
    except BuildError as e:
        print(e, file=sys.stderr)
        return 2
    for i in res.issues:
        print(i)
    return 0


def cmd_panel(args) -> int:
    from .build import BuildError
    from .panel.export import build_panel

    lib = _lib(args)
    machine_path = Path(args.machine)
    if not machine_path.exists():
        machine_path = lib.machines_dir / f"{args.machine}.yaml"
    machine = Machine.load(machine_path)
    try:
        res = build_panel(lib, machine, Path(args.out))
    except BuildError as e:
        print(e, file=sys.stderr)
        return 2
    for issue in res.issues:
        print(issue)
    print(res.folder)
    return 0


def cmd_check(args) -> int:
    from .importer import check
    lib = _lib(args)
    rep = check(lib, Path(args.file), kind=args.kind, title=args.title or Path(args.file).stem)
    print(rep.summary())
    return 1 if rep.errors else 0


def cmd_import(args) -> int:
    from .importer import import_file
    lib = _lib(args)
    module = lib.modules.get(args.module)
    if module is None:
        if not args.slot:
            print(f"Modul '{args.module}' existiert nicht – mit --slot und --title neu anlegen",
                  file=sys.stderr)
            return 2
        module = lib.new_module(args.module, {args.language: args.title or args.module},
                                args.slot, args.kind)
    rep = import_file(lib, Path(args.file), module, args.language, note=args.note or "")
    print(rep.summary())
    return 1 if rep.errors else 0


def cmd_seed(args) -> int:
    from .seed import seed_from_legacy
    target = Path(args.library)
    if (target / "library.yaml").exists() and not args.force:
        print(f"{target} enthält schon eine Bibliothek (--force zum Überschreiben)", file=sys.stderr)
        return 2
    if args.force and target.exists():
        import shutil
        shutil.rmtree(target)
    seed_from_legacy(Path(args.legacy), target)
    print(f"Bibliothek angelegt: {target}  (Bericht: {target / 'SEED_REPORT.md'})")
    return 0


def cmd_template(args) -> int:
    from .template import create_master_template
    create_master_template(Path(args.source), Path(args.out))
    print(f"Vorlage geschrieben: {args.out}")
    return 0


def cmd_self_test(args) -> int:
    """Checks that a packaged app is complete (used by the release pipeline)."""
    import json
    import tempfile
    import traceback

    from . import __version__
    result = {"version": __version__, "ok": False, "checks": {}}
    try:
        from .gui import style
        for name in ("Manrope.ttf", "logo.png", "app_icon.png", "clip.png"):
            result["checks"][name] = (style.ASSETS / name).exists()
        from .panel.export import TEMPLATE
        result["checks"]["panel_template"] = all((TEMPLATE / n).exists() for n in ("index.html", "app.js", "style.css"))
        import docx  # noqa: F401
        import docxcompose  # noqa: F401
        from docx import Document
        from PySide6 import QtSvg  # noqa: F401
        from PySide6.QtWidgets import QApplication  # noqa: F401
        from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
        tr = QTranslator()
        result["checks"]["translations_de"] = tr.load(
            QLocale(QLocale.Language.German), "qtbase", "_",
            QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
        from .updater import _ssl_context, platform_key
        _ssl_context()
        result["checks"]["platform"] = platform_key()
        with tempfile.TemporaryDirectory() as tmp:
            d = Document()
            d.add_paragraph("9.5 Clipper", style="Heading 2")
            d.save(Path(tmp) / "t.docx")
            from .normalize import normalize_file
            rep = normalize_file(Path(tmp) / "t.docx", kind="component", title="Clipper")
            result["checks"]["normalize"] = [h.text for h in rep.headings] == ["Clipper"]
        result["ok"] = all(v for v in result["checks"].values())
    except Exception:
        result["error"] = traceback.format_exc()
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if result["ok"] else 1


def cmd_update(args) -> int:
    from . import __version__
    from . import updater
    lib = None
    try:
        lib = Library(Path(args.library))
    except Exception:
        pass
    feeds = [args.feed] if args.feed else updater.feed_candidates("", lib)
    res = updater.check(feeds)
    print(f"installiert: {__version__}  ·  neueste: {res.latest or '–'}  ·  Quelle: {res.source or '–'}")
    for e in res.errors:
        print("  übersprungen:", e)
    if not res.release:
        print("Kein Update für diesen Rechner.")
        return 0
    print(f"Update verfügbar: {res.release.version} ({res.release.filename})")
    if args.action != "apply":
        return 0
    import tempfile
    pkg = updater.download(res.release, Path(tempfile.mkdtemp(prefix="clipbook-dl-")),
                           progress=lambda d, t: None)
    updater.install(pkg, relaunch=not args.no_relaunch)
    print("Installation gestartet – die App wird ersetzt, sobald dieser Prozess endet.")
    return 0


def main(argv: list[str] | None = None) -> int:
    from . import __version__
    argv = list(sys.argv[1:] if argv is None else argv)
    argv = [a for a in argv if not a.startswith("-psn_")]     # macOS Finder process id
    ap = argparse.ArgumentParser(prog="clipbook", description="Betriebsanleitungen aus Bausteinen bauen")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--library", "-l", default="library", help="Pfad zur Bibliothek")
    sub = ap.add_subparsers(dest="cmd")

    st = sub.add_parser("self-test", help="Prüfen, ob die installierte App vollständig ist")
    st.add_argument("--out", help="Ergebnis zusätzlich in diese Datei schreiben")

    up = sub.add_parser("update", help="Nach Updates suchen / Update installieren")
    up.add_argument("action", choices=["check", "apply"], nargs="?", default="check")
    up.add_argument("--feed", help="Update-Quelle (Ordner oder URL) statt der Standardquellen")
    up.add_argument("--no-relaunch", action="store_true")

    sub.add_parser("gui", help="Programmoberfläche starten (Standard)")

    b = sub.add_parser("build", help="Anleitung für eine Maschine erzeugen")
    b.add_argument("machine", help="Maschinen-Datei (.yaml) oder Name in library/machines")
    b.add_argument("--out", "-o", default="output")
    b.add_argument("--language")
    b.add_argument("--engine", default="auto", choices=["auto", "word", "libreoffice", "none"])
    b.add_argument("--no-pdf", action="store_true")

    pn = sub.add_parser("panel", help="Anleitung fürs HMI-Panel erzeugen (HTML-Ordner, alle Sprachen)")
    pn.add_argument("machine", help="Maschinen-Datei (.yaml) oder Name in library/machines")
    pn.add_argument("--out", "-o", default="output")

    c = sub.add_parser("check", help="Word-Datei prüfen, ohne sie zu importieren")
    c.add_argument("file")
    c.add_argument("--kind", default="component", choices=["component", "chapters"])
    c.add_argument("--title")

    i = sub.add_parser("import", help="Word-Datei als Modul (neu oder Update) importieren")
    i.add_argument("file")
    i.add_argument("module", help="Modul-ID, z. B. clipper-dcx5s")
    i.add_argument("--language", default="de")
    i.add_argument("--slot", help="nur für neue Module")
    i.add_argument("--title", help="nur für neue Module")
    i.add_argument("--kind", default="component", choices=["component", "chapters"])
    i.add_argument("--note")

    s = sub.add_parser("seed", help="Bibliothek aus den bisherigen Anleitungen anlegen")
    s.add_argument("legacy", help="Ordner 'Bedienungsanleitungen'")
    s.add_argument("--force", action="store_true")

    t = sub.add_parser("template", help="Master-Vorlage aus einer bestehenden Anleitung erzeugen")
    t.add_argument("source")
    t.add_argument("out")

    if not argv:      # double-click: start the program
        from .gui.app import run
        return run(None)
    args = ap.parse_args(argv)
    if args.cmd in (None, "gui"):
        from .gui.app import run
        return run(Path(args.library) if "--library" in argv or "-l" in argv else None)
    return {"build": cmd_build, "panel": cmd_panel, "check": cmd_check, "import": cmd_import, "seed": cmd_seed,
            "self-test": cmd_self_test, "update": cmd_update,
            "template": cmd_template}[args.cmd](args)
