"""Look & feel: Profil-Clip colors (from profil-clip.de) and the Manrope font, identical on macOS and Windows."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

ACCENT = "#0160b2"
ACCENT_HOVER = "#014d8e"
TEXT = "#212121"
MUTED = "#6c6c6c"
BORDER = "#e3e6ea"
BG = "#f3f5f8"
OK = "#1e7d4f"
WARN = "#a15c00"
ERROR = "#b42318"

QSS = f"""
* {{ font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog, #page {{ background: {BG}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

#sidebar {{ background: #ffffff; border-right: 1px solid {BORDER}; }}
#appName {{ font-size: 13px; font-weight: 700; color: {ACCENT}; }}
#appSub {{ color: {MUTED}; font-size: 11px; }}
#navButton {{ text-align: left; padding: 9px 14px; border: none; border-radius: 8px;
              font-size: 14px; background: transparent; }}
#navButton:hover {{ background: #f0f3f8; }}
#navButton:checked {{ background: #e5eff9; color: {ACCENT}; font-weight: 600; }}

#title {{ font-size: 24px; font-weight: 650; }}
#titleEdit {{ font-size: 22px; font-weight: 650; border: 1px solid transparent; border-radius: 6px;
              background: transparent; padding: 2px 6px; }}
#titleEdit:hover {{ border-color: {BORDER}; background: #fff; }}
#titleEdit:focus {{ border-color: {ACCENT}; background: #fff; }}
#subtitle, #hint {{ color: {MUTED}; }}
#hint {{ font-size: 12px; }}
#sectionTitle {{ font-size: 15px; font-weight: 650; }}
#stepNumber {{ background: {ACCENT}; color: white; border-radius: 11px; font-weight: 700;
               min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; }}
#slotLabel {{ color: {MUTED}; }}
#fixed {{ color: {MUTED}; }}

#card, #machineCard, #moduleRow {{ background: #ffffff; border: 1px solid {BORDER}; border-radius: 12px; }}
#machineCard:hover {{ border-color: {ACCENT}; }}
#cardTitle {{ font-size: 15px; font-weight: 650; }}
#chip {{ background: #eef2f7; border-radius: 9px; padding: 2px 8px; color: #3b4456; font-size: 11px; }}
#chipMissing {{ background: #fdf3e7; border-radius: 9px; padding: 2px 8px; color: {WARN}; font-size: 11px; }}

QPushButton {{ padding: 7px 14px; border: 1px solid #cfd6e1; border-radius: 8px; background: #ffffff; }}
QPushButton:hover {{ background: #f0f3f8; }}
QPushButton:disabled {{ color: #a3aab8; }}
QPushButton#primary {{ background: {ACCENT}; color: white; border: none; font-weight: 600;
                       padding: 10px 20px; font-size: 14px; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: #a9bfdc; color: white; }}
QPushButton#link {{ border: none; background: transparent; color: {ACCENT}; padding: 4px 2px; }}
QPushButton#link:hover {{ text-decoration: underline; }}
QPushButton#seg {{ border-radius: 0; padding: 6px 14px; margin: 0; }}
QPushButton#segFirst {{ border-top-right-radius: 0; border-bottom-right-radius: 0; padding: 6px 14px; }}
QPushButton#segLast {{ border-top-left-radius: 0; border-bottom-left-radius: 0; padding: 6px 14px; }}
QPushButton#seg:checked, QPushButton#segFirst:checked, QPushButton#segLast:checked {{
    background: {ACCENT}; color: white; border-color: {ACCENT}; }}
QToolButton#more {{ border: none; padding: 4px 8px; border-radius: 6px; font-size: 16px; }}
QToolButton#more:hover {{ background: #f0f3f8; }}
QToolButton#more::menu-indicator {{ image: none; }}

QLineEdit, QComboBox, QPlainTextEdit {{ padding: 6px 8px; border: 1px solid #cfd6e1; border-radius: 6px;
                                         background: #ffffff; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{ image: url({{ICONS}}/chevron.svg); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ border: 1px solid {BORDER}; border-radius: 6px; padding: 4px;
                               background: #fff; selection-background-color: #e5eff9;
                               selection-color: {TEXT}; outline: none; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1.5px solid #b8c1cf; border-radius: 4px;
                        background: #fff; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT};
                                image: url({{ICONS}}/check.svg); }}
QRadioButton::indicator {{ width: 16px; height: 16px; border: 1.5px solid #b8c1cf; border-radius: 9px;
                           background: #fff; }}
QRadioButton::indicator:checked {{ border: 5px solid {ACCENT}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #c9d0db; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #aab3c2; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #c9d0db; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
#page {{ background: {BG}; }}
#panel {{ background: #ffffff; border: 1px solid {BORDER}; border-radius: 14px; }}
#panel[dropTarget="true"] {{ border: 2px dashed {ERROR}; background: #fff7f7; }}
#panelTitle {{ font-size: 16px; font-weight: 650; }}
#panelCaption {{ color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
#subCard {{ background: #f8fafc; border: 1px solid {BORDER}; border-radius: 10px; }}
#fieldLabel {{ color: {MUTED}; font-size: 11px; }}

#machineItem {{ border-radius: 10px; border: 1px solid transparent; }}
#machineItem:hover {{ background: #f3f6fa; }}
#machineItem[selected="true"] {{ background: #e5eff9; border-color: #b9d3ee; }}
#machineName {{ font-weight: 600; }}

#tile {{ background: #ffffff; border: 1px solid {BORDER}; border-radius: 12px; }}
#tile:hover {{ border-color: {ACCENT}; background: #fbfdff; }}
#tile[used="true"] {{ background: #f6faf7; border-color: #bfe0cc; }}
#tileTitle {{ font-weight: 650; font-size: 13px; }}
#chapterTile {{ background: #ffffff; border: 1px solid {BORDER}; border-radius: 10px; }}
#chapterTile:hover {{ border-color: {ACCENT}; }}
#chapterNo {{ color: {ACCENT}; font-weight: 700; font-size: 15px; }}
#outlineText {{ font-size: 12px; color: #3b4456; }}
#dropIndicator {{ background: {ACCENT}; border-radius: 2px; }}
#emptyDrop {{ border: 2px dashed #c3cbd8; border-radius: 12px; color: {MUTED}; font-size: 14px;
              background: #fafbfd; }}

QToolButton#iconButton {{ border: none; border-radius: 6px; padding: 5px; background: transparent; }}
QToolButton#iconButton:hover {{ background: #eef2f7; }}
QToolButton#iconButton::menu-indicator {{ image: none; width: 0; }}
QPushButton#flat {{ border: none; background: transparent; color: #3b4456; padding: 6px 8px;
                    text-align: left; }}
QPushButton#flat:hover {{ background: #eef2f7; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: #cfe0f3; border-radius: 3px; }}
QSplitter#mainSplit::handle {{ background: {BORDER}; }}
QSplitter#mainSplit::handle:hover {{ background: {ACCENT}; }}
#updateBanner {{ background: {ACCENT}; }}
#bannerText {{ color: #ffffff; }}
QPushButton#bannerPrimary {{ background: #ffffff; color: {ACCENT}; border: none; font-weight: 650; padding: 6px 14px; }}
QPushButton#bannerPrimary:hover {{ background: #e5eff9; }}
QPushButton#bannerLink {{ background: transparent; border: none; color: #dbe9f7; padding: 6px 8px; }}
QPushButton#bannerLink:hover {{ color: #ffffff; text-decoration: underline; }}
QToolTip {{ background: #212121; color: #ffffff; border: none; padding: 6px 8px; border-radius: 6px; }}
QMenu {{ background: #fff; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: #e5eff9; color: {TEXT}; }}

QTreeWidget#preview {{ border: none; background: transparent; }}
QTreeWidget#preview::item {{ padding: 3px 0; }}
QTreeWidget#preview::item:selected {{ background: #e5eff9; color: {TEXT}; }}

QProgressBar {{ border: none; background: #e7ecf3; border-radius: 3px; max-height: 6px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; background: #fff; top: -1px; }}
QTabBar::tab {{ padding: 7px 14px; border: none; color: {MUTED}; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; font-weight: 600; }}
QTableWidget {{ border: none; gridline-color: {BORDER}; }}
QHeaderView::section {{ background: #f6f8fb; border: none; border-bottom: 1px solid {BORDER};
                        padding: 6px; font-weight: 600; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 10px; margin-top: 14px; padding: 12px;
             background: #fff; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; font-weight: 600; }}
"""


_CHEVRON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12"><path d="M2.5 4.5l3.5 3.5 3.5-3.5" '
            'fill="none" stroke="#6c6c6c" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')
_CHECK = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-6.5" '
          'fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def _icon_dir() -> str:
    d = Path(tempfile.gettempdir()) / "clipbook-icons"
    d.mkdir(exist_ok=True)
    (d / "chevron.svg").write_text(_CHEVRON, encoding="utf-8")
    (d / "check.svg").write_text(_CHECK, encoding="utf-8")
    return d.as_posix()


ASSETS = Path(__file__).resolve().parent / "assets"


def load_font(app: QApplication) -> None:
    """Manrope is the font of profil-clip.de (SIL Open Font License, bundled)."""
    fid = QFontDatabase.addApplicationFont(str(ASSETS / "Manrope.ttf"))
    families = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
    if families:
        f = QFont(families[0])
        f.setPixelSize(13)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        app.setFont(f)


def apply(app: QApplication) -> None:
    app.setStyle(QStyleFactory.create("Fusion"))
    load_font(app)
    pal = QPalette()
    for role, color in ((QPalette.ColorRole.Window, BG), (QPalette.ColorRole.Base, "#ffffff"),
                        (QPalette.ColorRole.AlternateBase, "#f7f9fc"), (QPalette.ColorRole.Text, TEXT),
                        (QPalette.ColorRole.WindowText, TEXT), (QPalette.ColorRole.Button, "#ffffff"),
                        (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
                        (QPalette.ColorRole.HighlightedText, "#ffffff"),
                        (QPalette.ColorRole.PlaceholderText, "#9aa2b1"),
                        (QPalette.ColorRole.ToolTipBase, "#ffffff"), (QPalette.ColorRole.ToolTipText, TEXT),
                        (QPalette.ColorRole.Link, ACCENT), (QPalette.ColorRole.LinkVisited, ACCENT_HOVER)):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(QSS.replace("{ICONS}", _icon_dir()))
