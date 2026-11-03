"""Layout engines: update table of contents / page numbers and export PDF.

python-docx cannot paginate, so a real word processor does the last step:

* Word (Windows)   – COM automation via pywin32. Best fidelity.
* Word (macOS)     – AppleScript via osascript.
* LibreOffice      – headless, via its bundled Python + UNO. Used for the PDF only;
                     the .docx stays the one we generated (Word refreshes its fields
                     on open), so no formatting is lost by a LibreOffice round trip.
* none             – the .docx is marked "update fields on open"; Word asks once.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Callable

Log = Callable[[str], None]

ENGINES = ("auto", "word", "libreoffice", "none")


class EngineError(RuntimeError):
    pass


# ---------------------------------------------------------------- discovery

def find_libreoffice() -> tuple[Path, Path] | None:
    """Return (soffice, python) of a LibreOffice installation."""
    candidates: list[tuple[Path, Path]] = []
    env = os.environ.get("CLIPBOOK_LIBREOFFICE")
    if env:
        base = Path(env)
        candidates.append((base / "program" / "soffice.exe", base / "program" / "python.exe"))
        candidates.append((base / "Contents" / "MacOS" / "soffice",
                           base / "Contents" / "Resources" / "python"))
    if sys.platform == "darwin":
        for app in (Path("/Applications/LibreOffice.app"),
                    Path.home() / "Applications" / "LibreOffice.app"):
            candidates.append((app / "Contents" / "MacOS" / "soffice",
                               app / "Contents" / "Resources" / "python"))
    elif sys.platform == "win32":
        for pf in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                   os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            base = Path(pf) / "LibreOffice" / "program"
            candidates.append((base / "soffice.exe", base / "python.exe"))
    else:
        for base in (Path("/usr/lib/libreoffice/program"), Path("/opt/libreoffice/program")):
            candidates.append((base / "soffice", Path("/usr/bin/python3")))
    for soffice, py in candidates:
        if soffice.exists() and py.exists():
            return soffice, py
    return None


def word_available() -> bool:
    if sys.platform == "darwin":
        return any(p.exists() for p in (Path("/Applications/Microsoft Word.app"),
                                         Path.home() / "Applications" / "Microsoft Word.app"))
    if sys.platform == "win32":
        try:
            import winreg  # noqa: F401
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application"):
                return True
        except OSError:
            return False
    return False


def available_engines() -> list[str]:
    out = []
    if word_available():
        out.append("word")
    if find_libreoffice():
        out.append("libreoffice")
    out.append("none")
    return out


# ---------------------------------------------------------------- dispatcher

def finalize(raw_docx: Path, out_docx: Path, out_pdf: Path | None,
             engine: str = "auto", log: Log = print) -> str:
    """Update fields of raw_docx, write out_docx (+ out_pdf). Returns the engine used."""
    order: list[str]
    if engine == "auto":
        order = [e for e in ("word", "libreoffice") if e in available_engines()] + ["none"]
    else:
        order = [engine]
    last_error = None
    for eng in order:
        try:
            if eng == "word":
                if sys.platform == "win32":
                    _word_windows(raw_docx, out_docx, out_pdf, log)
                elif sys.platform == "darwin":
                    _word_mac(raw_docx, out_docx, out_pdf, log)
                else:
                    raise EngineError("Word gibt es nur unter Windows/macOS")
            elif eng == "libreoffice":
                _libreoffice(raw_docx, out_docx, out_pdf, log)
            elif eng == "none":
                shutil.copyfile(raw_docx, out_docx)
                if out_pdf:
                    log("Kein PDF erzeugt (Word/LibreOffice nicht verfügbar). "
                        "Word aktualisiert Inhaltsverzeichnis und Seitenzahlen beim Öffnen.")
            else:
                raise EngineError(f"Unbekannte Engine '{eng}'")
            return eng
        except Exception as exc:  # try next engine
            last_error = exc
            log(f"Engine '{eng}' fehlgeschlagen: {exc}")
    raise EngineError(f"Kein Layout-Programm hat funktioniert: {last_error}")


# ---------------------------------------------------------------- Word / Windows

def _word_windows(src: Path, out_docx: Path, out_pdf: Path | None, log: Log) -> None:
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore

    log("Word (Windows): Felder aktualisieren …")
    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = None
    try:
        doc = word.Documents.Open(str(src.resolve()), ConfirmConversions=False,
                                  ReadOnly=False, AddToRecentFiles=False)
        for _ in range(2):  # 2nd pass: TOC length may shift page numbers
            doc.Fields.Update()
            for toc in doc.TablesOfContents:
                toc.Update()
            for story in doc.StoryRanges:
                story.Fields.Update()
        doc.SaveAs2(str(out_docx.resolve()), FileFormat=16)  # wdFormatDocumentDefault
        if out_pdf:
            log("Word (Windows): PDF exportieren …")
            doc.ExportAsFixedFormat(str(out_pdf.resolve()), ExportFormat=17,  # PDF
                                    CreateBookmarks=1)  # headings -> PDF bookmarks
    finally:
        if doc is not None:
            doc.Close(SaveChanges=0)
        word.Quit()
        pythoncom.CoUninitialize()


# ---------------------------------------------------------------- Word / macOS

_APPLESCRIPT = r'''
on run argv
    set srcPath to item 1 of argv
    set docxPath to item 2 of argv
    set pdfPath to item 3 of argv
    tell application "Microsoft Word"
        set theDoc to open file name (POSIX file srcPath as string)
        repeat 2 times
            set fieldCount to count of fields of theDoc
            repeat with i from 1 to fieldCount
                try
                    update field (field i of theDoc)
                end try
            end repeat
            repeat with i from 1 to (count of tables of contents of theDoc)
                update (table of contents i of theDoc)
            end repeat
        end repeat
        save as theDoc file name (POSIX file docxPath as string) file format format document
        if pdfPath is not "" then
            save as theDoc file name (POSIX file pdfPath as string) file format format PDF
        end if
        close theDoc saving no
    end tell
end run
'''


def _word_mac(src: Path, out_docx: Path, out_pdf: Path | None, log: Log) -> None:
    # Word for Mac is sandboxed: it can always read/write its own container folder.
    container = Path.home() / "Library" / "Containers" / "com.microsoft.Word" / "Data" / "clipbook"
    container.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    w_src = container / f"in_{tag}.docx"
    w_docx = container / f"out_{tag}.docx"
    w_pdf = container / f"out_{tag}.pdf"
    shutil.copyfile(src, w_src)
    log("Word (macOS): Felder aktualisieren …")
    try:
        proc = subprocess.run(
            ["osascript", "-e", _APPLESCRIPT, str(w_src), str(w_docx), str(w_pdf) if out_pdf else ""],
            capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            raise EngineError(proc.stderr.strip() or "AppleScript-Fehler")
        shutil.move(str(w_docx), out_docx)
        if out_pdf:
            shutil.move(str(w_pdf), out_pdf)
    finally:
        for f in (w_src, w_docx, w_pdf):
            f.unlink(missing_ok=True)


# ---------------------------------------------------------------- LibreOffice

_BASIC_MODULE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Clipbook" script:language="StarBasic">
Sub UpdateAndExport(src As String, pdf As String)
  Dim args(0) As New com.sun.star.beans.PropertyValue
  args(0).Name = &quot;Hidden&quot;
  args(0).Value = True
  doc = StarDesktop.loadComponentFromURL(ConvertToURL(src), &quot;_blank&quot;, 0, args())
  For pass = 1 To 2
    idx = doc.getDocumentIndexes()
    For i = 0 To idx.getCount() - 1
      idx.getByIndex(i).update()
    Next i
    doc.getTextFields().refresh()
    doc.refresh()
  Next pass
  Dim f(0) As New com.sun.star.beans.PropertyValue
  f(0).Name = &quot;FilterName&quot;
  f(0).Value = &quot;writer_pdf_Export&quot;
  doc.storeToURL(ConvertToURL(pdf), f())
  doc.close(True)
  StarDesktop.terminate()
End Sub
</script:module>
"""

_SCRIPT_XLB = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE library:library PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "library.dtd">
<library:library xmlns:library="http://openoffice.org/2000/library" library:name="Standard" library:readonly="false" library:passwordprotected="false">
 <library:element library:name="Module1"/>
 <library:element library:name="Clipbook"/>
</library:library>
"""


def _soffice(soffice: Path, profile: Path, *args: str, timeout: int = 900):
    cmd = [str(soffice), "--headless", "--invisible", "--nologo", "--norestore", "--nodefault",
           "-env:UserInstallation=" + profile.resolve().as_uri(), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _libreoffice(src: Path, out_docx: Path, out_pdf: Path | None, log: Log) -> None:
    found = find_libreoffice()
    if not found:
        raise EngineError("LibreOffice nicht gefunden")
    soffice = found[0]
    # The .docx is delivered as generated (Word refreshes its fields on open);
    # LibreOffice only renders the PDF with an up-to-date TOC and page numbers.
    shutil.copyfile(src, out_docx)
    if not out_pdf:
        return
    log("LibreOffice: Inhaltsverzeichnis aktualisieren und PDF erzeugen …")
    with tempfile.TemporaryDirectory(prefix="clipbook-lo-") as tmp:
        tmp_path = Path(tmp)
        profile = tmp_path / "profile"
        # 1) create a fresh profile, 2) add our macro to "My Macros", 3) run it
        _soffice(soffice, profile, "--terminate_after_init", timeout=300)
        std = profile / "user" / "basic" / "Standard"
        if not std.exists():
            raise EngineError("LibreOffice-Profil konnte nicht angelegt werden")
        (std / "Clipbook.xba").write_text(_BASIC_MODULE, encoding="utf-8")
        (std / "script.xlb").write_text(_SCRIPT_XLB, encoding="utf-8")
        in_doc = tmp_path / "in.docx"
        pdf_tmp = tmp_path / "out.pdf"
        shutil.copyfile(src, in_doc)
        macro = 'macro:///Standard.Clipbook.UpdateAndExport("%s","%s")' % (in_doc, pdf_tmp)
        proc = _soffice(soffice, profile, macro)
        if not pdf_tmp.exists():
            raise EngineError((proc.stderr or proc.stdout).strip()[-2000:] or "kein PDF erzeugt")
        shutil.move(str(pdf_tmp), out_pdf)
