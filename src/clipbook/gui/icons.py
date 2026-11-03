"""Line icons (24×24, drawn as SVG) – identical on macOS and Windows, any color."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

import math


def _gear(teeth: int = 8, r_out: float = 10.2, r_in: float = 7.6, hole: float = 3.0) -> str:
    """A proper cog wheel: trapezoid teeth around a ring, round hole in the middle."""
    pts = []
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a = i * step - math.pi / 2
        for frac, r in ((-0.30, r_in), (-0.17, r_out), (0.17, r_out), (0.30, r_in)):
            ang = a + frac * step * 1.6
            pts.append((12 + r * math.cos(ang), 12 + r * math.sin(ang)))
    d = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + "Z"
    return f'<path d="{d}"/><circle cx="12" cy="12" r="{hole}"/>'


# {c} is replaced by the color (used for filled dots)
PATHS = {
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    "upload": '<path d="M12 15V4M7 9l5-5 5 5M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "settings": _gear(),
    "play": '<path d="M7 4.5l12 7.5-12 7.5z"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "pdf": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M8.5 16.5v-4h1.5a1.2 1.2 0 0 1 0 2.4H8.5M13 12.5v4h1a2 2 0 0 0 0-4z"/>',
    "word": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M8 12l1.3 5 1.7-4 1.7 4L14 12"/>',
    "grip": ''.join(f'<circle cx="{x}" cy="{y}" r="1.3" fill="{{c}}" stroke="none"/>'
                    for x in (9, 15) for y in (6, 12, 18)),
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    # tubular bag with clips at both ends (the Profil-Clip product)
    "machine": '<rect x="2.5" y="8" width="19" height="8" rx="4" transform="rotate(-35 12 12)"/>'
               '<path d="M20 6.4l1.9-1.3M4 17.6l-1.9 1.3"/>',
    "clip": '<path d="M18 5.5H9.5A3.5 3.5 0 0 0 6 9v6a3.5 3.5 0 0 0 3.5 3.5H18"/>',
    "phone": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "alert": '<path d="M12 3.5l9.5 17h-19z"/><path d="M12 10v4.5M12 17.5v.01"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "sort": '<path d="M8 4v16M4 8l4-4 4 4M16 20V4M12 16l4 4 4-4"/>',
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
    "chevron-right": '<path d="M9 6l6 6-6 6"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "external": '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "dots": ''.join(f'<circle cx="{x}" cy="12" r="1.5" fill="{{c}}" stroke="none"/>' for x in (5, 12, 19)),
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "table": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.01"/>',
    # component categories
    "book": '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5z"/><path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19v-3M9 7h6"/>',
    "droplet": '<path d="M12 3s-6 7-6 11a6 6 0 0 0 12 0c0-4-6-11-6-11z"/>',
    "film": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    "scissors": '<circle cx="6" cy="7" r="3"/><circle cx="6" cy="17" r="3"/><path d="M8.5 8.5L20 19M8.5 15.5L20 5"/>',
    "monitor": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "sliders": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "wrench": '<path d="M14.7 6.3a4 4 0 0 0-5.3 5.3l-5.9 5.9a1.5 1.5 0 0 0 2.1 2.1l5.9-5.9a4 4 0 0 0 5.3-5.3l-2.6 2.6-2.4-.6-.6-2.4z"/>',
    "package": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "puzzle": '<path d="M10 4a2 2 0 1 1 4 0v2h4v4h-2a2 2 0 1 0 0 4h2v4h-4v-2a2 2 0 1 0-4 0v2H6v-4h2a2 2 0 1 0 0-4H6V6h4z"/>',
}

# look of each place in the manual: (icon, color)
SLOT_STYLE = {   # colors from the Profil-Clip website palette
    "general": ("book", "#0160b2"),
    "dosing": ("droplet", "#319fc0"),
    "film": ("film", "#014d8e"),
    "clipper": ("clip", "#e07b39"),
    "control": ("monitor", "#2b7bb9"),
    "options": ("sliders", "#6c6c6c"),
    "service": ("wrench", "#d9534f"),
    "consumables": ("package", "#3f9142"),
    "ce": ("shield", "#b8890f"),
}
DEFAULT_SLOT_STYLE = ("puzzle", "#6c6c6c")


def slot_style(slot_id: str) -> tuple[str, str]:
    return SLOT_STYLE.get(slot_id, DEFAULT_SLOT_STYLE)


@lru_cache(maxsize=512)
def pixmap(name: str, color: str = "#3b4456", size: int = 18, stroke: float = 2.0) -> QPixmap:
    body = PATHS.get(name, PATHS["puzzle"]).replace("{c}", color)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    scale = 3
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pm.setDevicePixelRatio(scale)
    return pm


def icon(name: str, color: str = "#3b4456", size: int = 18) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size))
    ic.addPixmap(pixmap(name, "#a3aab8", size), QIcon.Mode.Disabled)
    return ic
