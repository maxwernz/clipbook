"""Render packaging/icon/app_icon.svg into all icon files (run after changing the SVG).

    uv run python tools/make_icons.py
Writes packaging/icon/app_icon.icns (macOS), app_icon.ico (Windows), app_icon.png (1024)
and src/clipbook/gui/assets/app_icon.png (256, window icon).
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image  # noqa: E402
from PySide6.QtCore import QByteArray, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "packaging" / "icon"


def render(svg: bytes, size: int) -> Image.Image:
    img = QImage(size, size, QImage.Format.Format_RGBA8888)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    QSvgRenderer(QByteArray(svg)).render(p, QRectF(0, 0, size, size))
    p.end()
    return Image.frombuffer("RGBA", (size, size), bytes(img.constBits()), "raw", "RGBA", 0, 1).copy()


def main() -> None:
    QApplication.instance() or QApplication(sys.argv)
    svg = (ICON / "app_icon.svg").read_bytes()
    big = render(svg, 1024)
    big.save(ICON / "app_icon.png")
    # each size rendered from the vector, not scaled down -> sharp small icons
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = {s: render(svg, s) for s in ico_sizes}
    frames[256].save(ICON / "app_icon.ico", format="ICO", sizes=[(s, s) for s in ico_sizes],
                     append_images=[frames[s] for s in ico_sizes[:-1]])
    big.save(ICON / "app_icon.icns", format="ICNS")
    frames[256].save(ROOT / "src" / "clipbook" / "gui" / "assets" / "app_icon.png")
    print("icons written to", ICON)


if __name__ == "__main__":
    main()
