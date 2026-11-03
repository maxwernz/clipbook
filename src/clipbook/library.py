"""Module library and machine configurations (all stored as YAML + .docx files).

Layout of a library folder:

    library.yaml                 slots, languages, labels, default variables
    templates/master.docx        cover, TOC, header/footer, heading numbering
    modules/<id>/module.yaml     metadata (title, slot, version, history)
    modules/<id>/<lang>.docx     the text of the module, one file per language
    modules/<id>/data.yaml       structured data: maintenance, spare parts, faults
    modules/<id>/archive/        previous versions of the .docx files
    machines/<name>.yaml         saved machine configurations
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DATA_SECTIONS = ("maintenance", "spare_parts", "faults")

# A table row with a "draft" text is an unchecked proposal (e.g. assigned automatically by the
# first import). The text says what is unsure. Only a person who is responsible removes it.
DRAFT_KEY = "draft"


def is_draft(entry: dict) -> bool:
    return bool(str(entry.get(DRAFT_KEY) or "").strip())


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _dump_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False, width=100)


def tr(value: Any, lang: str, fallback: str = "de") -> tuple[str, bool]:
    """Translate a {lang: text} dict. Returns (text, is_fallback)."""
    if value is None:
        return "", False
    if isinstance(value, dict):
        if value.get(lang):
            return str(value[lang]), False
        if value.get(fallback):
            return str(value[fallback]), lang != fallback
        for v in value.values():
            if v:
                return str(v), True
        return "", False
    return str(value), False


def slugify(text: str) -> str:
    text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "modul"


# ---------------------------------------------------------------- slots

@dataclass
class Slot:
    id: str
    title: dict
    max: int | None = 1
    required: bool = False
    panel: bool = True               # shown in the panel manual (library.yaml: "panel: false" hides it)

    def label(self, lang: str) -> str:
        return tr(self.title, lang)[0]


# ---------------------------------------------------------------- modules

@dataclass
class Module:
    path: Path
    id: str
    title: dict
    slot: str
    version: int = 1
    kind: str = "component"          # component = one chapter, chapters = several H1
    data_sections: bool = True       # render own maintenance/parts/faults in its chapter
    description: str = ""
    conflicts: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    component: dict = field(default_factory=dict)   # short name for overview tables

    # -- files
    def docx_path(self, lang: str) -> Path:
        return self.path / f"{lang}.docx"

    def languages(self) -> list[str]:
        return sorted(p.stem for p in self.path.glob("*.docx") if not p.name.startswith("~"))

    def has_text(self) -> bool:
        return bool(self.languages())

    def label(self, lang: str = "de") -> str:
        return tr(self.title, lang)[0] or self.id

    def component_label(self, lang: str = "de") -> str:
        return tr(self.component, lang)[0] or self.label(lang)

    def entries(self, section: str) -> list[dict]:
        return list(self.data.get(section) or [])

    def has_data(self) -> bool:
        return any(self.entries(s) for s in DATA_SECTIONS)

    def draft_count(self, section: str | None = None) -> int:
        """Table rows that are an unchecked draft."""
        sections = [section] if section else DATA_SECTIONS
        return sum(1 for s in sections for e in self.entries(s) if is_draft(e))

    # -- persistence
    @classmethod
    def load(cls, path: Path) -> "Module":
        meta = _load_yaml(path / "module.yaml") or {}
        data = _load_yaml(path / "data.yaml") or {}
        title = meta.get("title") or {"de": path.name}
        if isinstance(title, str):
            title = {"de": title}
        return cls(
            path=path,
            id=meta.get("id", path.name),
            title=title,
            slot=meta.get("slot", "options"),
            version=int(meta.get("version", 1)),
            kind=meta.get("kind", "component"),
            data_sections=bool(meta.get("data_sections", True)),
            description=meta.get("description", "") or "",
            conflicts=list(meta.get("conflicts") or []),
            requires=list(meta.get("requires") or []),
            history=list(meta.get("history") or []),
            data={k: data.get(k) or [] for k in DATA_SECTIONS},
            component=meta.get("component") or {},
        )

    def save_meta(self) -> None:
        _dump_yaml(self.path / "module.yaml", {
            "id": self.id,
            "title": self.title,
            "slot": self.slot,
            "version": self.version,
            "kind": self.kind,
            "data_sections": self.data_sections,
            "description": self.description,
            **({"component": self.component} if self.component else {}),
            "conflicts": self.conflicts,
            "requires": self.requires,
            "history": self.history,
        })

    def save_data(self) -> None:
        clean = {k: v for k, v in self.data.items() if v}
        if clean:
            _dump_yaml(self.path / "data.yaml", clean)
        elif (self.path / "data.yaml").exists():
            (self.path / "data.yaml").unlink()

    def add_history(self, note: str, language: str | None = None) -> None:
        self.history.append({
            "version": self.version,
            "date": _dt.date.today().isoformat(),
            **({"language": language} if language else {}),
            "note": note,
        })


# ---------------------------------------------------------------- machines

@dataclass
class Machine:
    name: str
    language: str = "de"
    modules: list[str] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    last_built: str = ""
    path: Path | None = None

    @classmethod
    def load(cls, path: Path) -> "Machine":
        d = _load_yaml(path) or {}
        return cls(
            name=d.get("name", path.stem),
            language=d.get("language", "de"),
            modules=list(d.get("modules") or []),
            variables={str(k): "" if v is None else str(v)
                       for k, v in (d.get("variables") or {}).items()},
            last_built=str(d.get("last_built") or ""),
            path=path,
        )

    def save(self, path: Path | None = None) -> Path:
        path = path or self.path
        if path is None:
            raise ValueError("no path given")
        _dump_yaml(path, {
            "name": self.name,
            "language": self.language,
            "modules": self.modules,
            "variables": self.variables,
            **({"last_built": self.last_built} if self.last_built else {}),
        })
        self.path = path
        return path


# ---------------------------------------------------------------- library

@dataclass
class Issue:
    level: str          # "error" | "warning" | "info"
    message: str

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.message}"


class Library:
    def __init__(self, root: Path):
        self.root = Path(root)
        cfg = _load_yaml(self.root / "library.yaml")
        if cfg is None:
            raise FileNotFoundError(f"Keine library.yaml in {self.root}")
        self.config = cfg
        self.name: str = cfg.get("name", "Bibliothek")
        self.languages: list[str] = list(cfg.get("languages") or ["de"])
        self.default_language: str = cfg.get("default_language", "de")
        self.slots: list[Slot] = [
            Slot(id=s["id"], title=s.get("title") or {"de": s["id"]},
                 max=s.get("max", 1), required=bool(s.get("required", False)),
                 panel=bool(s.get("panel", True)))
            for s in cfg.get("slots") or []
        ]
        self.labels: dict = cfg.get("labels") or {}
        self.variables: list[dict] = list(cfg.get("variables") or [])
        self.modules: dict[str, Module] = {}
        self.reload_modules()

    # -- paths
    @property
    def modules_dir(self) -> Path:
        return self.root / "modules"

    @property
    def machines_dir(self) -> Path:
        return self.root / "machines"

    def template_path(self, lang: str) -> Path:
        specific = self.root / "templates" / f"master_{lang}.docx"
        return specific if specific.exists() else self.root / "templates" / "master.docx"

    # -- lookups
    def reload_modules(self) -> None:
        self.modules = {}
        if self.modules_dir.exists():
            for d in sorted(self.modules_dir.iterdir()):
                if (d / "module.yaml").exists():
                    m = Module.load(d)
                    self.modules[m.id] = m

    def slot(self, slot_id: str) -> Slot | None:
        return next((s for s in self.slots if s.id == slot_id), None)

    def slot_index(self, slot_id: str) -> int:
        for i, s in enumerate(self.slots):
            if s.id == slot_id:
                return i
        return len(self.slots)

    def label(self, key: str, lang: str) -> str:
        for candidate in (lang, self.default_language):
            v = (self.labels.get(candidate) or {}).get(key)
            if v:
                return str(v)
        return key

    def modules_in_slot(self, slot_id: str) -> list[Module]:
        return [m for m in self.modules.values() if m.slot == slot_id]

    def default_variables(self, lang: str) -> dict[str, str]:
        out = {}
        for v in self.variables:
            default = v.get("default", "")
            out[v["key"]] = tr(default, lang)[0] if isinstance(default, dict) else str(default)
        return out

    def machines(self) -> list[Path]:
        if not self.machines_dir.exists():
            return []
        return sorted(self.machines_dir.glob("*.yaml"))

    def new_module(self, module_id: str, title: dict, slot: str, kind: str = "component") -> Module:
        path = self.modules_dir / module_id
        if path.exists():
            raise FileExistsError(f"Modul '{module_id}' existiert bereits")
        path.mkdir(parents=True)
        m = Module(path=path, id=module_id, title=title, slot=slot, kind=kind,
                   data={k: [] for k in DATA_SECTIONS})
        m.add_history("Modul angelegt")
        m.save_meta()
        self.modules[module_id] = m
        return m

    # -- validation of a machine configuration
    def validate(self, machine: Machine) -> list[Issue]:
        issues: list[Issue] = []
        drafts: list[Module] = []
        lang = machine.language
        if lang not in self.languages:
            issues.append(Issue("warning", f"Sprache '{lang}' ist nicht in library.yaml eingetragen"))
        seen: dict[str, int] = {}
        for mid in machine.modules:
            m = self.modules.get(mid)
            if m is None:
                issues.append(Issue("error", f"Modul '{mid}' gibt es nicht in der Bibliothek"))
                continue
            seen[m.slot] = seen.get(m.slot, 0) + 1
            if m.has_text() and lang not in m.languages():
                issues.append(Issue("warning",
                                    f"'{m.label(lang)}' hat keinen Text auf '{lang}' – "
                                    f"es wird '{self.default_language}' verwendet"))
            if not m.has_text() and not m.has_data():
                issues.append(Issue("warning", f"'{m.label(lang)}' ist leer"))
            if m.draft_count():
                drafts.append(m)
            for c in m.conflicts:
                if c in machine.modules:
                    issues.append(Issue("error", f"'{m.label(lang)}' und "
                                                 f"'{self._lbl(c, lang)}' schließen sich aus"))
            for r in m.requires:
                if r not in machine.modules:
                    issues.append(Issue("error", f"'{m.label(lang)}' benötigt '{self._lbl(r, lang)}'"))
            if self.slot(m.slot) is None:
                issues.append(Issue("warning", f"'{m.label(lang)}' hat unbekannten Platz '{m.slot}'"))
        if drafts:
            n = sum(m.draft_count() for m in drafts)
            issues.append(Issue("warning", f"Entwurf: {n} {'Tabellenzeile ist' if n == 1 else 'Tabellenzeilen sind'} "
                                           f"(Wartung/Ersatzteile/Störungen) automatisch zugeordnet und nicht geprüft "
                                           f"– in {', '.join(m.label(lang) for m in drafts)}"))
        if len(set(machine.modules)) != len(machine.modules):
            issues.append(Issue("error", "Ein Modul ist mehrfach enthalten"))
        for s in self.slots:
            n = seen.get(s.id, 0)
            if s.max is not None and n > s.max:
                issues.append(Issue("error", f"Nur {s.max}× '{s.label(lang)}' erlaubt, gewählt: {n}"))
            if s.required and n == 0:
                issues.append(Issue("error", f"'{s.label(lang)}' fehlt (Pflicht)"))
        order = [self.slot_index(self.modules[m].slot) for m in machine.modules if m in self.modules]
        if order != sorted(order):
            issues.append(Issue("info", "Reihenfolge weicht von der Standardgliederung ab"))
        for key in ("Maschinentyp",):
            if key in self.default_variables(lang) and not machine.variables.get(key):
                issues.append(Issue("warning", f"Variable '{key}' ist leer"))
        return issues

    def _lbl(self, mid: str, lang: str) -> str:
        m = self.modules.get(mid)
        return m.label(lang) if m else mid

    def sort_by_slot(self, module_ids: list[str]) -> list[str]:
        return sorted(module_ids, key=lambda mid: (
            self.slot_index(self.modules[mid].slot) if mid in self.modules else 999,
            module_ids.index(mid)))
