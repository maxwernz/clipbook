"""Clipbook – Betriebsanleitungen aus Bausteinen zusammenstellen."""

__version__ = "0.3.0"          # single source of truth (pyproject + release tag must match)
APP_NAME = "Clipbook"
BUNDLE_ID = "de.profilclip.clipbook"
GITHUB_REPO = "maxwernz/clipbook"


def main() -> int:
    from .cli import main as _main
    return _main()
