"""Low-level helpers for working with WordprocessingML (the XML inside .docx)."""

from __future__ import annotations

import copy
import re
from typing import Iterable, Iterator

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": W_NS}

# "9.5.1 ", "11. ", "2.1.3.4 " at the very start of a heading
NUMBER_PREFIX = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?(?=\s|$)\s*")
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_:.\-ÄÖÜäöüß]+)\s*\}\}")


# ---------------------------------------------------------------- text access

def text_nodes(p) -> list:
    """All <w:t> elements of a paragraph in reading order (incl. hyperlinks)."""
    return p.findall(".//" + qn("w:t"))


def own_text_nodes(p) -> list:
    """<w:t> of the paragraph itself, excluding text inside nested text boxes."""
    result = []
    for t in p.iter(qn("w:t")):
        parent = t.getparent()
        nested = False
        while parent is not None and parent is not p:
            if parent.tag == qn("w:txbxContent"):
                nested = True
                break
            parent = parent.getparent()
        if not nested:
            result.append(t)
    return result


def para_text(p) -> str:
    return "".join(t.text or "" for t in own_text_nodes(p))


def iter_paragraphs(root) -> Iterator:
    """Every <w:p> below root, including those in tables and text boxes."""
    return root.iter(qn("w:p"))


def body_paragraphs(body) -> list:
    """Top-level paragraphs of the body (not in tables / text boxes)."""
    return [el for el in body if el.tag == qn("w:p")]


# ---------------------------------------------------------------- editing

def strip_prefix(p, pattern: re.Pattern = NUMBER_PREFIX) -> str | None:
    """Remove a prefix (default: manual chapter number) spanning any number of runs.

    Returns the removed prefix or None.
    """
    nodes = own_text_nodes(p)
    full = "".join(t.text or "" for t in nodes)
    m = pattern.match(full)
    if not m or not m.group(0):
        return None
    remaining = m.end()
    for t in nodes:
        txt = t.text or ""
        if remaining <= 0:
            break
        cut = min(len(txt), remaining)
        t.text = txt[cut:]
        remaining -= cut
    _fix_space(nodes)
    return m.group(0)


def strip_suffix(p, chars: str = ":.") -> None:
    """Remove trailing punctuation / whitespace (e.g. 'Drahtrollenwechsel.')."""
    nodes = [t for t in own_text_nodes(p) if t.text]
    while nodes:
        t = nodes[-1]
        new = t.text.rstrip()
        new = new.rstrip(chars).rstrip()
        if new:
            t.text = new
            break
        t.text = ""
        nodes.pop()


def _fix_space(nodes) -> None:
    for t in nodes:
        if t.text and (t.text[0].isspace() or t.text[-1].isspace()):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def replace_in_paragraph(p, mapping: dict[str, str] | None = None, func=None,
                         pattern: re.Pattern = PLACEHOLDER) -> int:
    """Replace pattern matches in a paragraph, even when Word split them over runs.

    Either a mapping key->value (key = group(1)) or a func(match)->str|None is used.
    Returns the number of replacements.
    """
    nodes = text_nodes(p)
    if not nodes:
        return 0
    full = "".join(t.text or "" for t in nodes)
    if "{{" not in full and pattern is PLACEHOLDER:
        return 0
    matches = list(pattern.finditer(full))
    count = 0
    for m in reversed(matches):
        if func is not None:
            value = func(m)
        else:
            value = (mapping or {}).get(m.group(1))
        if value is None:
            continue
        _replace_span(nodes, m.start(), m.end(), value)
        count += 1
    return count


def _replace_span(nodes, start: int, end: int, value: str) -> None:
    pos = 0
    first = True
    for t in nodes:
        txt = t.text or ""
        t_start, t_end = pos, pos + len(txt)
        pos = t_end
        if t_end <= start or t_start >= end:
            continue
        a = max(start, t_start) - t_start
        b = min(end, t_end) - t_start
        if first:
            t.text = txt[:a] + value + txt[b:]
            first = False
        else:
            t.text = txt[:a] + txt[b:]
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def set_paragraph_style(p, style_id: str | None) -> None:
    pPr = p.find(qn("w:pPr"))
    if style_id is None:
        if pPr is not None:
            ps = pPr.find(qn("w:pStyle"))
            if ps is not None:
                pPr.remove(ps)
        return
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p.insert(0, pPr)
    ps = pPr.find(qn("w:pStyle"))
    if ps is None:
        ps = OxmlElement("w:pStyle")
        pPr.insert(0, ps)
    ps.set(qn("w:val"), style_id)


def paragraph_style_id(p) -> str | None:
    ps = p.find(qn("w:pPr") + "/" + qn("w:pStyle"))
    return ps.get(qn("w:val")) if ps is not None else None


def remove_numbering(p) -> bool:
    pPr = p.find(qn("w:pPr"))
    if pPr is None:
        return False
    num = pPr.find(qn("w:numPr"))
    if num is not None:
        pPr.remove(num)
        return True
    return False


def clear_run_formatting(p) -> None:
    """Remove direct character formatting so the heading style decides the look."""
    for r in p.findall(qn("w:r")) + p.findall(qn("w:hyperlink") + "/" + qn("w:r")):
        rPr = r.find(qn("w:rPr"))
        if rPr is not None:
            r.remove(rPr)
    pPr = p.find(qn("w:pPr"))
    if pPr is not None:
        for tag in ("w:rPr", "w:jc", "w:ind", "w:spacing"):
            el = pPr.find(qn(tag))
            if el is not None:
                pPr.remove(el)


def has_graphics(p) -> bool:
    return bool(p.findall(".//" + qn("w:drawing")) or p.findall(".//" + qn("w:pict"))
                or p.findall(".//" + qn("w:object")))


def split_graphics_out(p):
    """Move runs containing pictures out of a (heading) paragraph into a new one after it."""
    new_p = OxmlElement("w:p")
    moved = False
    for r in list(p.findall(qn("w:r"))):
        if r.findall(".//" + qn("w:drawing")) or r.findall(".//" + qn("w:pict")) \
                or r.findall(".//" + qn("w:object")):
            p.remove(r)
            new_p.append(r)
            moved = True
    if moved:
        p.addnext(new_p)
        return new_p
    return None


def make_paragraph(text: str = "", style_id: str | None = None, bold: bool = False,
                   page_break_before: bool = False, size_half_points: int | None = None,
                   align: str | None = None):
    p = OxmlElement("w:p")
    if style_id or page_break_before or align:
        pPr = OxmlElement("w:pPr")
        if style_id:
            ps = OxmlElement("w:pStyle")
            ps.set(qn("w:val"), style_id)
            pPr.append(ps)
        if page_break_before:
            pPr.append(OxmlElement("w:pageBreakBefore"))
        if align:
            jc = OxmlElement("w:jc")
            jc.set(qn("w:val"), align)
            pPr.append(jc)
        p.append(pPr)
    lines = text.split("\n") if text else []
    for i, line in enumerate(lines):
        r = OxmlElement("w:r")
        if bold or size_half_points:
            rPr = OxmlElement("w:rPr")
            if bold:
                rPr.append(OxmlElement("w:b"))
            if size_half_points:
                sz = OxmlElement("w:sz")
                sz.set(qn("w:val"), str(size_half_points))
                rPr.append(sz)
            r.append(rPr)
        if i > 0:
            r.append(OxmlElement("w:br"))
        t = OxmlElement("w:t")
        t.text = line
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        r.append(t)
        p.append(r)
    return p


def add_field(p, instr: str, placeholder: str = "") -> None:
    """Append a complex field (e.g. 'TOC \\o "1-3" \\h \\z \\u', 'PAGEREF bm \\h')."""
    def run_with(child):
        r = OxmlElement("w:r")
        r.append(child)
        p.append(r)
        return r

    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "begin")
    fc.set(qn("w:dirty"), "true")
    run_with(fc)
    it = OxmlElement("w:instrText")
    it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    it.text = f" {instr} "
    run_with(it)
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "separate")
    run_with(fc)
    t = OxmlElement("w:t")
    t.text = placeholder
    run_with(t)
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "end")
    run_with(fc)


_bookmark_id = [9000]


def add_bookmark(p, name: str) -> None:
    _bookmark_id[0] += 1
    bid = str(_bookmark_id[0])
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), bid)
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), bid)
    pPr = p.find(qn("w:pPr"))
    if pPr is not None:
        pPr.addnext(start)
    else:
        p.insert(0, start)
    p.append(end)


def bookmark_name(*parts: str) -> str:
    """Word bookmark names: max 40 chars, letters/digits/underscore, start with letter."""
    raw = "_".join(parts)
    raw = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    return ("mb_" + raw)[:40]


def deepcopy(el):
    return copy.deepcopy(el)


def tostring(el) -> str:
    return etree.tostring(el, encoding="unicode")
