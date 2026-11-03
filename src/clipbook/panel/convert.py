"""A normalized module .docx -> blocks of HTML (headings, text, lists, tables, figures)."""

from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass, field

from docx.oxml.ns import qn

from .figures import EMU_PER_PT, MAX_ZOOM, NS, Figure, Item, ShapeReader, figure_svg, find, xpath

TWIP_PER_PT = 20
CALLOUT = re.compile(r"^\W*(gefahr|warnung|vorsicht|achtung|danger|warning|caution|pericolo|avvertenza|"
                     r"attenzione)\b", re.I)
NOTE = re.compile(r"^\W*(hinweis|info|notice|note|nota|avviso)\b", re.I)
NEAR = 3         # paragraphs: anchored shapes this close to a picture belong to it
NEAR_EMPTY = 10  # … or this close, if only empty paragraphs are in between


@dataclass
class Block:
    kind: str           # heading | html
    level: int = 0
    text: str = ""      # heading text
    html: str = ""
    weight: int = 0     # rough "how much screen" for splitting pages


@dataclass
class _Anchor:
    items: list[Item]
    placeable: bool
    block: bool         # takes its own space in the text flow (wrapTopAndBottom …)


@dataclass
class _Para:
    el: object
    kind: str = "para"  # para | heading | table | marker
    level: int = 0
    inline: str = ""
    text: str = ""
    align: str = ""
    list_key: tuple | None = None   # (numId, ilvl, fmt)
    figure: list[Item] = field(default_factory=list)     # inline pictures, laid out in the line
    anchors: list[_Anchor] = field(default_factory=list)
    height: float = 0.0
    marker: str = ""
    tight: bool = False             # no space after (lines of one block typed as paragraphs)


class Converter:
    def __init__(self, doc, images, *, marker_html=None, warn=None):
        self.doc = doc
        self.part = doc.part
        self.images = images
        self.marker_html = marker_html or (lambda name: "")
        self.warn = warn or (lambda msg: None)
        self.reader = ShapeReader(self.part, images, self._textbox_html, self.warn)
        self.uid = 0
        self._read_layout()
        self._read_styles()
        self._read_numbering()

    # ------------------------------------------------------------ document facts
    def _read_layout(self):
        sect = self.doc.element.body.find(qn("w:sectPr"))
        pg = sect.find(qn("w:pgSz")) if sect is not None else None
        mar = sect.find(qn("w:pgMar")) if sect is not None else None
        page_w = int(pg.get(qn("w:w"), 11906)) if pg is not None else 11906
        left = int(mar.get(qn("w:left"), 1417)) if mar is not None else 1417
        right = int(mar.get(qn("w:right"), 1417)) if mar is not None else 1417
        self.margin_left = left / TWIP_PER_PT
        self.col_w = (page_w - left - right) / TWIP_PER_PT
        self.font_pt = 11.0
        self.default_spacing: dict[str, float] = {"before": 0.0, "after": 0.0, "line": 1.0}
        defaults = self.doc.styles.element.find(qn("w:docDefaults"))
        if defaults is not None:
            sz = defaults.find(f"{qn('w:rPrDefault')}/{qn('w:rPr')}/{qn('w:sz')}")
            if sz is not None:
                self.font_pt = int(sz.get(qn("w:val"))) / 2
            ppr = defaults.find(f"{qn('w:pPrDefault')}/{qn('w:pPr')}")
            self.default_spacing.update(_spacing_of(ppr))

    def _read_styles(self):
        self.style_name: dict[str, str] = {}
        self.style_num: dict[str, tuple[str, int]] = {}
        self.style_spacing: dict[str, dict] = {}
        self.style_size: dict[str, float] = {}
        self.style_base: dict[str, str] = {}
        self.default_style = None
        for st in self.doc.styles.element.findall(qn("w:style")):
            sid = st.get(qn("w:styleId"))
            if st.get(qn("w:type")) == "paragraph" and st.get(qn("w:default")) in ("1", "true"):
                self.default_style = sid
            base = st.find(qn("w:basedOn"))
            if base is not None:
                self.style_base[sid] = base.get(qn("w:val"))
            self.style_spacing[sid] = _spacing_of(st.find(qn("w:pPr")))
            sz = st.find(f"{qn('w:rPr')}/{qn('w:sz')}")
            if sz is not None:
                self.style_size[sid] = int(sz.get(qn("w:val"))) / 2
            name = st.find(qn("w:name"))
            self.style_name[sid] = (name.get(qn("w:val")) if name is not None else sid or "").lower()
            num = st.find(f"{qn('w:pPr')}/{qn('w:numPr')}")
            if num is not None and num.find(qn("w:numId")) is not None:
                ilvl = num.find(qn("w:ilvl"))
                self.style_num[sid] = (num.find(qn("w:numId")).get(qn("w:val")),
                                       int(ilvl.get(qn("w:val"))) if ilvl is not None else 0)

    def _metrics(self, p, sid: str | None) -> tuple[dict, float]:
        """Spacing (before/after in pt, line multiple) and font size of a paragraph:
        own settings, then the style chain, then the document defaults."""
        spacing = dict(self.default_spacing)
        size = self.font_pt
        chain, cur = [], sid or self.default_style
        while cur and cur not in chain:
            chain.append(cur)
            cur = self.style_base.get(cur)
        for style in reversed(chain):
            spacing.update(self.style_spacing.get(style, {}))
            size = self.style_size.get(style, size)
        spacing.update(_spacing_of(p.find(qn("w:pPr"))))
        return spacing, size

    def _read_numbering(self):
        self.num_fmt: dict[tuple[str, int], tuple[str, int]] = {}
        try:
            numbering = self.part.numbering_part.element
        except (KeyError, NotImplementedError, AttributeError):
            return
        abstract = {}
        for an in numbering.findall(qn("w:abstractNum")):
            lv = {}
            for lvl in an.findall(qn("w:lvl")):
                fmt = lvl.find(qn("w:numFmt"))
                start = lvl.find(qn("w:start"))
                lv[int(lvl.get(qn("w:ilvl")))] = (fmt.get(qn("w:val")) if fmt is not None else "decimal",
                                                  int(start.get(qn("w:val"))) if start is not None else 1)
            abstract[an.get(qn("w:abstractNumId"))] = lv
        for num in numbering.findall(qn("w:num")):
            aid = num.find(qn("w:abstractNumId"))
            for ilvl, val in abstract.get(aid.get(qn("w:val")) if aid is not None else "", {}).items():
                self.num_fmt[(num.get(qn("w:numId")), ilvl)] = val

    # ------------------------------------------------------------ inline text
    def _runs_html(self, p, size_default: float | None = None) -> str:
        """Text of a paragraph (or text box paragraph) as HTML, without drawings."""
        out: list[str] = []
        state = {"field": None}  # None | "instr" | "result"

        def run(r):
            rpr = r.find(qn("w:rPr"))
            fmt = _run_format(rpr, size_default)
            buf = []
            for c in r:
                tag = c.tag.rsplit("}", 1)[-1]
                if tag == "fldChar":
                    kind = c.get(qn("w:fldCharType"))
                    state["field"] = {"begin": "instr", "separate": "result", "end": None}.get(kind)
                elif state["field"] == "instr":
                    continue
                elif tag == "t":
                    buf.append(html.escape(c.text or ""))
                elif tag == "tab":
                    buf.append(" ")
                elif tag in ("br", "cr"):
                    if c.get(qn("w:type")) != "page":
                        buf.append("<br>")
                elif tag == "noBreakHyphen":
                    buf.append("-")
            text = "".join(buf)
            if text:
                out.append((fmt, text))

        def walk(el):
            for c in el:
                tag = c.tag.rsplit("}", 1)[-1]
                if tag == "r":
                    run(c)
                elif tag in ("hyperlink", "ins", "smartTag", "fldSimple", "customXml"):
                    walk(c)
                elif tag == "sdt":
                    content = c.find(qn("w:sdtContent"))
                    if content is not None:
                        walk(content)

        walk(p)
        # merge neighbours with the same format
        merged: list[tuple[tuple, str]] = []
        for fmt, text in out:
            if merged and merged[-1][0] == fmt:
                merged[-1] = (fmt, merged[-1][1] + text)
            else:
                merged.append((fmt, text))
        return "".join(_wrap(fmt, text) for fmt, text in merged).strip()

    def _textbox_html(self, txbx) -> str:
        parts = []
        for p in txbx.iter(qn("w:p")):
            inner = self._runs_html(p, self.font_pt)
            jc = p.find(f"{qn('w:pPr')}/{qn('w:jc')}")
            align = jc.get(qn("w:val")) if jc is not None else ""
            style = ' style="text-align:center"' if align == "center" else \
                ' style="text-align:right"' if align in ("right", "end") else ""
            parts.append(f"<p{style}>{inner or '&#8203;'}</p>")
        while parts and parts[-1].endswith(">&#8203;</p>"):
            parts.pop()
        return "".join(parts)

    # ------------------------------------------------------------ drawings
    def _drawings(self, p) -> tuple[list[Item], list[_Anchor]]:
        inline_items: list[Item] = []
        anchors: list[_Anchor] = []
        x = 0.0
        for d in xpath(p, ".//wp:inline[not(ancestor::mc:Fallback)][not(ancestor::w:txbxContent)]"):
            ext = find(d, "wp:extent")
            w = int(ext.get("cx", 0)) / EMU_PER_PT
            h = int(ext.get("cy", 0)) / EMU_PER_PT
            gd = find(d, "a:graphic/a:graphicData")
            if gd is not None:
                inline_items += self.reader.read(gd, x, 0, w, h)
            x += w + 4
        for v in xpath(p, ".//w:pict[not(ancestor::mc:Fallback)]//v:imagedata | .//w:object//v:imagedata"):
            shape = v.getparent()
            w, h = _vml_size(shape.get("style", ""))
            src = self.images(self.part, v.get(f"{{{NS['r']}}}id"))
            if src and w and h:
                inline_items.append(Item("image", x, 0, w, h, src=src))
                x += w + 4
        for a in xpath(p, ".//wp:anchor[not(ancestor::mc:Fallback)][not(ancestor::w:txbxContent)]"):
            anchors.append(self._anchor(a))
        return inline_items, anchors

    def _anchor(self, a) -> _Anchor:
        ext = find(a, "wp:extent")
        w = int(ext.get("cx", 0)) / EMU_PER_PT
        h = int(ext.get("cy", 0)) / EMU_PER_PT
        x = self._axis(find(a, "wp:positionH"), w, horizontal=True)
        y = self._axis(find(a, "wp:positionV"), h, horizontal=False)
        placeable = x is not None and y is not None and a.get("simplePos") not in ("1", "true")
        gd = find(a, "a:graphic/a:graphicData")
        items = self.reader.read(gd, x or 0, y or 0, w, h) if gd is not None else []
        z = (0 if a.get("behindDoc") in ("1", "true") else 2, int(a.get("relativeHeight", 0)))
        for it in items:
            it.z = z
        wrap = next((c.tag.rsplit("}", 1)[-1] for c in a if c.tag.rsplit("}", 1)[-1].startswith("wrap")), "")
        return _Anchor(items, placeable, wrap in ("wrapTopAndBottom", "wrapSquare"))

    def _axis(self, pos, size: float, horizontal: bool) -> float | None:
        if pos is None:
            return None
        rel = pos.get("relativeFrom")
        off = find(pos, "wp:posOffset")
        al = find(pos, "wp:align")
        if horizontal:
            if off is not None:
                v = int(off.text) / EMU_PER_PT
            elif al is not None:
                v = {"left": 0, "center": (self.col_w - size) / 2, "right": self.col_w - size}.get(al.text, 0)
            else:
                return None
            if rel in ("page", "leftMargin"):
                v -= self.margin_left
            elif rel not in ("column", "margin", "character", "insideMargin"):
                return None
            return v
        if rel not in ("paragraph", "line"):
            return None
        if off is not None:
            return int(off.text) / EMU_PER_PT
        return 0 if al is not None else None

    # ------------------------------------------------------------ paragraphs
    def _para(self, p) -> _Para:
        info = _Para(p)
        ppr = p.find(qn("w:pPr"))
        sid = None
        if ppr is not None:
            st = ppr.find(qn("w:pStyle"))
            sid = st.get(qn("w:val")) if st is not None else None
            jc = ppr.find(qn("w:jc"))
            info.align = jc.get(qn("w:val")) if jc is not None else ""
        name = self.style_name.get(sid, "") if sid else ""
        m = re.fullmatch(r"heading (\d)", name)
        info.inline = self._runs_html(p)
        info.text = _plain(info.inline)
        if m and info.text:
            info.kind, info.level = "heading", int(m.group(1))
            return info
        if re.fullmatch(r"\{\{[^}]+\}\}", info.text.strip()):
            info.kind, info.marker = "marker", info.text.strip()[2:-2].split(":")[0].strip()
            return info
        num = ppr.find(qn("w:numPr")) if ppr is not None else None
        key = None
        if num is not None and num.find(qn("w:numId")) is not None:
            ilvl = num.find(qn("w:ilvl"))
            key = (num.find(qn("w:numId")).get(qn("w:val")), int(ilvl.get(qn("w:val"))) if ilvl is not None else 0)
        elif sid in self.style_num:
            key = self.style_num[sid]
        if key and key[0] != "0" and info.text:
            fmt, _start = self.num_fmt.get(key, ("bullet", 1))
            info.list_key = (key[0], key[1], fmt)
        info.figure, info.anchors = self._drawings(p)
        spacing, size = self._metrics(p, sid)
        info.tight = spacing["after"] < 3
        gaps = spacing["before"] + spacing["after"]
        if info.figure:
            info.height = max(it.y + it.h for it in info.figure) * spacing["line"] + gaps
        else:
            line = size * 1.17 * spacing["line"]
            chars_per_line = max(self.col_w / (size * 0.5), 20)
            lines = max(1, math.ceil(len(info.text) / chars_per_line)) if info.text else 1
            info.height = lines * line + gaps
        return info

    def _table(self, tbl) -> str:
        rows = []
        for tr in tbl.findall(qn("w:tr")):
            cells = []
            for tc in tr.findall(qn("w:tc")):
                tcpr = tc.find(qn("w:tcPr"))
                span = 1
                if tcpr is not None:
                    gs = tcpr.find(qn("w:gridSpan"))
                    span = int(gs.get(qn("w:val"))) if gs is not None else 1
                    vm = tcpr.find(qn("w:vMerge"))
                    if vm is not None and vm.get(qn("w:val")) != "restart":
                        cells.append(f'<td{f" colspan={span}" if span > 1 else ""}></td>')
                        continue
                content = []
                for p in tc.iter(qn("w:p")):
                    inner = self._runs_html(p)
                    items, _ = self._drawings(p)
                    imgs = "".join(f'<img src="{html.escape(it.src)}" alt="">' for it in items if it.kind == "image")
                    if inner or imgs:
                        content.append(inner + imgs)
                cells.append(f'<td{f" colspan={span}" if span > 1 else ""}>{"<br>".join(content)}</td>')
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return '<div class="tablewrap"><table>' + "".join(rows) + "</table></div>"

    # ------------------------------------------------------------ main
    def convert(self) -> list[Block]:
        body = self.doc.element.body
        paras: list[_Para] = []
        for el in _flow(body):
            if el.tag == qn("w:p"):
                paras.append(self._para(el))
            elif el.tag == qn("w:tbl"):
                t = _Para(el, kind="table")
                t.inline = self._table(el)
                t.text = _plain(t.inline)
                t.height = 200
                paras.append(t)
        self._attach_anchors(paras)
        return self._emit(paras)

    def _attach_anchors(self, paras: list[_Para]) -> None:
        """Move shapes anchored near a picture onto that picture; leave the rest in place."""
        pics = [i for i, p in enumerate(paras) if p.figure]
        for j, p in enumerate(paras):
            keep = []
            for anc in p.anchors:
                target = None
                if anc.placeable and anc.items:
                    best = None
                    for i in pics:
                        d = abs(i - j)
                        if d > NEAR_EMPTY or (best is not None and d >= best[0]):
                            continue
                        lo, hi = min(i, j), max(i, j)
                        if any(paras[k].kind in ("heading", "table") for k in range(lo, hi + 1)):
                            continue
                        # further away only across empty paragraphs (Word users often press Enter a few times)
                        if d > NEAR and any(paras[k].text or paras[k].figure for k in range(lo + 1, hi)):
                            continue
                        best = (d, i)
                    target = best[1] if best else None
                if target is None:
                    keep.append(anc)
                    continue
                if j >= target:
                    dy = sum(paras[k].height for k in range(target, j))
                else:
                    dy = -sum(paras[k].height for k in range(j, target))
                for it in anc.items:
                    it.y += dy
                paras[target].figure += anc.items
            p.anchors = keep

    def _emit(self, paras: list[_Para]) -> list[Block]:
        blocks: list[Block] = []
        lst: list[_Para] = []
        counters: dict[tuple[str, int], int] = {}

        def flush_list():
            if lst:
                blocks.append(Block("html", html=_list_html(lst, counters, self.num_fmt),
                                    weight=sum(len(x.text) + 40 for x in lst)))
                lst.clear()

        for p in paras:
            if p.kind == "heading":
                flush_list()
                blocks.append(Block("heading", level=p.level, text=p.text))
                continue
            if p.list_key and not p.figure:
                lst.append(p)
                self._standalone(p, blocks)
                continue
            flush_list()
            if p.kind == "table":
                blocks.append(Block("html", html=p.inline, weight=len(p.text) + 200))
                continue
            if p.kind == "marker":
                h = self.marker_html(p.marker)
                if h:
                    blocks.append(Block("html", html=h, weight=80))
                continue
            if p.inline:
                blocks.append(Block("html", html=_para_html(p), weight=len(p.text) + 30))
            if p.figure:
                blocks.append(Block("html", html=self._figure_html(p), weight=600))
            self._standalone(p, blocks)
        flush_list()
        return blocks

    def _standalone(self, p: _Para, blocks: list[Block]) -> None:
        """Shapes that belong to no picture: keep text boxes as boxes in the text flow."""
        for anc in p.anchors:
            texts = [it.text_html for it in anc.items if it.text_html]
            if not texts:
                continue
            text = "".join(texts)
            plain = _plain(text)
            cls = "callout warn" if CALLOUT.match(plain) else "callout note" if NOTE.match(plain) \
                else "callout" if anc.block or len(plain) > 60 else "label"
            blocks.append(Block("html", html=f'<div class="{cls}">{text}</div>', weight=len(plain) + 40))

    def _figure_html(self, p: _Para) -> str:
        fig = Figure(p.figure)
        if not fig.has_overlay and len(fig.images) == 1:
            img = fig.images[0]
            return (f'<figure class="pic"><img src="{html.escape(img.src)}" alt="" '
                    f'style="width:{img.w * MAX_ZOOM:.0f}px"></figure>')
        self.uid += 1
        return f'<figure class="pic">{figure_svg(fig, f"f{self.uid}")}</figure>'


# ---------------------------------------------------------------- helpers

def _flow(body):
    """Top-level paragraphs and tables in order (content controls unpacked)."""
    for el in body:
        if el.tag in (qn("w:p"), qn("w:tbl")):
            yield el
        elif el.tag == qn("w:sdt"):
            content = el.find(qn("w:sdtContent"))
            if content is not None:
                yield from _flow(content)


def _on(el) -> bool:
    return el is not None and el.get(qn("w:val")) not in ("0", "false", "none")


def _run_format(rpr, size_default: float | None) -> tuple:
    if rpr is None:
        return (False, False, False, None, None, f"{size_default:g}" if size_default else None)
    color = rpr.find(qn("w:color"))
    c = color.get(qn("w:val")) if color is not None else None
    c = None if not c or c.lower() in ("auto", "000000") else "#" + c.lower()
    va = rpr.find(qn("w:vertAlign"))
    sz = rpr.find(qn("w:sz"))
    size = int(sz.get(qn("w:val"))) / 2 if sz is not None else size_default
    return (_on(rpr.find(qn("w:b"))), _on(rpr.find(qn("w:i"))), _on(rpr.find(qn("w:u"))), c,
            va.get(qn("w:val")) if va is not None and va.get(qn("w:val")) in ("superscript", "subscript") else None,
            f"{size:g}" if size_default is not None and size else None)


def _wrap(fmt: tuple, text: str) -> str:
    bold, italic, under, color, va, size = fmt
    if va:
        text = f"<{'sup' if va == 'superscript' else 'sub'}>{text}</{'sup' if va == 'superscript' else 'sub'}>"
    if under:
        text = f"<u>{text}</u>"
    if italic:
        text = f"<i>{text}</i>"
    if bold:
        text = f"<b>{text}</b>"
    style = []
    if color:
        style.append(f"color:{color}")
    if size:
        style.append(f"font-size:{size}px")
    return f'<span style="{";".join(style)}">{text}</span>' if style else text


def _plain(h: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", h)).strip()


def _para_html(p: _Para) -> str:
    cls = []
    if CALLOUT.match(p.text):
        return f'<div class="callout warn">{p.inline}</div>'
    if NOTE.match(p.text) and len(p.text) > 12:
        return f'<div class="callout note">{p.inline}</div>'
    if p.align == "center":
        cls.append("center")
    if p.tight:
        cls.append("tight")
    return f'<p{f" class={chr(34)}{" ".join(cls)}{chr(34)}" if cls else ""}>{p.inline}</p>'


def _list_html(items: list[_Para], counters: dict, num_fmt: dict) -> str:
    out: list[str] = []
    stack: list[str] = []  # open list tags
    for it in items:
        num_id, ilvl, fmt = it.list_key
        tag = "ul" if fmt in ("bullet", "none") else "ol"
        while len(stack) > ilvl + 1:
            out.append(f"</li></{stack.pop()}>")
        if len(stack) == ilvl + 1 and stack[-1] != tag:
            out.append(f"</li></{stack.pop()}>")
        if len(stack) < ilvl + 1:
            while len(stack) < ilvl + 1:
                key = (num_id, len(stack))
                start = counters.get(key, num_fmt.get(key, ("", 1))[1] - 1) + 1
                attrs = f' start="{start}"' if tag == "ol" and start != 1 else ""
                if tag == "ol" and fmt in ("lowerLetter", "upperLetter"):
                    attrs += f' type="{"a" if fmt == "lowerLetter" else "A"}"'
                out.append(f"<{tag}{attrs}>")
                stack.append(tag)
        else:
            out.append("</li>")
        counters[(num_id, ilvl)] = counters.get((num_id, ilvl), num_fmt.get((num_id, ilvl), ("", 1))[1] - 1) + 1
        for deeper in [k for k in counters if k[0] == num_id and k[1] > ilvl]:
            del counters[deeper]
        out.append(f"<li>{it.inline}")
    while stack:
        out.append(f"</li></{stack.pop()}>")
    return "".join(out)


def _spacing_of(ppr) -> dict:
    """w:spacing of a pPr -> {"before": pt, "after": pt, "line": multiple} (only what is set)."""
    out: dict[str, float] = {}
    sp = ppr.find(qn("w:spacing")) if ppr is not None else None
    if sp is None:
        return out
    for key in ("before", "after"):
        if sp.get(qn(f"w:{key}")) is not None and sp.get(qn(f"w:{key}Autospacing")) not in ("1", "true"):
            out[key] = int(sp.get(qn(f"w:{key}"))) / TWIP_PER_PT
    if sp.get(qn("w:line")) and sp.get(qn("w:lineRule"), "auto") == "auto":
        out["line"] = int(sp.get(qn("w:line"))) / 240
    return out


def _vml_size(style: str) -> tuple[float, float]:
    def get(key):
        m = re.search(rf"{key}:\s*([\d.]+)(pt|in|px|cm|mm)?", style)
        if not m:
            return 0.0
        v = float(m.group(1))
        return v * {"in": 72, "px": 0.75, "cm": 28.35, "mm": 2.835}.get(m.group(2) or "pt", 1)
    return get("width"), get("height")
