# Regeln für Word-Module

Damit Clipbook ein Modul richtig einbaut, gelten für die Word-Dateien ein paar einfache Regeln.
Beim Import prüft das Programm die Datei und zeigt Abweichungen an.

## Überschriften

- Überschriften immer mit den Formatvorlagen **Überschrift 1, 2, 3** formatieren, nicht nur fett.
- **Keine Kapitelnummern eintippen.** Statt „9.5.1 Drahtrollenwechsel“ nur „Drahtrollenwechsel“.
  Die Nummern vergibt Word beim Erstellen der Anleitung, je nachdem, wo das Modul steht.
- Ein Baugruppen-Modul (Clipper, Dosierung, Folie …) beginnt mit **einer** Überschrift 1
  (z. B. „Clipper DCX5S“). Alles andere darunter ist Überschrift 2 oder 3.
- Module der Art „Mehrere Kapitel“ (z. B. Allgemeines) dürfen mehrere Überschrift-1-Kapitel haben.
- Keine Bilder in die Überschriftenzeile setzen.

## Verweise

- Nicht „siehe Kap. 4.4“ schreiben, denn die Nummer ändert sich je nach Maschine.
  Besser: „siehe Kapitel „Abschaltprozeduren““.

## Platzhalter

Text, der sich je Maschine ändert, als Platzhalter in doppelten geschweiften Klammern schreiben:

| Platzhalter | Beispiel |
|---|---|
| `{{Maschinentyp}}` | SKT H10 |
| `{{Maschinenbezeichnung}}` | Schlauchbeutel-Abfüllautomat |
| `{{Kunde}}`, `{{Seriennummer}}`, `{{Baujahr}}`, `{{Dokumentnummer}}`, `{{Ausgabe}}` | |

Weitere Platzhalter können im Programm unter „Maschinendaten“ angelegt werden.

## Wartung, Ersatzteile, Störungen

Diese Angaben stehen **nicht** im Word-Text, sondern als Tabellen beim Modul
(im Programm: Modul doppelklicken → Reiter Wartung / Ersatzteile / Störungen).
Das Programm setzt sie automatisch ans Ende des Modul-Kapitels und baut daraus die
Gesamtübersichten (Wartungsplan, Verschleißteile, Fehlercode-Liste mit Seitenzahlen).

Soll eine Tabelle an einer bestimmten Stelle im Text stehen, schreibt man dort in eine
eigene Zeile:

- `{{ABSCHNITT_WARTUNG}}`, `{{ABSCHNITT_ERSATZTEILE}}`, `{{ABSCHNITT_STOERUNGEN}}`: Tabellen dieses Moduls
- `{{GESAMT_WARTUNGSPLAN}}`, `{{GESAMT_ERSATZTEILE}}`, `{{GESAMT_FEHLERCODES}}`: Übersicht über alle
  Module der Maschine (steht im Modul „Wartung und Störungen“)

## Übersetzungen

Jede Sprache ist eine eigene Datei im selben Modul (`de.docx`, `en.docx`, `it.docx`).
Import: „Word-Datei importieren“ → bestehendes Modul → Sprache wählen.
Die Tabellen (Wartung, Störungen …) werden im Modul-Fenster übersetzt: oben die Sprache umstellen.
Gelb markierte Zellen sind noch nicht übersetzt.

## Kopf- und Fußzeile

Kommen aus der Vorlage `templates/master.docx` (Logo, Dokumentart, Maschinentyp, Seitenzahl).
Kopf- und Fußzeilen in den Modulen werden ignoriert.
