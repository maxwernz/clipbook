# Verteilen und Aktualisieren

## Kurzfassung

1. Version erhöhen (`src/clipbook/__init__.py` und `pyproject.toml`), Abschnitt in `CHANGELOG.md` schreiben.
2. `git tag v0.3.0 && git push origin main v0.3.0`
3. GitHub baut automatisch Windows-Setup und Mac-Apps (Apple Silicon und Intel), testet sie und legt eine
   Version unter **Releases** an.
4. Version auf das Netzlaufwerk bringen:
   `uv run python tools/publish_update.py --github v0.3.0 --to "<Bibliothek>/updates"`
5. Fertig. Jede installierte App meldet beim nächsten Start „Version 0.3.0 ist verfügbar“ und
   installiert sie auf Knopfdruck selbst.

## Woher holt sich die App Updates?

Die App sucht in dieser Reihenfolge nach `latest.json` und nimmt die neueste Version, die sie findet:

| | Quelle | Wofür |
|---|---|---|
| 1 | Einstellungen → Update-Quelle | Ausnahme für einen einzelnen Rechner |
| 2 | `update_feed:` in `library.yaml` | zentral für alle, z. B. ein interner Webserver |
| 3 | Ordner `updates/` in der Bibliothek | **Standard**: das Netzlaufwerk mit der Bibliothek |
| 4 | GitHub-Release des Projekts | nur erreichbar, wenn das Repository öffentlich ist |

Ist eine Quelle nicht erreichbar, wird sie still übersprungen (steht im Protokoll).

## Sicherheit

- Jede Datei hat in `latest.json` eine **SHA-256-Prüfsumme** und eine Größe. Passt eine davon nicht,
  wird das Update verworfen, und es wird nichts installiert.
- `latest.json` wird als Letztes und in einem Schritt geschrieben. Eine App sieht also nie eine
  halb kopierte Version.
- Mac: Vor dem Austausch wird die Signatur der neuen App geprüft. Schlägt der Austausch fehl, bleibt die
  alte App erhalten.
- Windows: Installation pro Benutzer nach `%LOCALAPPDATA%\Programs\Clipbook`, ohne
  Administratorrechte. Das Update läuft still und startet die App danach neu.

## Erstinstallation

**Windows:** `Clipbook-<Version>-Setup.exe` ausführen. Das Programm ist (noch) nicht
signiert. Wurde die Datei aus dem Internet oder aus Teams geladen, zeigt Windows eventuell
„Der Computer wurde durch Windows geschützt“ → *Weitere Informationen* → *Trotzdem ausführen*.
Spätere Updates zeigen diese Meldung nicht.

**Mac:** `Clipbook-<Version>-macOS-arm64.dmg` (Apple Silicon) bzw. `-x86_64` (Intel) öffnen
und die App in „Programme“ ziehen. Die App ist nicht bei Apple notarisiert. Kommt sie aus dem Internet,
blockiert macOS den ersten Start: *Systemeinstellungen → Datenschutz & Sicherheit → Trotzdem öffnen*.
Vom Netzlaufwerk kopiert, startet sie normalerweise direkt. Spätere Updates zeigen die Meldung nicht.

Beim ersten Start fragt die App nach der Bibliothek (Ordner auf dem Netzlaufwerk).

## Empfehlung für später

Für eine Verteilung ganz ohne Warnungen: ein Code-Signing-Zertifikat für Windows und eine Apple
Developer ID (99 €/Jahr) für die Notarisierung. Beides lässt sich in `tools/build_release.py` ergänzen.

## Protokolle

- Mac: `~/Library/Logs/Clipbook/` (`app.log`, `update.log`)
- Windows: `%LOCALAPPDATA%\Clipbook\Logs\`, Setup-Protokoll: `%TEMP%\Clipbook-update.log`

## Lokal bauen

```bash
uv run python tools/build_release.py        # baut für diesen Rechner, inkl. Selbsttest
uv run python tools/publish_update.py release/0.3.0 --to "<Bibliothek>/updates"
```

Windows braucht dafür [Inno Setup 6](https://jrsoftware.org/isdl.php).
