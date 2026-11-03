"""Generated tables (maintenance, spare parts, faults) with a simple, consistent look."""

from __future__ import annotations

from typing import Callable, Sequence

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from . import ooxml

CM = 567  # twips per cm

Cell = str | Callable[[object], None]   # text, or a function that fills the <w:p>


def _el(tag: str, **attrs) -> object:
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn(f"w:{k}"), str(v))
    return e


def _cell_paragraphs(content: Cell, bold: bool, size: int) -> list:
    if callable(content):
        p = ooxml.make_paragraph("")
        content(p)
        return [p]
    lines = str(content or "").split("\n") or [""]
    return [ooxml.make_paragraph(line, bold=bold, size_half_points=size) for line in lines]


def make_table(headers: Sequence[str], rows: Sequence[Sequence[Cell]], widths_cm: Sequence[float],
               font_size_pt: float = 10, header_fill: str = "D9D9D9"):
    """Return a <w:tbl> element with borders, a repeating header row and fixed widths."""
    size = int(font_size_pt * 2)
    tbl = _el("w:tbl")
    tblPr = _el("w:tblPr")
    tblPr.append(_el("w:tblW", w=int(sum(widths_cm) * CM), type="dxa"))
    borders = _el("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        borders.append(_el(f"w:{side}", val="single", sz=4, space=0, color="808080"))
    tblPr.append(borders)
    tblPr.append(_el("w:tblLayout", type="fixed"))
    mar = _el("w:tblCellMar")
    for side, v in (("top", 40), ("left", 80), ("bottom", 40), ("right", 80)):
        mar.append(_el(f"w:{side}", w=v, type="dxa"))
    tblPr.append(mar)
    tblPr.append(_el("w:tblLook", val="04A0", firstRow=1, lastRow=0, firstColumn=0,
                     lastColumn=0, noHBand=0, noVBand=1))
    tbl.append(tblPr)
    grid = _el("w:tblGrid")
    for w in widths_cm:
        grid.append(_el("w:gridCol", w=int(w * CM)))
    tbl.append(grid)

    def add_row(cells: Sequence[Cell], header: bool) -> None:
        tr = _el("w:tr")
        trPr = _el("w:trPr")
        trPr.append(_el("w:cantSplit"))
        if header:
            trPr.append(_el("w:tblHeader"))
        tr.append(trPr)
        for content, w in zip(cells, widths_cm):
            tc = _el("w:tc")
            tcPr = _el("w:tcPr")
            tcPr.append(_el("w:tcW", w=int(w * CM), type="dxa"))
            if header:
                tcPr.append(_el("w:shd", val="clear", color="auto", fill=header_fill))
            tc.append(tcPr)
            for p in _cell_paragraphs(content, header, size):
                tc.append(p)
            tr.append(tc)
        tbl.append(tr)

    add_row(headers, True)
    for r in rows:
        add_row(r, False)
    return tbl


def pageref(bookmark: str | None) -> Cell:
    if not bookmark:
        return "–"

    def fill(p):
        ooxml.add_field(p, f"PAGEREF {bookmark} \\h", "?")
    return fill
