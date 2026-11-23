# Dotationslisten

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-unterst%C3%BCtzen-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/rvalley98)

Handschriftlich ausgefüllte Abrechnungsformulare (Ausdrucke der Excel-Vorlage) scannen →
Werte prüfen → die Vorlage wird befüllt, Excel rechnet mit den eigenen Formeln.
Läuft komplett lokal: als Mac-/Windows-App oder per Docker auf einem Homeserver.

## Ablauf

1. Scanner legt PDFs per SMB in `data/eingang/` ab (oder Upload auf der Startseite).
2. Der Server liest die Datei ein, sobald sie fertig geschrieben ist:
   Seiten trennen, Leerseiten (Duplex-Rückseiten) überspringen, gedrehte Seiten aufrichten,
   Blatt am **gedruckten** Titel erkennen (Tesseract). Original → `data/archiv/`.
   Ein Stapel mit mehreren Abrechnungsbögen ergibt mehrere Vorgänge.
3. Erkennung der Handschrift mit einem lokalen Bildmodell über Ollama (optional, siehe unten).
4. Prüfseite: Scan links, Felder rechts. Rot = passt nicht (Datum, IBAN-Prüfziffer,
   Gliederungsnummer nicht in der Liste, ja/nein …). Speichern = geprüft.
5. „Excel erzeugen“ → `data/ausgang/<Datum> <Thema> (...).xlsx`.

Ohne Erkennung funktioniert alles genauso – die Felder werden dann von Hand eingetragen.

## Mac- und Windows-App

Eigenständige Apps ohne Docker: Mac mit Apple-Chip ab macOS 13, Windows 10/11 (64 Bit).
Enthalten Python, die App und Tesseract. Die Summen (Abrechnung, Verwendungsnachweis) rechnet
die App selbst (`app/formulas.py`) – weder Excel noch LibreOffice nötig; die erzeugten Dateien
öffnen Excel und LibreOffice gleichermaßen (sie rechnen beim Öffnen neu). LibreOffice braucht es
nur, um .xls-Dateien direkt einzulesen; Ollama (Handschrift) ist optional.

- Oberfläche im Browser unter http://127.0.0.1:8765 (nur lokal), Menüleisten- bzw.
  Taskleisten-Symbol (`desktop/launcher.py`). Version unten auf jeder Seite.
- Daten: `Dokumente/Dotationslisten` (Windows: liegt „Dokumente“ in OneDrive, dann
  `%USERPROFILE%\Dotationslisten`), über das Menü änderbar (z. B. NAS).
- Protokoll: `~/Library/Logs/Dotationslisten/app.log` bzw. `%LOCALAPPDATA%\Dotationslisten\Logs`.
- Nicht signiert/notarisiert: macOS → Systemeinstellungen → Datenschutz & Sicherheit →
  „Dennoch öffnen“; Windows → SmartScreen „Weitere Informationen“ → „Trotzdem ausführen“.
  Nutzer-Anleitungen: `macos/INSTALLATION.txt`, `windows/INSTALLATION.txt`.

**Bauen** – automatisch über GitHub Actions (`.github/workflows/build.yml`): Tests bei jedem Push;
Mac-DMG und Windows-Setup bei einem Versions-Tag (`git tag v1.0.1 && git push --tags` → Release
mit beiden Dateien) oder von Hand (Actions → Build → Run workflow → Artefakte). Beide Builds
starten die fertige App und lesen einen Test-Scan ein (`desktop/smoke_test.py`).

Lokal:
- Mac: `macos/build_app.sh` (Xcode-Befehlszeilenwerkzeuge, `brew install cmake uv`).
  Tesseract wird selbst kompiliert (`macos/build_tesseract.sh`, statisch, macOS ≥ 13).
- Windows: `windows\build_windows.ps1` (Python 3.12, Tesseract der UB Mannheim, Inno Setup 6).
- Versionsnummer in `VERSION`. Lizenztexte der mitgelieferten Komponenten sammelt
  `desktop/collect_licenses.py` (siehe `THIRD_PARTY_NOTICES.md`).

Tests nativ (wie in der Mac-App):

```sh
DATA_DIR=$PWD/data TESSERACT=$PWD/macos/build/tesseract/bin/tesseract \
TESSDATA_PREFIX=$PWD/macos/build/tesseract/tessdata macos/build/venv/bin/python -m pytest -q tests
```

## Verwendungsnachweis

Die Datei des Jahres („Anlage 3 – Verwendungsnachweis mit Raumkosten“, wie bisher ausgefüllt)
wird hochgeladen und bleibt unverändert; die App schreibt sie mit den fertigen Vorgängen in eine
neue Datei. Zuwendung (Anteil der Gliederung) und Mindestanteil Ausbildung + Übung sind in der App
einstellbar. Die Zellpositionen sind die dieses Formulars; beim Hochladen wird der Aufbau geprüft,
ein anderes Formular wird abgelehnt.

## Installation auf dem Server

```sh
git clone <repo> dotationslisten && cd dotationslisten
docker compose up -d --build        # Image wird auf dem Server gebaut (amd64)
```

Dann `http://<server>:8000` öffnen und einmalig die Vorlage („20250105 Muster.xls“) hochladen.
Alternativ: `docker compose exec app python -m app.setup_template "/data/vorlage/Muster.xls"`.

**Nur im Heimnetz betreiben.** Die Oberfläche hat kein Login, in den Daten stehen Namen und
IBANs. Port 8000 nicht im Router freigeben.

### Scanner-Ordner (SMB)

`data/eingang` auf dem Server als SMB-Freigabe einrichten (Samba des Betriebssystems bzw. die
Freigabe-Funktion von NAS/Unraid/OMV) und im Scanner als „Scan to Folder“-Ziel eintragen.
Der Container läuft als root und kann die Dateien lesen und verschieben.
Ältere Scanner können teils nur SMB1 – dann in Samba `server min protocol = NT1` nur für diese
Freigabe bzw. so eng wie möglich erlauben.

### Erkennung

Einstellung über `.env` neben der `docker-compose.yml`:

| Variante | `.env` | Hinweis |
|---|---|---|
| keine (Handeingabe) | `RECOGNIZER=none` | |
| auf dem Server (CPU) | – (Standard) und `docker compose --profile ollama up -d`, dann `docker compose exec ollama ollama pull qwen2.5vl:3b` + `OLLAMA_MODEL=qwen2.5vl:3b` | langsam (Minuten pro Seite), läuft nebenbei |
| auf dem Mac | `OLLAMA_URL=http://<mac>:11434` | Ollama auf dem Mac mit `OLLAMA_HOST=0.0.0.0` starten, damit es im LAN lauscht. Scans gehen dann unverschlüsselt durchs Heimnetz. |

Ist Ollama nicht erreichbar (Mac aus), warten die Seiten und werden erkannt, sobald es wieder
da ist. Wer eine Seite schon von Hand gespeichert hat, wird nicht mehr überschrieben.

## Entwicklung

```sh
docker build -t dotationslisten:dev .
docker run --rm -v $PWD:/srv -v $PWD/data:/data -w /srv dotationslisten:dev python -m pytest -q tests
```

Viele Tests brauchen `data/vorlage/vorlage.xlsx` und `data/verwendungsnachweis/original.xlsx`
(nicht im Repository) und werden sonst übersprungen. `app/fields.py` ist
die Feldkarte aller Eingabezellen; ein Test prüft sie gegen die freigegebenen Zellen der Vorlage.

## Lizenz

Copyright (c) 2026 Robin Valley. Alle Rechte vorbehalten – siehe [LICENSE](LICENSE).
Komponenten Dritter: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Unterstützen

Wenn dir die Dotationslisten helfen, freue ich mich über einen Kaffee: https://buymeacoffee.com/rvalley98
