# PyInstaller recipe. Use the release script instead of calling this directly:
#     uv run python tools/build_release.py
# Produces dist/Clipbook.app (macOS) or dist/Clipbook/Clipbook.exe (Windows).
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
init = (ROOT / "src" / "clipbook" / "__init__.py").read_text(encoding="utf-8")
VERSION = re.search(r'__version__ = "([^"]+)"', init).group(1)
APP_NAME = re.search(r'APP_NAME = "([^"]+)"', init).group(1)
BUNDLE_ID = re.search(r'BUNDLE_ID = "([^"]+)"', init).group(1)
ICON = ROOT / "packaging" / "icon"

datas = collect_data_files("docx") + collect_data_files("docxcompose") + collect_data_files("certifi") + [
    (str(ROOT / "src" / "clipbook" / "gui" / "assets"), "clipbook/gui/assets"),
    (str(ROOT / "src" / "clipbook" / "panel" / "template"), "clipbook/panel/template")]
hidden = ["truststore"]
if sys.platform == "win32":
    hidden += ["win32com", "win32com.client", "pythoncom", "pywintypes"]

a = Analysis([str(ROOT / "packaging" / "launch.py")], pathex=[str(ROOT / "src")], datas=datas,
             hiddenimports=hidden,
             excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
                       "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts",
                       "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtWebSockets"])
pyz = PYZ(a.pure)
version_file = str(ROOT / "build" / "version_info.txt") if sys.platform == "win32" else None
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APP_NAME, console=False, upx=False,
          icon=str(ICON / ("app_icon.ico" if sys.platform == "win32" else "app_icon.icns")),
          version=version_file)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)
if sys.platform == "darwin":
    app = BUNDLE(coll, name=f"{APP_NAME}.app", icon=str(ICON / "app_icon.icns"), bundle_identifier=BUNDLE_ID,
                 version=VERSION,
                 info_plist={
                     "CFBundleDisplayName": APP_NAME,
                     "CFBundleName": APP_NAME,
                     "CFBundleShortVersionString": VERSION,
                     "CFBundleVersion": VERSION,
                     "LSMinimumSystemVersion": "11.0",
                     "NSHighResolutionCapable": True,
                     "NSRequiresAquaSystemAppearance": True,     # app has its own light theme
                     "NSHumanReadableCopyright": "© Profi L-Clip GmbH – interne Software",
                     "NSAppleEventsUsageDescription":
                         "Clipbook steuert Microsoft Word, um Inhaltsverzeichnis und PDF zu erzeugen.",
                 })
