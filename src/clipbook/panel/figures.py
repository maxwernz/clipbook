"""Word drawings (DrawingML) -> SVG, for the panel manual.

A typical figure in the modules is a photo in its own paragraph plus text boxes, lines and arrows
anchored to the same paragraph ("Holm links", red arrow …). Word places those relative to the
paragraph, so they can be put back on top of the photo here. Everything ends up in one SVG with
a viewBox in points, so labels scale together with the photo.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from functools import lru_cache

from lxml import etree

from docx.oxml.ns import qn

EMU_PER_PT = 12700
# Word size (pt) -> panel px. The Word text column (~450 pt) then fills the panel width (~1180 px);
# smaller pictures stay smaller instead of being blown up.
MAX_ZOOM = 2.6
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
}
R_EMBED = f"{{{NS['r']}}}embed"
R_ID = f"{{{NS['r']}}}id"

SCHEME = {"lt1": "#ffffff", "bg1": "#ffffff", "dk1": "#000000", "tx1": "#000000", "lt2": "#e7e6e6",
          "bg2": "#e7e6e6", "dk2": "#44546a", "tx2": "#44546a", "accent1": "#4472c4", "accent2": "#ed7d31",
          "accent3": "#a5a5a5", "accent4": "#ffc000", "accent5": "#5b9bd5", "accent6": "#70ad47"}
PRESET = {"black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
          "yellow": "#ffff00", "gray": "#808080", "grey": "#808080", "darkGray": "#a9a9a9"}

RECT_LIKE = {"rect", "roundRect", "flowChartProcess", "flowChartAlternateProcess", "snip1Rect", "plaque",
             "wedgeRectCallout", "wedgeRoundRectCallout", "borderCallout1", "callout1", "frame"}
ELLIPSE_LIKE = {"ellipse", "flowChartConnector", "donut", "wedgeEllipseCallout"}
LINE_LIKE = {"line", "straightConnector1", "bentConnector2", "bentConnector3", "curvedConnector3"}
ARROW_TYPES = {"triangle", "arrow", "stealth", "diamond", "oval"}


def find(el, path):
    return el.find(path, NS)


def findall(el, path):
    return el.findall(path, NS)


@lru_cache(maxsize=None)
def _xp(path: str) -> etree.XPath:
    return etree.XPath(path, namespaces=NS)


def xpath(el, path):
    # python-docx elements override .xpath() with their own namespace map
    return _xp(path)(el)


def color_of(el) -> str | None:
    """Color of a fill/line element (srgbClr, schemeClr, prstClr, sysClr child)."""
    if el is None:
        return None
    for child in el:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "srgbClr":
            return "#" + child.get("val", "000000").lower()
        if tag == "schemeClr":
            return SCHEME.get(child.get("val"), "#808080")
        if tag == "prstClr":
            return PRESET.get(child.get("val"), "#000000")
        if tag == "sysClr":
            return "#" + (child.get("lastClr") or "000000").lower()
    return None


# ---------------------------------------------------------------- model

@dataclass
class Item:
    """One element of a figure, in points relative to the figure origin."""
    kind: str                 # image | rect | ellipse | line | path | text
    x: float
    y: float
    w: float
    h: float
    rot: float = 0.0
    flip_h: bool = False
    flip_v: bool = False
    src: str = ""             # image file name
    crop: tuple[float, float, float, float] = (0, 0, 0, 0)  # l, t, r, b in fractions
    fill: str | None = None
    stroke: str | None = None
    stroke_w: float = 0.75
    dash: bool = False
    head: str | None = None   # arrow at the path start
    tail: str | None = None   # arrow at the path end
    path: str = ""            # SVG path in 0..1 coordinates (custom geometry)
    text_html: str = ""
    insets: tuple[float, float, float, float] = (7.2, 3.6, 7.2, 3.6)  # l, t, r, b
    v_anchor: str = "t"
    preset: str = ""
    z: tuple[int, int] = (1, 0)  # (layer: 0 behind text, 1 in line, 2 in front; Word's relativeHeight)


@dataclass
class Figure:
    items: list[Item] = field(default_factory=list)

    def bbox(self) -> tuple[float, float, float, float]:
        xs, ys, xe, ye = [], [], [], []
        for it in self.items:
            pad = it.stroke_w if it.kind in ("line", "path") else 0
            xs.append(it.x - pad)
            ys.append(it.y - pad)
            xe.append(it.x + it.w + pad)
            ye.append(it.y + it.h + pad)
        return min(xs), min(ys), max(xe), max(ye)

    @property
    def has_overlay(self) -> bool:
        return any(it.kind != "image" for it in self.items)

    @property
    def images(self) -> list[Item]:
        return [it for it in self.items if it.kind == "image"]


# ---------------------------------------------------------------- reading DrawingML

class ShapeReader:
    """Turns wp:inline / wp:anchor content into Items. `images` stores picture parts and returns
    a file name; `text` renders the paragraphs of a text box to HTML."""

    def __init__(self, part, images, text, warn):
        self.part = part
        self.images = images
        self.text = text
        self.warn = warn
        self.skipped: set[str] = set()

    def read(self, graphic_data, x: float, y: float, w: float, h: float) -> list[Item]:
        out: list[Item] = []
        for child in graphic_data:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "pic":
                it = self._picture(child, x, y, w, h)
                if it:
                    out.append(it)
            elif tag == "wsp":
                out += self._shape(child, x, y, w, h)
            elif tag == "wgp":
                out += self._group(child, x, y, w, h)
            elif tag == "wpc":  # drawing canvas: children positioned in canvas coordinates
                out += self._group_children(child, None, x, y, w, h)
            else:
                self.skipped.add(tag)
        return out

    def _picture(self, pic, x, y, w, h) -> Item | None:
        blip = find(pic, ".//a:blip")
        if blip is None or not blip.get(R_EMBED):
            return None
        src = self.images(self.part, blip.get(R_EMBED))
        if not src:
            return None
        crop = (0, 0, 0, 0)
        rect = find(pic, ".//a:srcRect")
        if rect is not None:
            crop = tuple(int(rect.get(k, 0)) / 100000 for k in ("l", "t", "r", "b"))
        it = Item("image", x, y, w, h, src=src, crop=crop)
        self._xfrm(find(pic, "pic:spPr/a:xfrm"), it)
        return it

    def _group(self, grp, x, y, w, h) -> list[Item]:
        xfrm = find(grp, "wpg:grpSpPr/a:xfrm")
        return self._group_children(grp, xfrm, x, y, w, h)

    def _group_children(self, grp, xfrm, x, y, w, h) -> list[Item]:
        ch_off = find(xfrm, "a:chOff") if xfrm is not None else None
        ch_ext = find(xfrm, "a:chExt") if xfrm is not None else None
        cx0 = int(ch_off.get("x", 0)) if ch_off is not None else 0
        cy0 = int(ch_off.get("y", 0)) if ch_off is not None else 0
        cw = int(ch_ext.get("cx", 0)) if ch_ext is not None else 0
        ch = int(ch_ext.get("cy", 0)) if ch_ext is not None else 0
        sx = w / (cw / EMU_PER_PT) if cw else 1
        sy = h / (ch / EMU_PER_PT) if ch else 1
        out: list[Item] = []
        for child in grp:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag not in ("wsp", "pic", "grpSp", "wgp"):
                continue
            cx = find(child, ".//a:xfrm")
            off, ext = (find(cx, "a:off"), find(cx, "a:ext")) if cx is not None else (None, None)
            if off is None or ext is None:
                continue
            ix = x + (int(off.get("x", 0)) - cx0) / EMU_PER_PT * sx
            iy = y + (int(off.get("y", 0)) - cy0) / EMU_PER_PT * sy
            iw = int(ext.get("cx", 0)) / EMU_PER_PT * sx
            ih = int(ext.get("cy", 0)) / EMU_PER_PT * sy
            if tag == "pic":
                it = self._picture(child, ix, iy, iw, ih)
                out += [it] if it else []
            elif tag == "wsp":
                out += self._shape(child, ix, iy, iw, ih)
            else:  # nested group
                out += self._group_children(child, find(child, "wpg:grpSpPr/a:xfrm"), ix, iy, iw, ih)
        return out

    @staticmethod
    def _xfrm(xfrm, it: Item) -> None:
        if xfrm is None:
            return
        it.rot = int(xfrm.get("rot", 0)) / 60000
        it.flip_h = xfrm.get("flipH") in ("1", "true")
        it.flip_v = xfrm.get("flipV") in ("1", "true")

    def _shape(self, wsp, x, y, w, h) -> list[Item]:
        sp = find(wsp, "wps:spPr")
        style = find(wsp, "wps:style")
        prst = find(sp, "a:prstGeom") if sp is not None else None
        cust = find(sp, "a:custGeom") if sp is not None else None
        geom = prst.get("prst") if prst is not None else ("custom" if cust is not None else "rect")
        txbx = find(wsp, "wps:txbx/w:txbxContent")

        if geom in LINE_LIKE:
            kind = "line"
        elif geom == "custom":
            kind = "path"
        elif geom in ELLIPSE_LIKE:
            kind = "ellipse"
        elif geom in RECT_LIKE or geom in _ARROW_POLYS:
            kind = "rect" if geom in RECT_LIKE else "path"
        else:
            kind = "rect" if txbx is not None else ""
            if not kind:
                self.skipped.add(geom)
                return []

        it = Item(kind, x, y, w, h, preset=geom)
        self._xfrm(find(sp, "a:xfrm") if sp is not None else None, it)

        # fill
        fill_el = None
        if sp is not None:
            if find(sp, "a:noFill") is not None:
                it.fill = None
            elif (fill_el := find(sp, "a:solidFill")) is not None:
                it.fill = color_of(fill_el)
            elif style is not None and find(style, "a:fillRef") is not None \
                    and find(style, "a:fillRef").get("idx") not in ("0", None):
                it.fill = color_of(find(style, "a:fillRef"))
        # line
        ln = find(sp, "a:ln") if sp is not None else None
        hidden_line = ln is not None and find(ln, "a:noFill") is not None
        if ln is not None:
            if hidden_line:
                it.stroke = None
            else:
                it.stroke = color_of(find(ln, "a:solidFill"))
                if it.stroke is None and style is not None and find(style, "a:lnRef") is not None:
                    it.stroke = color_of(find(style, "a:lnRef"))
                it.stroke = it.stroke or "#000000"
            if ln.get("w"):
                it.stroke_w = int(ln.get("w")) / EMU_PER_PT
            dash = find(ln, "a:prstDash")
            it.dash = dash is not None and dash.get("val") not in ("solid", None)
            for end, attr in (("a:headEnd", "head"), ("a:tailEnd", "tail")):
                e = find(ln, end)
                if e is not None and e.get("type") in ARROW_TYPES:
                    setattr(it, attr, e.get("type"))
        elif style is not None and find(style, "a:lnRef") is not None \
                and find(style, "a:lnRef").get("idx") not in ("0", None):
            it.stroke = color_of(find(style, "a:lnRef")) or "#000000"

        if kind == "path":
            it.path = _custom_path(cust) if cust is not None else _ARROW_POLYS[geom]
            if not it.path:
                self.skipped.add("custGeom")
                return []
            if it.fill is None and it.stroke is None and not hidden_line:
                it.stroke = "#000000"
        if kind in ("line", "path") and it.fill is None and it.stroke is None and not it.text_html:
            return []  # invisible shape
        if kind == "line" and it.stroke is None:
            it.stroke = "#000000"

        if txbx is not None:
            it.text_html = self.text(txbx)
            body = find(wsp, "wps:bodyPr")
            if body is not None:
                ins = [int(body.get(k, d)) / EMU_PER_PT for k, d in
                       (("lIns", 91440), ("tIns", 45720), ("rIns", 91440), ("bIns", 45720))]
                it.insets = tuple(ins)
                it.v_anchor = body.get("anchor", "t")
        return [it]


def _custom_path(cust) -> str:
    """custGeom path list -> SVG path in 0..1 coordinates of the shape box."""
    out = []
    for path in findall(cust, "a:pathLst/a:path"):
        pw = float(path.get("w") or 0) or 1.0
        ph = float(path.get("h") or 0) or 1.0

        def pt(p):
            return f"{float(p.get('x', 0)) / pw:.4f} {float(p.get('y', 0)) / ph:.4f}"

        for cmd in path:
            tag = cmd.tag.rsplit("}", 1)[-1]
            pts = findall(cmd, "a:pt")
            if tag == "moveTo" and pts:
                out.append("M" + pt(pts[0]))
            elif tag == "lnTo" and pts:
                out.append("L" + pt(pts[0]))
            elif tag == "cubicBezTo" and len(pts) == 3:
                out.append("C" + " ".join(pt(p) for p in pts))
            elif tag == "quadBezTo" and len(pts) == 2:
                out.append("Q" + " ".join(pt(p) for p in pts))
            elif tag == "close":
                out.append("Z")
    return " ".join(out)


# simple block arrows (default adjust values), 0..1 coordinates
_ARROW_POLYS = {
    "rightArrow": "M0 .25 L.6 .25 L.6 0 L1 .5 L.6 1 L.6 .75 L0 .75 Z",
    "leftArrow": "M1 .25 L.4 .25 L.4 0 L0 .5 L.4 1 L.4 .75 L1 .75 Z",
    "upArrow": "M.25 1 L.25 .4 L0 .4 L.5 0 L1 .4 L.75 .4 L.75 1 Z",
    "downArrow": "M.25 0 L.25 .6 L0 .6 L.5 1 L1 .6 L.75 .6 L.75 0 Z",
    "leftRightArrow": "M0 .5 L.25 0 L.25 .25 L.75 .25 L.75 0 L1 .5 L.75 1 L.75 .75 L.25 .75 L.25 1 Z",
    "upDownArrow": "M.5 0 L1 .25 L.75 .25 L.75 .75 L1 .75 L.5 1 L0 .75 L.25 .75 L.25 .25 L0 .25 Z",
    "circularArrow": "M.15 .6 A.36 .36 0 1 1 .78 .78 M.66 .72 L.8 .8 L.84 .63",
}


# ---------------------------------------------------------------- SVG output

def _num(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def figure_svg(fig: Figure, uid: str) -> str:
    x0, y0, x1, y1 = fig.bbox()
    w, h = x1 - x0, y1 - y0
    markers: dict[tuple[str, str], str] = {}
    parts: list[str] = []

    def marker(kind: str, color: str) -> str:
        key = (kind, color)
        if key not in markers:
            markers[key] = f"{uid}m{len(markers)}"
        return markers[key]

    for it in sorted(fig.items, key=lambda i: i.z):
        cx, cy = it.x + it.w / 2, it.y + it.h / 2
        tf = []
        if it.rot:
            tf.append(f"rotate({_num(it.rot)} {_num(cx)} {_num(cy)})")
        if it.flip_h or it.flip_v:
            tf.append(f"translate({_num(cx)} {_num(cy)}) scale({-1 if it.flip_h else 1} {-1 if it.flip_v else 1}) "
                      f"translate({_num(-cx)} {_num(-cy)})")
        transform = f' transform="{" ".join(tf)}"' if tf else ""
        stroke = (f' stroke="{it.stroke}" stroke-width="{_num(it.stroke_w)}"'
                  + (' stroke-dasharray="4 3"' if it.dash else "")) if it.stroke else ' stroke="none"'
        fill = f' fill="{it.fill}"' if it.fill else ' fill="none"'

        if it.kind == "image":
            l, t, r, b = it.crop
            vw, vh = max(1 - l - r, 0.01), max(1 - t - b, 0.01)
            parts.append(f'<svg x="{_num(it.x)}" y="{_num(it.y)}" width="{_num(it.w)}" height="{_num(it.h)}" '
                         f'viewBox="{l:.4f} {t:.4f} {vw:.4f} {vh:.4f}" preserveAspectRatio="none"{transform}>'
                         f'<image href="{html.escape(it.src)}" width="1" height="1" preserveAspectRatio="none"/></svg>')
        elif it.kind == "rect":
            if it.fill or it.stroke:
                rx = min(it.w, it.h) * 0.15 if it.preset == "roundRect" else 0
                parts.append(f'<rect x="{_num(it.x)}" y="{_num(it.y)}" width="{_num(it.w)}" height="{_num(it.h)}" '
                             f'rx="{_num(rx)}"{fill}{stroke}{transform}/>')
        elif it.kind == "ellipse":
            parts.append(f'<ellipse cx="{_num(cx)}" cy="{_num(cy)}" rx="{_num(it.w / 2)}" ry="{_num(it.h / 2)}"'
                         f'{fill}{stroke}{transform}/>')
        elif it.kind == "line":
            ends = ""
            if it.head:
                ends += f' marker-start="url(#{marker(it.head, it.stroke)})"'
            if it.tail:
                ends += f' marker-end="url(#{marker(it.tail, it.stroke)})"'
            parts.append(f'<line x1="{_num(it.x)}" y1="{_num(it.y)}" x2="{_num(it.x + it.w)}" '
                         f'y2="{_num(it.y + it.h)}"{stroke}{ends}{transform}/>')
        elif it.kind == "path":
            d = _scale_path(it.path, it.x, it.y, it.w, it.h)
            ends = ""
            if it.head:
                ends += f' marker-start="url(#{marker(it.head, it.stroke or "#000")})"'
            if it.tail:
                ends += f' marker-end="url(#{marker(it.tail, it.stroke or "#000")})"'
            parts.append(f'<path d="{d}"{fill}{stroke}{ends} stroke-linejoin="round"{transform}/>')

        if it.text_html:
            l, t, r, b = it.insets
            align = {"ctr": "center", "b": "flex-end"}.get(it.v_anchor, "flex-start")
            rot = f' transform="rotate({_num(it.rot)} {_num(cx)} {_num(cy)})"' if it.rot else ""
            parts.append(f'<foreignObject x="{_num(it.x)}" y="{_num(it.y)}" width="{_num(it.w)}" '
                         f'height="{_num(it.h)}"{rot}><div xmlns="http://www.w3.org/1999/xhtml" class="tb" '
                         f'style="padding:{_num(t)}px {_num(r)}px {_num(b)}px {_num(l)}px;'
                         f'justify-content:{align}">{it.text_html}</div></foreignObject>')

    defs = "".join(_marker_def(mid, kind, color) for (kind, color), mid in markers.items())
    return (f'<svg class="fig" viewBox="{_num(x0)} {_num(y0)} {_num(w)} {_num(h)}" '
            f'style="aspect-ratio:{_num(w)}/{_num(h)};width:{_num(w * MAX_ZOOM)}px" '
            f'xmlns="http://www.w3.org/2000/svg">'
            + (f"<defs>{defs}</defs>" if defs else "") + "".join(parts) + "</svg>")


def _scale_path(d: str, x: float, y: float, w: float, h: float) -> str:
    """Map a path in 0..1 box coordinates onto the box (x, y, w, h)."""
    out = []
    for cmd, args in re.findall(r"([MLCQAZ])([^MLCQAZ]*)", d):
        n = [float(v) for v in args.split()]
        if cmd == "A":  # rx ry rotation large-arc sweep x y
            out.append(f"A{_num(n[0] * w)} {_num(n[1] * h)} {_num(n[2])} {int(n[3])} {int(n[4])} "
                       f"{_num(x + n[5] * w)} {_num(y + n[6] * h)}")
        elif cmd == "Z":
            out.append("Z")
        else:
            out.append(cmd + " ".join(f"{_num(x + n[i] * w)} {_num(y + n[i + 1] * h)}"
                                      for i in range(0, len(n) - 1, 2)))
    return " ".join(out)


def _marker_def(mid: str, kind: str, color: str) -> str:
    shape = {
        "oval": '<circle cx="5" cy="5" r="4"/>',
        "diamond": '<path d="M5 0 L10 5 L5 10 L0 5 Z"/>',
    }.get(kind, '<path d="M0 0 L10 5 L0 10 Z"/>')
    return (f'<marker id="{mid}" viewBox="0 0 10 10" refX="{8 if kind not in ("oval", "diamond") else 5}" '
            f'refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse" fill="{color}">'
            f"{shape}</marker>")
