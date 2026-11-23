# Dotationslisten

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-unterst%C3%BCtzen-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/rvalley98)

Handschriftlich ausgefüllte Abrechnungsformulare (Ausdrucke der Excel-Vorlage) scannen →
Werte prüfen → die Vorlage wird befüllt; dazu der Verwendungsnachweis des Jahres.
Eine installierbare App für Mac und Windows, die komplett auf dem eigenen Rechner läuft.

## Installation

Download unter [Releases](../../releases/latest):

- **Mac** (Apple-Chip, ab macOS 13): `Dotationslisten-<Version>.dmg` öffnen, App in „Programme“
  ziehen. Beim ersten Start: Systemeinstellungen → Datenschutz & Sicherheit → „Dennoch öffnen“.
- **Windows** (10/11, 64 Bit): `Dotationslisten-Setup-<Version>.exe` ausführen, keine
  Administratorrechte nötig. SmartScreen: „Weitere Informationen“ → „Trotzdem ausführen“.

Ausführliche Anleitungen für Nutzer: [macos/INSTALLATION.txt](macos/INSTALLATION.txt),
[windows/INSTALLATION.txt](windows/INSTALLATION.txt) (liegen auch DMG bzw. Setup bei).

Die App sitzt in der Menüleiste bzw. im Infobereich der Taskleiste und öffnet ihre Oberfläche im
Browser unter http://127.0.0.1:8765 – nur auf diesem Rechner erreichbar, ohne Login (in den
Daten stehen Namen und IBANs). Gibt es eine neue Version, zeigt die App oben einen Hinweis.

Optional, kostenlos:
- [Ollama](https://ollama.com/download) für die Handschrifterkennung (Modell per Knopf in der
  App, ca. 6 GB). Ohne Ollama werden die Werte von Hand eingetragen.
- [LibreOffice](https://de.libreoffice.org/download/download/) nur, um .xls-Dateien direkt
  einzulesen. Die Summen rechnet die App selbst (`app/formulas.py`); die erzeugten Dateien
  öffnen Excel und LibreOffice gleichermaßen.

## Ablauf

1. Einmalig die Vorlage hochladen (Startseite).
2. Scans als PDF hochladen oder vom Scanner in den Ordner `eingang` im Datenordner legen
   lassen. Die App trennt die Seiten, überspringt Leerseiten, richtet gedrehte Seiten auf und
   erkennt das Blatt am **gedruckten** Titel (Tesseract). Original → `archiv`.
   Ein Stapel mit mehreren Abrechnungsbögen ergibt mehrere Vorgänge.
3. Handschrift erkennen lassen (Ollama) oder von Hand eintragen.
4. Prüfseite: Scan links, Felder rechts. Rot = passt nicht (Datum, IBAN-Prüfziffer,
   Gliederungsnummer, ja/nein …). Speichern = geprüft.
5. „Excel erzeugen“ → `ausgang/<Datum> <Thema> (...).xlsx`.

Außerdem: Abrechnungen ganz von Hand anlegen, bestehende Excel-Abrechnungen importieren, alle
Excel-Dateien auf einmal erzeugen.

### Daten

`Dokumente/Dotationslisten` (Windows: liegt „Dokumente“ in OneDrive, dann
`%USERPROFILE%\Dotationslisten`, damit nichts ungefragt in die Cloud geht). Über das Menü
änderbar, z. B. auf ein NAS. Jeder Vorgang ist ein Ordner mit `job.json` und den Seitenbildern
unter `arbeit/` – bitte regelmäßig sichern. Protokoll: `~/Library/Logs/Dotationslisten/app.log`
bzw. `%LOCALAPPDATA%\Dotationslisten\Logs\app.log`.

Scanner: den Ordner `eingang` freigeben (bzw. auf dem NAS anlegen und den Datenordner dorthin
legen) und im Scanner als „Scan to Folder“-Ziel eintragen. Neue Dateien werden eingelesen, sobald
sie fertig geschrieben sind.

### Verwendungsnachweis

Die Datei des Jahres („Anlage 3 – Verwendungsnachweis mit Raumkosten“, wie bisher ausgefüllt)
wird hochgeladen und bleibt unverändert; die App schreibt sie mit den fertigen Vorgängen in eine
neue Datei und zeigt die Aufteilung der Verwendung. Zuwendung (Anteil der Gliederung) und
Mindestanteil Ausbildung + Übung sind einstellbar. Die Zellpositionen sind die dieses Formulars;
beim Hochladen wird der Aufbau geprüft, ein anderes Formular wird abgelehnt.

## Entwicklung

Python 3.12. Die App ist FastAPI + Jinja2 (`app/`), gestartet vom Desktop-Launcher
(`desktop/launcher.py`: Server auf 127.0.0.1, Menüleiste/Taskleiste, Datenordner).

```sh
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt rumps   # Windows: pystray
DATA_DIR=$PWD/data .venv/bin/python desktop/launcher.py
```

Tests: `DATA_DIR=$PWD/data python -m pytest -q`. Viele Tests brauchen die Vorlage
(`data/vorlage/vorlage.xlsx`, entsteht beim Hochladen) und `data/verwendungsnachweis/original.xlsx`
– beide nicht im Repository – und werden sonst übersprungen. Für die Erkennungs-Tests ein
Tesseract mit deutschen Sprachdaten (`TESSERACT`, `TESSDATA_PREFIX`, z. B. aus `macos/build`).
`app/fields.py` ist die Feldkarte aller Eingabezellen; ein Test prüft sie gegen die Vorlage.

### Bauen und veröffentlichen

GitHub Actions (`.github/workflows/build.yml`): Tests bei jedem Push. Bei einem Versions-Tag
werden Mac-DMG und Windows-Setup gebaut, gestartet und mit einem Test-Scan geprüft
(`desktop/smoke_test.py`), dann als Release veröffentlicht:

```sh
echo 1.2.0 > VERSION && git commit -am "Version 1.2.0" && git tag v1.2.0 && git push && git push --tags
```

Lokal:
- Mac: `macos/build_app.sh` (Xcode-Befehlszeilenwerkzeuge, `brew install cmake uv`).
  Tesseract wird selbst kompiliert (`macos/build_tesseract.sh`, statisch, macOS ≥ 13) –
  Homebrew-Programme laufen nur auf dem macOS, für das sie gebaut wurden.
- Windows: `windows\build_windows.ps1` (Python 3.12, Tesseract der UB Mannheim, Inno Setup 6).

Die Apps sind nicht signiert bzw. notarisiert (kein Apple-Developer-Konto, kein
Code-Signing-Zertifikat) – daher die Warnungen beim ersten Start.

## Lizenz

Copyright (c) 2026 Robin Valley. Alle Rechte vorbehalten – siehe [LICENSE](LICENSE).
Komponenten Dritter: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Unterstützen

Wenn dir die Dotationslisten helfen, freue ich mich über einen Kaffee: https://buymeacoffee.com/rvalley98
