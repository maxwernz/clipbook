"""Publish a built release to an update source (e.g. the network drive).

    uv run python tools/publish_update.py release/0.2.0 --to "/Volumes/Daten/Anleitungs-Bibliothek/updates"

Copies the installer files, then writes latest.json (all platforms of the newest version)
in one atomic step – apps never see a half-written file. Mac and Windows builds can be
published one after the other; they are merged. Older versions are removed (keeps --keep).
Release notes come from CHANGELOG.md (section of this version).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _stream in (sys.stdout, sys.stderr):   # Windows consoles are not UTF-8 by default
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "src"))
from clipbook.updater import parse_version  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def notes_for(version: str) -> str:
    log = ROOT / "CHANGELOG.md"
    if not log.exists():
        return ""
    text = log.read_text(encoding="utf-8")
    m = re.search(rf"^## \[?{re.escape(version)}\]?.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def copy_verified(src: Path, dst: Path, digest: str) -> None:
    if dst.exists() and sha256(dst) == digest:
        return
    tmp = dst.with_name(dst.name + ".part")
    shutil.copyfile(src, tmp)
    if sha256(tmp) != digest:
        tmp.unlink()
        sys.exit(f"Kopie von {src.name} ist fehlerhaft – abgebrochen")
    os.replace(tmp, dst)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("release_dirs", nargs="*", type=Path, help="release/<version> (one or more)")
    ap.add_argument("--github", metavar="TAG", help="Pakete dieser GitHub-Version laden (z. B. v0.3.0), braucht gh")
    ap.add_argument("--require", default="", help="Plattformen, die vorhanden sein müssen, z. B. windows-x64,macos-arm64")
    ap.add_argument("--to", required=True, type=Path, help="update source folder")
    ap.add_argument("--keep", type=int, default=3, help="number of versions to keep (default 3)")
    args = ap.parse_args()
    if args.github:
        import subprocess
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="clipbook-release-"))
        subprocess.run(["gh", "release", "download", args.github, "-D", str(tmp), "-p", "asset-*.json",
                        "-p", "*.zip", "-p", "*.exe"], check=True)
        args.release_dirs.append(tmp)
    if not args.release_dirs:
        sys.exit("Bitte einen release-Ordner oder --github TAG angeben")

    assets = []
    for d in args.release_dirs:
        for f in sorted(d.rglob("asset-*.json")):        # also in sub-folders (CI artifacts)
            info = json.loads(f.read_text(encoding="utf-8"))
            info["_src"] = f.parent / info["file"]
            if not info["_src"].exists() or sha256(info["_src"]) != info["sha256"]:
                sys.exit(f"{info['file']} fehlt oder passt nicht zur Prüfsumme")
            assets.append(info)
    if not assets:
        sys.exit("Keine gebauten Pakete gefunden (asset-*.json)")
    missing = [k for k in args.require.split(",") if k and k not in {a["platform"] for a in assets}]
    if missing:
        sys.exit(f"Pakete fehlen für: {', '.join(missing)}")
    versions = {a["version"] for a in assets}
    if len(versions) != 1:
        sys.exit(f"Unterschiedliche Versionen: {versions}")
    version = versions.pop()

    feed = args.to
    feed.mkdir(parents=True, exist_ok=True)
    manifest_path = feed / "latest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if parse_version(manifest.get("version", "0")) > parse_version(version):
            sys.exit(f"Die Quelle hat schon eine neuere Version ({manifest['version']})")
        if manifest.get("version") != version:
            manifest = {}

    for a in assets:
        copy_verified(a["_src"], feed / a["file"], a["sha256"])
    manifest.update({"version": version, "released": dt.date.today().isoformat(),
                     "notes": notes_for(version) or manifest.get("notes", "")})
    manifest.setdefault("assets", {})
    for a in assets:
        manifest["assets"][a["platform"]] = {"file": a["file"], "sha256": a["sha256"], "size": a["size"]}
    atomic_write(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False))

    # history + cleanup of old installers
    hist_path = feed / "versions.json"
    history = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else []
    history = [h for h in history if h["version"] != version] + [manifest]
    history.sort(key=lambda h: parse_version(h["version"]))
    keep = history[-args.keep:]
    atomic_write(hist_path, json.dumps(keep, indent=2, ensure_ascii=False))
    wanted = {a["file"] for h in keep for a in h.get("assets", {}).values()}
    for f in feed.iterdir():
        if f.is_file() and f.suffix in (".exe", ".zip", ".dmg") and f.name not in wanted:
            f.unlink()
    print(f"Veröffentlicht: Version {version} → {feed}")
    for k, a in manifest["assets"].items():
        print(f"  {k:14s} {a['file']}")


if __name__ == "__main__":
    main()
