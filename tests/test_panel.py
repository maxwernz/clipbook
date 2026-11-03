"""Panel manual export: Word -> HTML pages, figures with labels, data.js."""

import json
from pathlib import Path

import pytest
import yaml
from docx import Document
from docx.shared import Pt
from lxml import etree
from PySide6.QtGui import QColor, QImage

from manual_builder.build import BuildError
from manual_builder.importer import import_file
from manual_builder.library import Library, Machine
from manual_builder.panel.convert import Block, Converter
from manual_builder.panel.export import STAMP, build_panel, paginate
from manual_builder.panel.images import ImageStore
from manual_builder.seed import DEFAULT_LIBRARY
from manual_builder.template import create_master_template

ANCHOR = """
<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
     xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
     xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
     xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
 <w:drawing><wp:anchor behindDoc="0" relativeHeight="5" simplePos="0">
  <wp:simplePos x="0" y="0"/>
  <wp:positionH relativeFrom="column"><wp:posOffset>{x}</wp:posOffset></wp:positionH>
  <wp:positionV relativeFrom="paragraph"><wp:posOffset>{y}</wp:posOffset></wp:positionV>
  <wp:extent cx="{w}" cy="{h}"/><wp:wrapNone/>
  <a:graphic><a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
   <wps:wsp><wps:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
     <a:prstGeom prst="{geom}"/>{fill}{line}</wps:spPr>{text}<wps:bodyPr/></wps:wsp>
  </a:graphicData></a:graphic></wp:anchor></w:drawing></w:r>"""


def _anchor(p, geom="rect", x=0, y=0, w=914400, h=254000, text="", line='<a:ln><a:noFill/></a:ln>',
            fill="<a:noFill/>"):
    txbx = (f'<wps:txbx><w:txbxContent><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:txbxContent></wps:txbx>'
            if text else "")
    xml = ANCHOR.format(x=x, y=y, w=w, h=h, geom=geom, fill=fill, line=line, text=txbx)
    p._p.append(etree.fromstring(xml.replace("<w:txbxContent>", '<w:txbxContent xmlns:w="http://schemas.'
                                             'openxmlformats.org/wordprocessingml/2006/main">')))


def _png(path: Path, w=400, h=300) -> Path:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("#336699"))
    img.save(str(path))
    return path


def _clipper_doc(path: Path, tmp: Path) -> Path:
    doc = Document()
    doc.add_paragraph("Clipper X", style="Heading 1")
    doc.add_paragraph("Einleitung für {{Maschinentyp}}.")
    doc.add_paragraph("Draht wechseln", style="Heading 2")
    doc.add_paragraph("Schritt eins", style="List Number")
    doc.add_paragraph("Schritt zwei", style="List Number")
    doc.add_paragraph("Achtung: Messer sind scharf.")
    pic = doc.add_paragraph()
    pic.add_run().add_picture(str(_png(tmp / "p.png")), width=Pt(200))
    _anchor(pic, x=Pt(220).emu, y=Pt(40).emu, text="Klemmschraube")                       # label
    _anchor(pic, geom="line", x=Pt(100).emu, y=Pt(50).emu, w=Pt(120).emu, h=0,
            line='<a:ln w="25400"><a:solidFill><a:srgbClr val="FF0000"/></a:solidFill>'
                 '<a:tailEnd type="triangle"/></a:ln>')                                      # red arrow
    _anchor(pic, geom="line", line="<a:ln><a:noFill/></a:ln>")                              # hidden line
    doc.add_paragraph("Grundstellung", style="Heading 2")
    doc.add_paragraph("{{ABSCHNITT_STOERUNGEN}}")
    doc.save(str(path))
    return path


@pytest.fixture
def lib(tmp_path) -> Library:
    root = tmp_path / "library"
    root.mkdir()
    (root / "library.yaml").write_text(yaml.safe_dump(DEFAULT_LIBRARY, allow_unicode=True), encoding="utf-8")
    src = Document()
    src.add_paragraph("x", style="List Number")
    src.save(str(tmp_path / "src.docx"))
    create_master_template(tmp_path / "src.docx", root / "templates" / "master.docx")
    (root / "modules").mkdir()
    (root / "machines").mkdir()
    lib = Library(root)
    gen = lib.new_module("allgemein", {"de": "Allgemeines"}, "general", "chapters")
    doc = Document()
    doc.add_paragraph("Sicherheit", style="Heading 1")
    doc.add_paragraph("Gefahr: nicht in die Maschine greifen.")
    doc.save(str(tmp_path / "a.docx"))
    import_file(lib, tmp_path / "a.docx", gen, "de")
    lib.new_module("wartung", {"de": "Wartung"}, "service", "chapters")
    clip = lib.new_module("clipper", {"de": "Clipper X", "en": "Clipper X"}, "clipper")
    import_file(lib, _clipper_doc(tmp_path / "c.docx", tmp_path), clip, "de")
    clip.data["faults"] = [{"code": 12, "message": {"de": "Draht leer", "en": "Wire empty"},
                            "cause": {"de": "Spule leer"}, "remedy": {"de": "Spule wechseln"}}]
    clip.data["maintenance"] = [{"interval_days": 7, "interval": {"de": "Wöchentlich"},
                                 "task": {"de": "Reinigen"}, "parts": {"de": "Messer"}}]
    clip.save_data()
    return lib


def _data(folder: Path) -> dict:
    raw = (folder / "data.js").read_text("utf-8")
    assert raw.startswith("window.MANUAL = ")
    return json.loads(raw[len("window.MANUAL = "):].rstrip().rstrip(";"))


def test_paginate_splits_at_headings_and_long_chapters():
    blocks = [Block("heading", 1, "Clipper"), Block("html", html="<p>intro</p>", weight=10),
              Block("heading", 2, "Kurz"), Block("html", html="<p>a</p>", weight=10),
              Block("heading", 2, "Lang"), Block("html", html="<p>b</p>", weight=10),
              Block("heading", 3, "Teil 1"), Block("html", html="<p>c</p>", weight=3000),
              Block("heading", 3, "Teil 2"), Block("html", html="<p>d</p>", weight=3000)]
    pages = paginate(blocks, "component", "Clipper")
    assert [(p["title"], p.get("group", "")) for p in pages] == [
        ("Clipper", ""), ("Kurz", ""), ("Lang", ""), ("Teil 1", "Lang"), ("Teil 2", "Lang")]


def test_converter_puts_labels_and_arrows_on_the_picture(tmp_path):
    doc = Document(str(_clipper_doc(tmp_path / "c.docx", tmp_path)))
    store = ImageStore(tmp_path / "out")
    blocks = Converter(doc, store).convert()
    html = "\n".join(b.html for b in blocks)
    assert "<ol>" in html and "<li>Schritt zwei" in html
    assert 'class="callout warn"' in html
    fig = next(b.html for b in blocks if "<svg" in b.html)
    assert "Klemmschraube" in fig and "foreignObject" in fig      # label inside the figure
    assert fig.count("<line") == 1 and 'stroke="#ff0000"' in fig  # arrow drawn, hidden line not
    assert "marker-end" in fig
    assert len(list((tmp_path / "out" / "img").iterdir())) == 1


def test_build_panel(lib, tmp_path):
    machine = Machine(name="Test 1", modules=["allgemein", "clipper", "wartung"], variables={"Maschinentyp": "SKT X"})
    res = build_panel(lib, machine, tmp_path / "out", log=lambda m: None)
    folder = res.folder
    assert folder.name == "Test_1_Panel"
    for name in ("index.html", "app.js", "style.css", STAMP):
        assert (folder / name).exists()
    data = _data(folder)
    assert data["machine"] == "SKT X"
    clip = next(c for c in data["components"] if c["id"] == "clipper")
    titles = [p["title"] for p in clip["pages"]["de"]]
    assert titles == ["Clipper X", "Draht wechseln", "Grundstellung"]
    assert "SKT X" in clip["pages"]["de"][0]["html"]                       # placeholder replaced
    assert 'data-go="#/component/clipper/faults"' in clip["pages"]["de"][2]["html"]  # marker -> link
    assert clip["fallback"]["en"] == "de"                                  # no English text yet
    assert data["faults"] == [{"code": "12", "component": "clipper", "message": {"de": "Draht leer", "en": "Wire empty"},
                               "cause": {"de": "Spule leer"}, "remedy": {"de": "Spule wechseln"}}]
    assert data["maintenance"][0]["component"] == "clipper"
    assert len(list((folder / "img").iterdir())) == 1

    # exporting again replaces the folder; a foreign folder is never deleted
    build_panel(lib, machine, tmp_path / "out", log=lambda m: None)
    (folder / STAMP).unlink()
    with pytest.raises(FileExistsError):
        build_panel(lib, machine, tmp_path / "out", log=lambda m: None)


def test_slot_can_be_hidden_from_panel(lib, tmp_path):
    lib.slot("general").panel = False
    machine = Machine(name="M", modules=["allgemein", "clipper", "wartung"])
    data = _data(build_panel(lib, machine, tmp_path / "o", log=lambda m: None).folder)
    assert [c["id"] for c in data["components"]] == ["clipper", "wartung"]


def test_build_panel_stops_on_errors(lib, tmp_path):
    with pytest.raises(BuildError):
        build_panel(lib, Machine(name="M", modules=["clipper", "clipper", "wartung"]), tmp_path / "o", log=lambda m: None)
