"""Create a private tester ZIP; never upload its confidential contents to GitHub.

Run after exporting the example panel and downloading the release installers:
  uv run python tools/prepare_handoff.py --library ../Anleitungs-Bibliothek \
      --panel /path/to/SKT_H10_Beispiel_Panel --installers release/0.3.0
Output lives in the git-ignored release/ directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library", type=Path, required=True)
    ap.add_argument("--panel", type=Path, required=True)
    ap.add_argument("--installers", type=Path)
    args = ap.parse_args()
    from clipbook import __version__
    from clipbook.library import Library, Machine

    lib = Library(args.library)
    machine_file = lib.machines_dir / "skt-h10-beispiel.yaml"
    machine = Machine.load(machine_file)
    assert not [i for i in lib.validate(machine) if i.level == "error"]
    for name in ("index.html", "app.js", "style.css", "data.js", "img"):
        if not (args.panel / name).exists():
            raise SystemExit(f"Incomplete panel export: {name}")
    folder = ROOT / "release" / f"Clipbook-{__version__}-Testpaket"
    if folder.exists():
        raise SystemExit(f"Already exists: {folder}; choose a fresh output before rebuilding")
    folder.mkdir(parents=True)
    library = folder / "Anleitungs-Bibliothek"
    library.mkdir()
    for name in ("library.yaml", "SEED_REPORT.md"):
        shutil.copy2(args.library / name, library / name)
    for name in ("modules", "templates"):
        shutil.copytree(args.library / name, library / name,
                        ignore=shutil.ignore_patterns("archive", ".DS_Store", "~$*", ".git"))
    (library / "machines").mkdir()
    shutil.copy2(machine_file, library / "machines" / machine_file.name)
    shutil.copytree(args.panel, folder / "Panel" / args.panel.name)
    shutil.copy2(ROOT / "docs" / "Kurzanleitung.html", folder / "START-HIER.html")
    (folder / "START-HIER.txt").write_text(
        f"Clipbook {__version__} – Testpaket\n\n"
        "1. ZIP vollständig entpacken.\n"
        "2. START-HIER.html im Browser öffnen (Installation und Testablauf).\n"
        "3. Panel sofort testen: Panel/SKT_H10_Beispiel_Panel/index.html öffnen.\n"
        "4. App installieren, Bibliothek öffnen → Anleitungs-Bibliothek wählen.\n\n"
        "Die Bibliothek ist eine unabhängige Testkopie. Fachliche Entwürfe sind markiert.\n"
        "Keine freigegebene Betriebsanleitung. Nur intern an Testpersonen weitergeben.\n",
        encoding="utf-8")
    # A portable content package is useful when installers are sent as download links.
    data_zip = shutil.make_archive(str(folder) + "-Daten", "zip", folder.parent, folder.name)
    if args.installers:
        files = sorted([*args.installers.glob("*-Setup.exe"), *args.installers.glob("*.dmg")])
        if len(files) != 3:
            raise SystemExit("Expected Windows setup and both macOS DMGs")
        installers = folder / "Installer"
        installers.mkdir()
        for file in files:
            shutil.copy2(file, installers / file.name)
    checksums = {}
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            checksums[str(p.relative_to(folder))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (folder / "Pruefsummen.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    archive = shutil.make_archive(str(folder), "zip", folder.parent, folder.name)
    for path in (data_zip, archive):
        print(f"{path} ({Path(path).stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
