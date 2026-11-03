"""Render the original manual exactly as before (old files, old order, typed chapter numbers).

Used as a reference to compare against manuals built with Clipbook.
    uv run python tools/render_reference.py ../Bedienungsanleitungen ~/ProfilClip/Referenz
"""
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK
from docxcompose.composer import Composer

from clipbook import ooxml
from clipbook.engines import finalize

ORDER = [  # chapter order of "Inhaltsverzeichnis_Struktur Anleitung.pdf"
    "Deutsch/Allgemeine Anleitung/Allgemein_Deutsch_Muss angepasst werden.docx",  # 1–9.1
    "Deutsch/Dosierung/Servo 2k Dosierung (Fischer).docx",                         # 9.2
    "Deutsch/Folie/Folie und Siegelung 2K (Fischer).docx",                         # 9.3–9.4
    "Deutsch/Clipper/Draht-Deutsch.docx",                                          # 9.5–9.9
    "Deutsch/Touchscreen/Touchscreen Deutsch.docx",                                # 10
    "Deutsch/Wartung_Störungen/Wartung und Störungen.docx",                        # 11–12
    "Deutsch/Allgemeine Anleitung/Verbrauchsgüter_Deutsch_muss angepasst werden.docx",  # 13
    "Deutsch/CE-Vordruck/CE-H10 Deutsch.docx",                                     # 14
]


def _outline_levels(doc) -> None:
    """Give heading 1-3 styles an explicit outline level so every engine puts them in the TOC."""
    import re
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    for st in doc.styles:
        m = re.fullmatch(r"heading (\d)", (st.name or "").lower())
        if m:
            pPr = st.element.get_or_add_pPr()
            ol = pPr.find(qn("w:outlineLvl"))
            if ol is None:
                ol = OxmlElement("w:outlineLvl")
                pPr.append(ol)
            ol.set(qn("w:val"), str(int(m.group(1)) - 1))


def main(legacy: Path, out_dir: Path) -> None:
    master = Document(str(legacy / ORDER[0]))
    _outline_levels(master)
    body = master.element.body
    first = body[0]
    # title + table of contents in front, like the old manual
    title = ooxml.make_paragraph("Betriebsanleitung Schlauchbeutel-Abfüllautomat SKT H10",
                                 bold=True, size_half_points=32)
    inhalt = ooxml.make_paragraph("Inhalt", bold=True, size_half_points=28)
    toc = ooxml.make_paragraph("")
    ooxml.add_field(toc, 'TOC \\o "1-3" \\h \\z \\u', "Inhaltsverzeichnis")
    for el in (title, inhalt, toc):
        first.addprevious(el)
    toc.addnext(ooxml.make_paragraph("", page_break_before=True))
    composer = Composer(master)
    for rel in ORDER[1:]:
        doc = Document(str(legacy / rel))
        doc.paragraphs[0].insert_paragraph_before("").add_run().add_break(WD_BREAK.PAGE)
        composer.append(doc)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.docx"
        composer.save(str(raw))
        finalize(raw, out_dir / "Referenz_alte_Anleitung_SKT_H10.docx",
                 out_dir / "Referenz_alte_Anleitung_SKT_H10.pdf")


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser())
