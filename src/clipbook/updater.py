"""Self-update: find, download, verify and install new versions.

An update source ("feed") is a folder or web address containing ``latest.json``:

    {
      "version": "0.3.0",
      "released": "2026-11-02",
      "notes": "- Neue Funktion …",
      "assets": {
        "windows-x64":  {"file": "Clipbook-0.3.0-Setup.exe", "sha256": "…", "size": 123},
        "macos-arm64":  {"file": "Clipbook-0.3.0-macOS-arm64.zip", "sha256": "…", "size": 123}
      }
    }

``file`` is relative to latest.json (or a full URL). Sources are tried in this order:
  1. the address set on this computer (Einstellungen)
  2. ``update_feed`` in library.yaml (set once for everybody)
  3. the folder ``updates/`` inside the library (e.g. on the network drive)
  4. the GitHub release of the project (only reachable if the repository is public)

Installing:
  Windows  the downloaded Setup.exe runs silently (per user, no admin rights), then restarts the app
  macOS    the new .app replaces the running one after the app has quit, then it is reopened
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import APP_NAME, GITHUB_REPO, __version__

log = logging.getLogger("clipbook.update")

GITHUB_FEED = f"https://github.com/{GITHUB_REPO}/releases/latest/download/latest.json"
TIMEOUT = 15


class UpdateError(RuntimeError):
    """Error with a message that can be shown to the user as is."""


# ---------------------------------------------------------------- versions / platform

def parse_version(v: str) -> tuple:
    parts = []
    for p in str(v).strip().lstrip("vV").split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def platform_key() -> str:
    machine = platform.machine().lower()
    if sys.platform == "win32":
        return "windows-arm64" if machine in ("arm64", "aarch64") else "windows-x64"
    if sys.platform == "darwin":
        return "macos-arm64" if machine in ("arm64", "aarch64") else "macos-x86_64"
    return f"linux-{machine}"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_bundle() -> Path | None:
    """macOS: the running .app; Windows: the installation folder."""
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for parent in exe.parents:
            if parent.suffix == ".app":
                return parent
        return None
    return exe.parent


def can_self_update() -> tuple[bool, str]:
    """(possible, reason if not)."""
    if not is_frozen():
        return False, "Entwicklungsversion – Updates gibt es nur in der installierten App."
    if sys.platform == "darwin":
        if app_bundle() is None:
            return False, "App-Paket nicht gefunden."
        return True, ""
    if sys.platform == "win32":
        if not (app_bundle() / "unins000.exe").exists():
            return False, ("Die App wurde nicht mit dem Installationsprogramm installiert. "
                           "Bitte die neue Version einmal mit Setup installieren.")
        return True, ""
    return False, "Automatische Updates gibt es nur für Windows und macOS."


# ---------------------------------------------------------------- sources

def feed_candidates(device_feed: str = "", library=None) -> list[str]:
    out: list[str] = []
    if device_feed.strip():
        out.append(device_feed.strip())
    if library is not None:
        cfg = (library.config.get("update_feed") or "").strip()
        if cfg:
            out.append(cfg)
        out.append(str(library.root / "updates"))
    out.append(GITHUB_FEED)
    seen, unique = set(), []
    for f in out:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique


def _is_url(s: str) -> bool:
    return s.lower().startswith(("http://", "https://"))


def manifest_location(feed: str) -> str:
    if feed.lower().endswith(".json"):
        return feed
    if _is_url(feed):
        return feed.rstrip("/") + "/latest.json"
    return str(Path(feed).expanduser() / "latest.json")


def _ssl_context() -> ssl.SSLContext:
    try:  # use the operating system's certificates (works behind company proxies)
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            return ssl.create_default_context()


def _open_url(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{__version__}"})
    return urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_context())


# ---------------------------------------------------------------- manifest

@dataclass
class Release:
    version: str
    notes: str
    released: str
    source: str               # where latest.json was found
    asset_location: str       # path or URL of the installer for this computer
    sha256: str
    size: int
    extra: dict = field(default_factory=dict)

    @property
    def filename(self) -> str:
        return Path(urllib.parse.urlparse(self.asset_location).path).name if _is_url(self.asset_location) \
            else Path(self.asset_location).name


def read_manifest(feed: str) -> tuple[dict, str]:
    loc = manifest_location(feed)
    try:
        if _is_url(loc):
            with _open_url(loc) as r:
                data = r.read(1_000_000)
        else:
            p = Path(loc)
            if not p.exists():
                raise UpdateError(f"Keine Update-Informationen gefunden ({loc})")
            data = p.read_bytes()
    except UpdateError:
        raise
    except Exception as e:
        raise UpdateError(f"Update-Quelle nicht erreichbar ({loc}): {e}") from e
    try:
        manifest = json.loads(data.decode("utf-8"))
        if not isinstance(manifest, dict) or "version" not in manifest:
            raise ValueError("Feld 'version' fehlt")
    except Exception as e:
        raise UpdateError(f"Update-Informationen sind ungültig ({loc}): {e}") from e
    return manifest, loc


def release_from_manifest(manifest: dict, loc: str, key: str | None = None) -> Release | None:
    key = key or platform_key()
    asset = (manifest.get("assets") or {}).get(key)
    if not asset:
        return None
    file = asset.get("file") or asset.get("url") or ""
    if _is_url(file) or Path(file).is_absolute():
        location = file
    elif _is_url(loc):
        location = urllib.parse.urljoin(loc, urllib.parse.quote(file))
    else:
        location = str(Path(loc).parent / file)
    return Release(version=str(manifest["version"]), notes=str(manifest.get("notes") or "").strip(),
                   released=str(manifest.get("released") or ""), source=loc, asset_location=location,
                   sha256=str(asset.get("sha256") or "").lower(), size=int(asset.get("size") or 0))


@dataclass
class CheckResult:
    release: Release | None        # newer version for this computer, or None
    latest: str | None             # newest version seen anywhere
    source: str | None             # where it was found
    errors: list[str]


def check(feeds: list[str], current: str = __version__) -> CheckResult:
    """Ask all sources; the newest version that has a file for this computer wins."""
    best: Release | None = None
    latest, source, errors = None, None, []
    for feed in feeds:
        try:
            manifest, loc = read_manifest(feed)
        except UpdateError as e:
            errors.append(str(e))
            log.info("Update-Quelle übersprungen: %s", e)
            continue
        v = str(manifest["version"])
        if latest is None or parse_version(v) > parse_version(latest):
            latest, source = v, loc
        rel = release_from_manifest(manifest, loc)
        if rel and is_newer(rel.version, current) and (best is None or is_newer(rel.version, best.version)):
            best = rel
    log.info("Update-Prüfung: aktuell %s, neueste %s, für diesen Rechner %s",
             current, latest, best.version if best else "-")
    return CheckResult(best, latest, source, errors)


# ---------------------------------------------------------------- download

Progress = Callable[[int, int], None]   # (bytes done, bytes total)


def download(rel: Release, dest_dir: Path, progress: Progress | None = None,
             cancelled: Callable[[], bool] | None = None) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / rel.filename
    part = target.with_suffix(target.suffix + ".part")
    h = hashlib.sha256()
    done = 0
    total = rel.size
    try:
        if _is_url(rel.asset_location):
            src = _open_url(rel.asset_location)
            total = total or int(src.headers.get("Content-Length") or 0)
        else:
            p = Path(rel.asset_location)
            if not p.exists():
                raise UpdateError(f"Installationsdatei fehlt: {p}")
            total = total or p.stat().st_size
            src = p.open("rb")
        with src, part.open("wb") as out:
            while True:
                if cancelled and cancelled():
                    raise UpdateError("Abgebrochen")
                chunk = src.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    except Exception as e:
        part.unlink(missing_ok=True)
        raise UpdateError(f"Download fehlgeschlagen: {e}") from e
    if rel.size and done != rel.size:
        part.unlink(missing_ok=True)
        raise UpdateError(f"Download unvollständig ({done} von {rel.size} Bytes)")
    if rel.sha256 and h.hexdigest() != rel.sha256:
        part.unlink(missing_ok=True)
        raise UpdateError("Prüfsumme stimmt nicht – die Datei ist beschädigt oder unvollständig.")
    if not rel.sha256:
        log.warning("Update ohne Prüfsumme: %s", rel.asset_location)
    part.replace(target)
    log.info("Update geladen: %s (%d Bytes, sha256 ok)", target, done)
    return target


# ---------------------------------------------------------------- install

def _detached(cmd: list[str]) -> None:
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                    "close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def install(package: Path, relaunch: bool = True) -> None:
    """Start the installation. The caller must quit the app right afterwards."""
    ok, reason = can_self_update()
    if not ok:
        raise UpdateError(reason)
    if sys.platform == "win32":
        _install_windows(package)
    elif sys.platform == "darwin":
        _install_macos(package, relaunch)


def _install_windows(setup: Path) -> None:
    logfile = Path(tempfile.gettempdir()) / f"{APP_NAME}-update.log"
    # Inno Setup: silent, per user; the setup's [Run] entry starts the new version afterwards
    _detached([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
               f"/LOG={logfile}"])
    log.info("Windows-Setup gestartet: %s", setup)


_MAC_SCRIPT = r'''#!/bin/bash
# replaces the app bundle after the running app has quit, then reopens it.
# TARGET is OLD, or OLD's folder + the new app's name if the app was renamed.
PID="$1"; OLD="$2"; NEW="$3"; RELAUNCH="$4"; LOG="$5"; WORK="$6"; TARGET="${7:-$2}"
exec >>"$LOG" 2>&1
echo "$(date) update: waiting for $PID"
for i in $(seq 1 600); do kill -0 "$PID" 2>/dev/null || break; sleep 0.2; done
swap() {
  set -e
  BAK="${OLD%.app}.update-old.app"
  rm -rf "$BAK"
  [ "$TARGET" != "$OLD" ] && rm -rf "$TARGET"
  mv "$OLD" "$BAK"
  if ! mv "$NEW" "$TARGET"; then mv "$BAK" "$OLD"; exit 1; fi
  rm -rf "$BAK"
  xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null || true
}
if [ -w "$(dirname "$OLD")" ] && [ -w "$OLD" ]; then
  ( swap ) || { echo "$(date) update: swap failed"; TARGET="$OLD"; }
else
  echo "$(date) update: asking for administrator rights"
  /usr/bin/osascript -e "do shell script \"/bin/bash '$WORK/swap.sh' '$OLD' '$NEW' '$TARGET'\" with administrator privileges" \
    || { echo "$(date) update: cancelled or failed"; TARGET="$OLD"; }
fi
touch "$TARGET"
[ "$RELAUNCH" = "1" ] && /usr/bin/open "$TARGET"
rm -rf "$WORK"
echo "$(date) update: done"
'''

_MAC_SWAP = r'''#!/bin/bash
set -e
OLD="$1"; NEW="$2"; TARGET="${3:-$1}"; BAK="${OLD%.app}.update-old.app"
rm -rf "$BAK"
[ "$TARGET" != "$OLD" ] && rm -rf "$TARGET"
mv "$OLD" "$BAK"
if ! mv "$NEW" "$TARGET"; then mv "$BAK" "$OLD"; exit 1; fi
rm -rf "$BAK"
xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null || true
'''


def prepare_macos(zip_path: Path, work: Path) -> Path:
    """Unpack the zip (keeping signatures and symlinks) and check the new app."""
    staging = work / "new"
    staging.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["/usr/bin/ditto", "-x", "-k", str(zip_path), str(staging)], capture_output=True, text=True)
    if r.returncode != 0:
        raise UpdateError(f"Update konnte nicht entpackt werden: {r.stderr.strip()}")
    apps = list(staging.glob("*.app"))
    if len(apps) != 1:
        raise UpdateError("Im Update wurde keine App gefunden.")
    new_app = apps[0]
    r = subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(new_app)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise UpdateError(f"Die Signatur des Updates ist ungültig: {r.stderr.strip()[:300]}")
    return new_app


def _install_macos(zip_path: Path, relaunch: bool) -> None:
    old = app_bundle()
    work = Path(tempfile.mkdtemp(prefix="clipbook-update-"))
    new_app = prepare_macos(zip_path, work)
    script = work / "update.sh"
    script.write_text(_MAC_SCRIPT, encoding="utf-8")
    (work / "swap.sh").write_text(_MAC_SWAP, encoding="utf-8")
    from .logsetup import log_dir
    target = old.parent / new_app.name      # differs from old only if the app was renamed
    _detached(["/bin/bash", str(script), str(os.getpid()), str(old), str(new_app),
               "1" if relaunch else "0", str(log_dir() / "update.log"), str(work), str(target)])
    log.info("macOS-Update vorbereitet: %s -> %s", new_app, target)
