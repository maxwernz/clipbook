"""Preview of the table of contents of a machine's manual (without building it)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docx import Document

from . import ooxml
from .library import DATA_SECTIONS, Library, Machine, Module
from .normalize import normalize_document

_cache: dict[tuple, tuple[list[tuple[int, str]], bool]] = {}


@dataclass
class Entry:
    number: str
    text: str
    children: list["Entry"] = field(default_factory=list)
    module_id: str = ""


def _module_headings(module: Module, lang: str, default_lang: str) -> tuple[list[tuple[int, str]], bool]:
    """(headings, has_own_markers) of the module text, cached by file and modification time."""
    path: Path | None = None
    for code in (lang, default_lang, *module.languages()):
        if module.docx_path(code).exists():
            path = module.docx_path(code)
            break
    if path is None:
        return [(1, module.label(lang))], False
    key = (str(path), path.stat().st_mtime, module.kind, module.label(lang))
    if key not in _cache:
        doc = Document(str(path))
        rep = normalize_document(doc, kind=module.kind, title=module.label(lang))
        text = "\n".join(ooxml.para_text(p) for p in ooxml.iter_paragraphs(doc.element.body))
        _cache[key] = ([(h.level, h.text) for h in rep.headings], "{{ABSCHNITT_" in text)
    return _cache[key]


def outline(lib: Library, machine: Machine, max_level: int = 2) -> list[Entry]:
    lang = machine.language
    flat: list[tuple[int, str, str]] = []
    for mid in machine.modules:
        m = lib.modules.get(mid)
        if m is None:
            continue
        heads, own_markers = _module_headings(m, lang, lib.default_language)
        flat += [(lvl, txt, mid) for lvl, txt in heads]
        if m.data_sections and not own_markers:
            for section in DATA_SECTIONS:
                if m.entries(section):
                    flat.append((2, lib.label(section, lang), mid))
    counters = [0] * 10
    roots: list[Entry] = []
    stack: list[Entry] = []
    for lvl, txt, mid in flat:
        counters[lvl - 1] += 1
        for i in range(lvl, 10):
            counters[i] = 0
        if lvl > max_level:
            continue
        e = Entry(".".join(str(c) for c in counters[:lvl]), txt, module_id=mid)
        if lvl == 1 or not stack:
            roots.append(e)
            stack = [e]
        else:
            stack[0].children.append(e)
    return roots
