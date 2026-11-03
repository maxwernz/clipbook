"""Panel manual: one offline folder per machine for the HMI panel (index.html + data.js + img/).

The pages are made for the 10" Unified Comfort Panel (1280 × 800, touch) and open via file://.
Jump addresses for the HMI: index.html?lang=de#/fault/12, #/component/<module id>, #/.
See docs/Panel-HTML.md.
"""

from __future__ import annotations

import datetime as _dt
import html
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from docx import Document

from ..build import BuildError, _replace_placeholders
from ..library import Issue, Library, Machine, Module, is_draft
from ..normalize import normalize_document
from .convert import Block, Converter
from .images import ImageStore

Log = Callable[[str], None]
TEMPLATE = Path(__file__).parent / "template"
STAMP = ".panel-manual"           # marks folders we may overwrite
PAGE_LIMIT = 2200                 # weight above which a page is split at its sub-headings


@dataclass
class PanelResult:
    folder: Path
    issues: list[Issue] = field(default_factory=list)


def panel_folder_name(machine: Machine) -> str:
    safe = re.sub(r"[^\w\-]+", "_", machine.name).strip("_") or "Anleitung"
    return f"{safe}_Panel"


# ---------------------------------------------------------------- pages

@dataclass
class _Page:
    title: str
    group: str = ""
    blocks: list[Block] = field(default_factory=list)

    @property
    def weight(self) -> int:
        return sum(b.weight for b in self.blocks)


def paginate(blocks: list[Block], kind: str, title: str) -> list[dict]:
    """Split a module into touch-sized pages: one per chapter (H2 of a component module,
    H1 of a multi-chapter module); long chapters are split again at their sub-headings."""
    page_level = 2 if kind == "component" else 1
    pages: list[_Page] = []
    group = ""
    current = _Page(title)
    for b in blocks:
        if b.kind == "heading" and b.level < page_level:
            group = b.text if kind != "component" else ""
            if current.blocks:
                pages.append(current)
            current = _Page(b.text)
            continue
        if b.kind == "heading" and b.level == page_level:
            if current.blocks:
                pages.append(current)
            current = _Page(b.text, group)
            continue
        current.blocks.append(b)
    if current.blocks:
        pages.append(current)

    out: list[_Page] = []
    for p in pages:
        subs = [b for b in p.blocks if b.kind == "heading" and b.level == page_level + 1]
        if p.weight <= PAGE_LIMIT or not subs:
            out.append(p)
            continue
        part = _Page(p.title, p.group)
        for b in p.blocks:
            if b.kind == "heading" and b.level == page_level + 1:
                if part.blocks:
                    out.append(part)
                part = _Page(b.text, p.title)
            else:
                part.blocks.append(b)
        if part.blocks:
            out.append(part)

    result = []
    for p in out:
        parts = []
        for b in p.blocks:
            if b.kind == "heading":
                h = min(6, 3 + max(0, b.level - page_level - 1))
                parts.append(f"<h{h}>{html.escape(b.text)}</h{h}>")
            else:
                parts.append(b.html)
        result.append({"title": p.title, **({"group": p.group} if p.group else {}), "html": "\n".join(parts)})
    return result


# ---------------------------------------------------------------- export

MARKER_TARGET = {
    "ABSCHNITT_STOERUNGEN": ("faults", "#/component/{id}/faults"),
    "ABSCHNITT_WARTUNG": ("maintenance", "#/maintenance"),
    "ABSCHNITT_ERSATZTEILE": ("spare_parts", "#/parts"),
    "GESAMT_FEHLERCODES": ("faults", "#/faults"),
    "GESAMT_WARTUNGSPLAN": ("maintenance", "#/maintenance"),
    "GESAMT_ERSATZTEILE": ("spare_parts", "#/parts"),
}


def _module_pages(lib: Library, module: Module, lang: str, values: dict, images: ImageStore,
                  issues: list[Issue], log: Log) -> tuple[list[dict], str | None]:
    src = module.docx_path(lang)
    fallback = None
    if not src.exists():
        for code in (lib.default_language, *module.languages()):
            if module.docx_path(code).exists():
                src, fallback = module.docx_path(code), code
                break
    doc = Document(str(src))
    title = module.label(lang)
    normalize_document(doc, kind=module.kind, title=title)
    _replace_placeholders(doc, values, lib, lang, [])

    def marker_html(name: str) -> str:
        target = MARKER_TARGET.get(name)
        if not target:
            return ""
        label, href = target
        return (f'<button class="btn link" data-go="{href.format(id=module.id)}">'
                f'{html.escape(lib.label(label, lang))} ›</button>')

    warnings: list[str] = []
    conv = Converter(doc, images, marker_html=marker_html, warn=warnings.append)
    blocks = conv.convert()
    if conv.reader.skipped:
        warnings.append("Zeichnungselemente nicht übernommen: " + ", ".join(sorted(conv.reader.skipped)))
    for w in dict.fromkeys(warnings):
        issues.append(Issue("warning", f"Panel · {module.label()} ({lang}): {w}"))
    return paginate(blocks, module.kind, title), fallback


def _merge_languages(issues: list[Issue]) -> list[Issue]:
    """'Panel · X (de): msg' + 'Panel · X (en): msg' -> 'Panel · X (de, en): msg'."""
    merged: dict[tuple, list[str]] = {}
    out: list[Issue | tuple] = []
    for i in issues:
        m = re.match(r"(Panel · .+) \((\w\w)\): (.*)", i.message)
        if not m:
            out.append(i)
            continue
        key = (i.level, m.group(1), m.group(3))
        if key not in merged:
            merged[key] = []
            out.append(key)
        merged[key].append(m.group(2))
    return [x if isinstance(x, Issue) else Issue(x[0], f"{x[1]} ({', '.join(merged[x])}): {x[2]}") for x in out]


def build_panel(lib: Library, machine: Machine, out_dir: Path, log: Log = print) -> PanelResult:
    from ..gui.icons import PATHS, slot_style

    issues = lib.validate(machine)
    errors = [i for i in issues if i.level == "error"]
    if errors:
        raise BuildError(errors)
    issues = [i for i in issues if i.level == "warning" and "Sprache" not in i.message]

    folder = Path(out_dir) / panel_folder_name(machine)
    if folder.exists():
        if not (folder / STAMP).exists():
            raise FileExistsError(f"{folder} gibt es schon und ist keine Panel-Anleitung, bitte umbenennen")
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    (folder / STAMP).write_text("Von Clipbook erzeugt, wird beim nächsten Export überschrieben.\n")
    for f in TEMPLATE.iterdir():
        if f.is_file():
            shutil.copy2(f, folder / f.name)

    langs = list(lib.languages)
    images = ImageStore(folder, warn=lambda msg: issues.append(Issue("warning", f"Panel: {msg}")))
    modules = [lib.modules[m] for m in machine.modules if m in lib.modules]
    components = []
    for module in modules:
        slot = lib.slot(module.slot)
        if slot is not None and not slot.panel:
            continue
        icon, color = slot_style(module.slot)
        comp = {
            "id": module.id,
            "slot": module.slot,
            "title": {lang: module.label(lang) for lang in langs},
            "color": color,
            "icon": PATHS.get(icon, PATHS["puzzle"]),
            "pages": {},
        }
        if module.has_text():
            for lang in langs:
                log(f"Panel: {module.label(lang)} ({lang})")
                values = lib.default_variables(lang)
                values.update({k: v for k, v in machine.variables.items() if v != ""})
                if not values.get("Ausgabe"):
                    values["Ausgabe"] = _dt.date.today().strftime("%d.%m.%Y")
                pages, fallback = _module_pages(lib, module, lang, values, images, issues, log)
                comp["pages"][lang] = pages
                if fallback:
                    comp.setdefault("fallback", {})[lang] = fallback
        components.append(comp)
    images.finish()
    issues = _merge_languages(issues)

    def texts(value):
        if isinstance(value, dict):
            return {k: str(v) for k, v in value.items() if v not in (None, "")}
        return "" if value is None else str(value)

    data = {
        "format": 1,
        "machine": machine.variables.get("Maschinentyp") or lib.default_variables(langs[0]).get("Maschinentyp")
        or machine.name,
        "name": machine.name,
        "created": _dt.datetime.now().strftime("%d.%m.%Y %H:%M"),
        "languages": langs,
        "labels": {lang: {k: lib.label(k, lang) for k in ("maintenance", "spare_parts", "faults", "interval",
                                                          "task", "parts", "part_no", "description", "cause",
                                                          "remedy", "module")} for lang in langs},
        "components": components,
        "faults": [], "maintenance": [], "spare_parts": [],
    }
    codes: dict[str, list[str]] = {}
    for m in modules:
        for x in m.entries("faults"):
            data["faults"].append({"code": str(x.get("code", "")).strip(), "component": m.id,
                                   **({"draft": True} if is_draft(x) else {}),
                                   **{k: texts(x.get(k)) for k in ("message", "cause", "remedy")}})
            codes.setdefault(str(x.get("code")), []).append(m.label())
        for x in m.entries("maintenance"):
            data["maintenance"].append({"interval_days": x.get("interval_days") or 0, "component": m.id,
                                        **({"draft": True} if is_draft(x) else {}),
                                        **{k: texts(x.get(k)) for k in ("interval", "task", "parts")}})
        for x in m.entries("spare_parts"):
            data["spare_parts"].append({"part_no": str(x.get("part_no", "")), "component": m.id,
                                        **({"draft": True} if is_draft(x) else {}),
                                        **{k: texts(x.get(k)) for k in ("description", "interval")}})
    for code, mods in codes.items():
        if len(mods) > 1:
            issues.append(Issue("warning", f"Störung {code} kommt mehrfach vor ({', '.join(mods)}): "
                                           f"das Panel kann nur eine davon anspringen"))

    (folder / "data.js").write_text("window.MANUAL = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n",
                                    encoding="utf-8")
    size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
    log(f"Fertig: {folder.name} ({size / 1e6:.1f} MB)")
    return PanelResult(folder, issues)
