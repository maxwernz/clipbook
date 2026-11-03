"""Pictures from the Word files -> img/ of the panel folder (scaled down, deduplicated)."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage

MAX_PX = 1600            # longest side; the panel is 1280 × 800, zoom view included
JPEG_QUALITY = 85
PNG_LIMIT = 350_000      # bigger PNG photos become JPEG
VECTOR = {"image/x-wmf": "wmf", "image/x-emf": "emf", "image/wmf": "wmf", "image/emf": "emf"}


class ImageStore:
    def __init__(self, folder: Path, warn=print):
        self.dir = folder / "img"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.warn = warn
        self.done: dict[str, str] = {}
        self.vector: dict[str, bytes] = {}   # name -> WMF/EMF data, converted at the end

    def __call__(self, part, rid: str | None) -> str | None:
        if not rid:
            return None
        target = part.related_parts.get(rid)
        if target is None or not hasattr(target, "blob"):
            return None
        blob = target.blob
        key = hashlib.sha1(blob).hexdigest()[:16]
        if key in self.done:
            return self.done[key]
        ctype = getattr(target, "content_type", "")
        if ctype in VECTOR:
            name = f"img/{key}.png"
            self.vector[name] = (VECTOR[ctype], blob)
        elif ctype == "image/svg+xml":
            name = f"img/{key}.svg"
            (self.dir / f"{key}.svg").write_bytes(blob)
        else:
            name = self._raster(key, blob, ctype)
        if name:
            self.done[key] = name
        return name

    def _raster(self, key: str, blob: bytes, ctype: str) -> str | None:
        img = QImage.fromData(QByteArray(blob))
        if img.isNull():
            self.warn(f"Bild ({ctype}) konnte nicht gelesen werden")
            return None
        if max(img.width(), img.height()) > MAX_PX:
            img = img.scaled(MAX_PX, MAX_PX, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        alpha = img.hasAlphaChannel()
        as_png = alpha or (ctype == "image/png" and len(blob) <= PNG_LIMIT)
        fmt, ext = ("PNG", "png") if as_png else ("JPEG", "jpg")
        if not as_png and img.format() != QImage.Format.Format_RGB32:
            img = img.convertToFormat(QImage.Format.Format_RGB32)
        buf = QByteArray()
        dev = QBuffer(buf)
        dev.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(dev, fmt, JPEG_QUALITY if fmt == "JPEG" else -1)
        dev.close()
        (self.dir / f"{key}.{ext}").write_bytes(bytes(buf.data()))
        return f"img/{key}.{ext}"

    def finish(self) -> None:
        """Convert WMF/EMF pictures with LibreOffice (browsers can't show them)."""
        if not self.vector:
            return
        from ..engines import find_libreoffice

        found = find_libreoffice()
        if not found:
            self.warn(f"{len(self.vector)} Bild(er) im Format WMF/EMF: zum Umwandeln wird LibreOffice "
                      f"gebraucht, fehlen im Panel")
            return
        with tempfile.TemporaryDirectory(prefix="panel-img-") as tmp:
            src = []
            for name, (ext, blob) in self.vector.items():
                p = Path(tmp) / f"{Path(name).stem}.{ext}"
                p.write_bytes(blob)
                src.append(str(p))
            out = Path(tmp) / "out"
            try:
                subprocess.run([str(found[0]), "--headless", "--convert-to", "png", "--outdir", str(out), *src],
                               capture_output=True, timeout=300, check=False)
            except (OSError, subprocess.TimeoutExpired) as e:
                self.warn(f"WMF/EMF-Umwandlung fehlgeschlagen: {e}")
                return
            for name in self.vector:
                png = out / Path(name).name
                if png.exists():
                    shutil.move(str(png), self.dir / png.name)
                else:
                    self.warn(f"Bild {name} (WMF/EMF) konnte nicht umgewandelt werden")
