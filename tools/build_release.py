"""Build the installable app for this computer's platform.

    uv run python tools/build_release.py

macOS   → release/<version>/Clipbook-<version>-macOS-<arch>.zip   (used for updates)
          release/<version>/Clipbook-<version>-macOS-<arch>.dmg   (first installation)
Windows → release/<version>/Clipbook-<version>-Setup.exe          (installation + updates)

Each run also writes release/<version>/asset-<platform>.json (checksum, size), which
tools/publish_update.py turns into latest.json for the update source.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _stream in (sys.stdout, sys.stderr):   # Windows consoles are not UTF-8 by default
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "src"))
from clipbook import APP_NAME, __version__  # noqa: E402
from clipbook.updater import platform_key  # noqa: E402

VERSION = __version__
DIST = ROOT / "dist"
BUILD = ROOT / "build"
OUT = ROOT / "release" / VERSION


def run(cmd: list[str], **kw) -> None:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_version_consistency() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pv = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
    if pv != VERSION:
        sys.exit(f"Version passt nicht: pyproject.toml {pv} ≠ __init__.py {VERSION}")
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if tag.startswith("v") and tag[1:] != VERSION:
        sys.exit(f"Git-Tag {tag} passt nicht zur Version {VERSION}")


def windows_version_file() -> None:
    nums = [int(x) for x in re.findall(r"\d+", VERSION)[:3]] + [0]
    t = tuple(nums[:4])
    BUILD.mkdir(exist_ok=True)
    (BUILD / "version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040704b0', [
      StringStruct('CompanyName', 'Profi L-Clip GmbH'),
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', '{APP_NAME}'),
      StringStruct('LegalCopyright', '© Profi L-Clip GmbH – interne Software'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{VERSION}')])]),
        VarFileInfo([VarStruct('Translation', [1031, 1200])])]
)
""", encoding="utf-8")


def pyinstaller() -> None:
    for d in (DIST,):
        shutil.rmtree(d, ignore_errors=True)
    run([sys.executable, "-m", "PyInstaller", ROOT / "packaging" / "clipbook.spec", "--noconfirm",
         "--clean", "--distpath", DIST, "--workpath", BUILD / "pyinstaller"])


def self_test(exe: Path) -> None:
    report = BUILD / "self-test.json"
    report.unlink(missing_ok=True)
    r = subprocess.run([str(exe), "self-test", "--out", str(report)], capture_output=True, text=True, timeout=300)
    data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
    if r.returncode != 0 or not data.get("ok") or data.get("version") != VERSION:
        print(r.stdout, r.stderr)
        sys.exit(f"Selbsttest der gebauten App fehlgeschlagen: {data}")
    print("Selbsttest ok:", data["checks"])


def write_asset(platform: str, file: Path) -> None:
    info = {"version": VERSION, "platform": platform, "file": file.name, "sha256": sha256(file),
            "size": file.stat().st_size}
    (OUT / f"asset-{platform}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"→ {file.name}  ({info['size'] / 1e6:.1f} MB, sha256 {info['sha256'][:12]}…)")


def build_macos() -> None:
    app = DIST / f"{APP_NAME}.app"
    run(["codesign", "--force", "--deep", "--sign", "-", app])          # consistent ad-hoc signature
    run(["codesign", "--verify", "--deep", "--strict", app])
    self_test(app / "Contents" / "MacOS" / APP_NAME)
    arch = platform_key().split("-", 1)[1]
    base = f"{APP_NAME}-{VERSION}-macOS-{arch}"
    zip_path = OUT / f"{base}.zip"
    run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, zip_path])
    # disk image for the first installation: app + link to /Applications
    stage = BUILD / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    run(["ditto", app, stage / app.name])
    (stage / "Applications").symlink_to("/Applications")
    dmg = OUT / f"{base}.dmg"
    dmg.unlink(missing_ok=True)
    run(["hdiutil", "create", "-volname", f"{APP_NAME} {VERSION}", "-srcfolder", stage, "-ov",
         "-format", "UDZO", dmg])
    write_asset(platform_key(), zip_path)


def find_iscc() -> Path:
    candidates = [os.environ.get("ISCC", ""),
                  r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
                  r"C:\Program Files\Inno Setup 6\ISCC.exe",
                  str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe")]
    for c in candidates:
        if c and Path(c).exists():
            return Path(c)
    sys.exit("Inno Setup 6 (ISCC.exe) nicht gefunden – https://jrsoftware.org/isdl.php")


def build_windows() -> None:
    folder = DIST / APP_NAME
    self_test(folder / f"{APP_NAME}.exe")
    run([find_iscc(), f"/DAppVersion={VERSION}", f"/DSourceDir={folder}", f"/DOutputDir={OUT}",
         ROOT / "packaging" / "windows" / "installer.iss"])
    write_asset(platform_key(), OUT / f"{APP_NAME}-{VERSION}-Setup.exe")


def main() -> None:
    check_version_consistency()
    OUT.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        windows_version_file()
    pyinstaller()
    if sys.platform == "darwin":
        build_macos()
    elif sys.platform == "win32":
        build_windows()
    else:
        sys.exit("Pakete werden nur für macOS und Windows gebaut.")
    print(f"\nFertig: {OUT}")


if __name__ == "__main__":
    main()
