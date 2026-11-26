# Dotationslisten

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-unterst%C3%BCtzen-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/rvalley98)

**Die Abrechnungen des Katastrophenschutzes einer DLRG-Gliederung digital erfassen: Papierbögen
scannen, Werte prüfen, Excel-Abrechnung und Verwendungsnachweis automatisch befüllen.**

Entstanden aus der Arbeit als Referent Katastrophenschutz einer DLRG-Ortsgruppe. Eine
installierbare App für Mac und Windows, die komplett auf dem eigenen Rechner läuft – ohne
Server, ohne Cloud, ohne Konto. Texterkennung (Tesseract) und Handschrifterkennung (Ollama) sind
dabei.

> Kein offizielles Angebot der DLRG. Die App arbeitet mit der Excel-Vorlage, die die Gliederung
> ohnehin verwendet, und ändert nichts an den Abrechnungsregeln.

## Worum es geht

Für jeden Ausbildungsabend und jede Übung im Katastrophenschutz (KatS) wird eine Abrechnung
fällig: Veranstaltungsabrechnung, Teilnehmerliste mit Unterschriften, Tagegeld bzw.
Aufwandsvergütung, Fahrtkosten, bei Tauchübungen das Tauchprotokoll. Ausgedruckt und vor Ort von
Hand ausgefüllt, müssen die Bögen danach in die Excel-Vorlage abgetippt werden – und am Jahresende
noch einmal, Zeile für Zeile, in den Verwendungsnachweis der Zuwendung.

Die App nimmt dieses doppelte Abtippen ab:

1. **Scannen.** Den ganzen Stapel einer Veranstaltung als PDF einscannen – Reihenfolge,
   Leerseiten und auf dem Kopf liegende Blätter sind egal.
2. **Erkennen.** Die App sortiert jede Seite dem richtigen Blatt zu (am gedruckten Titel) und
   liest auf Wunsch auch die Handschrift.
3. **Prüfen.** Scan und Eingabefelder nebeneinander, Auffälliges ist rot markiert.
4. **Excel.** Die Vorlage wird befüllt – genau so, als hätte man sie von Hand ausgefüllt.
5. **Verwendungsnachweis.** Alle fertigen Abrechnungen eines Jahres landen mit einem Klick im
   Kostenblatt; die App zeigt, ob der Mindestanteil für Ausbildung und Übung erreicht ist.

### Erkannte Blätter

| Blatt der Vorlage | Inhalt |
|---|---|
| Veranstaltungsabrechnung (Abrechnungsbogen) | Thema, Art (Ausbildung/Übung/…), Ort, Gliederungsnummer, Beginn/Ende, Kosten, Anteil KatS, DLRG-eigene Fahrzeuge |
| Teilnehmerliste | Name, Vorname, Wohnort je Teilnehmer |
| Tagegeld / Aufwandsvergütung | außerhalb der Gemeinde, Anzahl Tagegeld/Aufwandsvergütung, gezählte Unterschriften |
| Abrechnung Fahrtkosten KatS (mehrere) | Fahrer, Kennzeichen, IBAN, Kilometer, Mitfahrer, Anhänger |
| Tauchprotokoll | Tauchtrupps (Sicherheitstaucher, 1.–3. Taucher) |

Was sich aus anderen Blättern ergibt (Kopfdaten, Summen, Pauschalen), rechnet die Vorlage selbst –
die App schreibt nur in die Eingabefelder.

## Installation

Download der neuesten Version unter [Releases](../../releases/latest).

**Mac** (Apple-Chip M1 oder neuer, macOS 13 oder neuer)
1. `Dotationslisten-<Version>.dmg` öffnen, „Dotationslisten“ in „Programme“ ziehen.
2. Erster Start: macOS meldet, dass die App nicht geprüft werden kann → „Fertig“ →
   Systemeinstellungen → Datenschutz & Sicherheit → bei „Dotationslisten“ „Dennoch öffnen“.
   Nur einmal nötig.

**Windows** (10 oder 11, 64 Bit)
1. `Dotationslisten-Setup-<Version>.exe` starten – keine Administratorrechte nötig.
2. Erscheint „Der Computer wurde durch Windows geschützt“: „Weitere Informationen“ →
   „Trotzdem ausführen“. Nur einmal nötig.

Die Warnungen kommen, weil die App nicht bei Apple bzw. Microsoft signiert ist (das kostet
jährliche Gebühren); an der App selbst ändert das nichts.

Ausführliche Anleitungen zum Weitergeben: [macos/INSTALLATION.txt](macos/INSTALLATION.txt),
[windows/INSTALLATION.txt](windows/INSTALLATION.txt) – sie liegen auch der DMG bzw. dem Setup bei.

### Nach dem Start

Die App sitzt als kleines Symbol in der Menüleiste (Mac) bzw. im Infobereich der Taskleiste
(Windows) und öffnet ihre Oberfläche im Browser unter http://127.0.0.1:8765. Diese Adresse ist
nur auf dem eigenen Rechner erreichbar. Über das Symbol: Öffnen, Datenordner zeigen,
Datenordner ändern, Protokoll, Beenden.

Erscheint eine neue Version, zeigt die App oben einen Hinweis mit Link zum Download. Zum
Aktualisieren einfach die neue Version drüberinstallieren – die Daten bleiben erhalten.

### Handschrifterkennung einrichten

Die Erkennung (Ollama) ist in der App enthalten und startet mit ihr. Nur das Erkennungsmodell
(qwen2.5vl, ca. 6 GB) wird einmalig nachgeladen: oben in der App auf „Modell jetzt laden“ klicken.
Danach läuft die Erkennung ohne Internet.

- Empfohlen: 16 GB Arbeitsspeicher. Mac mit Apple-Chip: meist unter einer Minute pro Seite.
  Windows: mit einer Nvidia-Grafikkarte schnell, sonst auf dem Prozessor mehrere Minuten pro Seite.
- Mac: braucht macOS 14 oder neuer; unter macOS 13 werden die Werte von Hand eingetragen.
- Ist Ollama schon separat installiert und gestartet, nutzt die App dieses (und dessen Modelle).
- Das Modell liegt im Benutzerordner unter `.ollama` (nicht im Datenordner) und bleibt beim
  Deinstallieren erhalten; zum Entfernen den Ordner `.ollama/models` löschen.

Ohne Modell funktioniert alles andere genauso – die Werte werden dann von Hand eingetragen.

### Optional: LibreOffice

[LibreOffice](https://de.libreoffice.org/download/download/) (kostenlos) wird nur gebraucht, um alte
`.xls`-Dateien direkt einzulesen. Die erzeugten `.xlsx`-Dateien öffnen Microsoft Excel und
LibreOffice gleichermaßen; alle Summen rechnet die App selbst.

## Arbeitsablauf

### 1. Vorlage hochladen (einmalig)

Auf der Startseite die Excel-Vorlage der Abrechnung hochladen, am besten als `.xlsx` (eine `.xls`
vorher in Excel „Speichern unter → Excel-Arbeitsmappe“). Die App prüft, ob alle bekannten Blätter
und Eingabefelder vorhanden sind. Gibt es eine neue Fassung der Vorlage, einfach erneut hochladen.

### 2. Scans einlesen

- **Hochladen** über die Startseite (PDF, auch mehrere auf einmal), oder
- **Scan-Ordner:** Der Scanner legt die PDFs direkt in den Ordner `eingang` im Datenordner. Neue
  Dateien werden eingelesen, sobald sie fertig geschrieben sind; das Original wandert nach
  `archiv`.

Jede Seite wird ausgerichtet, Leerseiten werden übersprungen, und die Seite wird anhand des
**gedruckten** Titels einem Blatt zugeordnet. Ein Stapel mit mehreren Veranstaltungsabrechnungen
wird automatisch in mehrere Vorgänge getrennt. Eine falsch zugeordnete Seite lässt sich von Hand
einem anderen Blatt zuweisen, ein fehlendes Blatt von Hand hinzufügen.

### 3. Erkennen und prüfen

Ist das Erkennungsmodell geladen, füllt die App die Felder automatisch vor („Neu erkennen“
wiederholt das für eine Seite); sonst werden sie von Hand eingetragen.
Auf der Prüfseite steht der Scan links, die Felder rechts. Rot markiert ist, was nicht passt:

- Datum, Uhrzeit, Beträge, Kilometer oder Prozent nicht als solche lesbar
- „ja/nein“- und Auswahlfelder mit einem nicht erlaubten Wert
- IBAN mit falscher Prüfziffer
- Gliederungsnummer, die nicht in der Gliederungsliste der Vorlage steht

Die Teilnehmeranzahl für Tagegeld bzw. Aufwandsvergütung zählt die App selbst: aus den
Unterschriften auf dem Tagegeld-Blatt, ersatzweise aus der Teilnehmerliste.

Mit „Speichern“ gilt das Blatt als geprüft. Erst wenn alle Blätter eines Vorgangs geprüft sind,
geht er in den Verwendungsnachweis.

### 4. Excel erzeugen

„Excel erzeugen“ schreibt die Werte in eine Kopie der Vorlage:
`ausgang/<JJJJMMTT> <Thema> (…).xlsx`. Die Datei ist eine ganz normale Abrechnung zum Ausdrucken,
Weitergeben oder Nachbearbeiten. Wird ein Vorgang danach noch geändert, weist die App darauf hin,
dass die Excel-Datei neu erzeugt werden sollte. „Alle neu erzeugen“ macht das für alle Vorgänge auf einmal.

Außerdem: Abrechnungen ganz ohne Scan von Hand anlegen und bestehende Excel-Abrechnungen
(auch aus den Vorjahren, .xlsx oder .xls) importieren. Eine importierte Datei ist die fertige
Excel des Vorgangs: Sie landet unverändert in `ausgang` (eine .xls als .xlsx), ihre Summen gehen
in den Verwendungsnachweis, und „Alle neu erzeugen“ lässt sie in Ruhe. Was in der Datei von Hand
geändert wurde – ein geleertes oder überschriebenes Feld „Gezahlte Tagegelder“, eine leere
Teilnehmeranzahl, eine Formel in einem Eingabefeld –, wird so übernommen, dass auch ein späteres
„Excel erzeugen“ dieselben Summen ergibt. Dieselbe Datei zweimal zu importieren legt keinen
zweiten Vorgang an.

### 5. Verwendungsnachweis

Hochgeladen wird die Datei des Jahres („Anlage 3 – Verwendungsnachweis mit Raumkosten“), so wie sie
bisher geführt wurde – mit Raumkosten, von Hand eingetragenen Zeilen und der Zuwendung. Diese Datei
bleibt unverändert. Die App schreibt sie zusammen mit den fertigen Vorgängen in eine **neue**
Datei `Verwendungsnachweis <Jahr>.xlsx`:

- je Vorgang eine Zeile im Kostenblatt: Gliederungsnummer, Art, Thema, Ort, Datum,
  Gesamtkosten, Anteil KatS
- übernommen werden nur Vorgänge des gewählten Jahres mit Art „Ausbildung“ oder „Übung“, die
  vollständig geprüft sind und deren Excel aktuell ist; die Übersicht nennt bei jedem anderen
  Vorgang den Grund
- Zeilen, die schon in der Datei stehen (gleiches Datum und Thema), werden nicht doppelt
  eingetragen

Die Seite zeigt die Summen für Übungen, Ausbildung und Verwaltung, den Eigenanteil und als Grafik
die Aufteilung der Ausgaben mit Markierungen für die Zuwendung und den Mindestanteil.
**Einstellbar** sind die Höhe der Zuwendung und der Mindestanteil Ausbildung + Übung
(voreingestellt 60 %); beides wird in die erzeugte Datei übernommen.

**Raumkosten (Verwaltung):** Die Verwaltungskosten kommen aus dem Blatt „Raumkosten“ – bis zu
10 Gebäude mit je 8 Räumen, jeder Raum mit Nutzungsart (Verwaltung oder Ausbildung), Größe, Miete
pro qm und KatS-Anteil. Die App liest diese Werte aus der hochgeladenen Datei und zeigt sie
mit den berechneten Kosten je Raum. Sie lassen sich dort bearbeiten; „Speichern & neu berechnen“
schreibt sie in die neue Datei, die hochgeladene bleibt unverändert. „Werte aus der Datei
übernehmen“ macht die Änderungen rückgängig. Wird ein neuer Verwendungsnachweis hochgeladen,
gelten dessen Raumkosten.

Die App kennt die Zellpositionen genau dieses Formulars. Beim Hochladen prüft sie den Aufbau; ein
anderes Formular wird mit Hinweis abgelehnt, statt falsche Zahlen zu liefern.

## Daten und Datenschutz

In den Abrechnungen stehen Namen, Wohnorte und IBANs der Helferinnen und Helfer. Deshalb:

- **Alles bleibt auf dem Rechner.** Scans, Erkennung (Tesseract und Ollama) und Excel laufen
  lokal. Verbindungen nach außen gibt es nur zwei, beide ohne Abrechnungsdaten: einmal täglich
  die Abfrage der neuesten Versionsnummer bei GitHub und – nur auf Knopfdruck – der einmalige
  Download des Erkennungsmodells von ollama.com. Die Cloud-Funktionen von Ollama sind
  abgeschaltet.
- **Kein Zugriff aus dem Netz.** Die Oberfläche ist nur unter 127.0.0.1 auf dem eigenen Rechner
  erreichbar – daher braucht sie auch kein Passwort. Den Rechner selbst mit einem Kennwort
  schützen.
- **Datenordner:** `Dokumente/Dotationslisten`. Unter Windows, wenn „Dokumente“ in OneDrive liegt,
  stattdessen `C:\Benutzer\<Name>\Dotationslisten`, damit nichts ungefragt in die Cloud
  synchronisiert wird.
- **Aufbau:** je Vorgang ein Ordner mit `job.json` (alle Werte) und den Seitenbildern unter
  `arbeit/`; dazu `vorlage/`, `verwendungsnachweis/`, `eingang/`, `archiv/`, `ausgang/`.
- **Sichern** (Time Machine, Windows-Dateiversionsverlauf oder NAS) und Altdaten nach Ablauf der
  Aufbewahrungsfristen löschen – dafür die Ordner der Vorgänge entfernen.
- **Deinstallieren** entfernt nur das Programm, der Datenordner bleibt.

### NAS und mehrere Rechner

Über „Datenordner ändern …“ kann der Datenordner auf ein NAS gelegt werden; der Scanner speichert
dann in den Ordner `eingang` auf dem NAS. Bestehende Vorgänge vorher selbst in den neuen Ordner
kopieren.

Es sollte immer nur **ein** Rechner gleichzeitig mit demselben Datenordner arbeiten. Arbeiten
zwei gleichzeitig am selben Vorgang, können Änderungen des einen verloren gehen.

## Hilfe bei Problemen

- **Die Seite öffnet sich nicht:** Über das Symbol in Menüleiste/Taskleiste „Öffnen“ wählen. Fehlt
  das Symbol, die App neu starten.
- **„Datei ist noch geöffnet“:** Die Excel-Datei ist in Excel oder LibreOffice offen – schließen
  und erneut erzeugen.
- **Seite falsch zugeordnet:** auf der Vorgangsseite das richtige Blatt auswählen. Meist war der
  gedruckte Titel abgeschnitten oder stark verschmutzt.
- **Handschrifterkennung sehr langsam:** normal ohne starke Grafikeinheit (Windows ohne
  Nvidia-Karte); Werte notfalls von Hand eintragen.
- **„Handschrifterkennung startet …“ bleibt stehen:** App beenden und neu starten; Details im
  Protokollordner in `ollama.log`.
- **Protokoll:** Menü „Protokoll anzeigen“ (Mac: `~/Library/Logs/Dotationslisten/app.log`,
  Windows: `%LOCALAPPDATA%\Dotationslisten\Logs\app.log`; daneben `ollama.log`) – bei Fehlermeldungen hilft es, den
  Inhalt mitzuschicken (vorher auf Namen/IBANs prüfen).

## Entwicklung

Python 3.12. FastAPI + Jinja2 (`app/`), gestartet vom Desktop-Launcher (`desktop/launcher.py`:
Server auf 127.0.0.1, Menüleiste/Taskleiste, Datenordner, Ollama). Bausteine:

- `app/fields.py` – Feldkarte aller Eingabezellen der Vorlage (ein Test prüft sie gegen die
  Vorlage)
- `app/pages.py` – Seiten trennen, ausrichten, Leerseiten, Zuordnung per Tesseract
- `app/recognize.py` – Handschrift per Ollama; `app/signatures.py` – Unterschriften zählen
- `app/checks.py`, `app/rules.py` – Plausibilitätsprüfung, abgeleitete Werte
- `app/workbook.py` – Vorlage befüllen
- `app/formulas.py` – eigener Formel-Rechner für die Summen (kein LibreOffice nötig)
- `app/verwendungsnachweis.py` – Kostenblatt, Einstellungen, Zusammenfassung
- `app/updates.py` – Hinweis auf neue Versionen
- `desktop/fetch_ollama.py` – lädt das festgelegte Ollama-Release (Prüfsumme) für den Build;
  Mac: nur arm64 und llama.cpp/Metal (~56 MB), Windows: CPU, Vulkan und Nvidia CUDA 12

Ollama: Läuft unter 127.0.0.1:11434 ein eigenes Ollama, nutzt der Launcher dieses, sonst startet er
das mitgelieferte unter 127.0.0.1:11435 (`OLLAMA_NO_CLOUD=1`) und beendet es mit der App.
`DOTATIONSLISTEN_OLLAMA=mitgeliefert` erzwingt das mitgelieferte, `OLLAMA_URL` setzt eines fest.

```sh
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt rumps   # Windows: pystray
DATA_DIR=$PWD/data .venv/bin/python desktop/launcher.py
```

Tests: `DATA_DIR=$PWD/data python -m pytest -q`. Viele Tests brauchen die Vorlage
(`data/vorlage/vorlage.xlsx`) und `data/verwendungsnachweis/original.xlsx` – beide nicht im
Repository, da mit echten Daten – und werden sonst übersprungen. Für die Erkennungs-Tests ein
Tesseract mit deutschen Sprachdaten (`TESSERACT`, `TESSDATA_PREFIX`, z. B. aus `macos/build`).

### Bauen und veröffentlichen

GitHub Actions (`.github/workflows/build.yml`): Tests bei jedem Push. Bei einem Versions-Tag
werden Mac-DMG und Windows-Setup gebaut, gestartet, mit einem Test-Scan geprüft
(`desktop/smoke_test.py`) und als Release veröffentlicht:

```sh
echo 1.2.0 > VERSION && git commit -am "Version 1.2.0" && git tag v1.2.0 && git push && git push --tags
```

Lokal:
- Mac: `macos/build_app.sh` (Xcode-Befehlszeilenwerkzeuge, `brew install cmake uv`).
  Tesseract wird selbst kompiliert (`macos/build_tesseract.sh`, statisch, macOS ≥ 13).
- Windows: `windows\build_windows.ps1` (Python 3.12, Tesseract der UB Mannheim, Inno Setup 6).

## Lizenz

Copyright (c) 2026 Robin Valley. Alle Rechte vorbehalten – siehe [LICENSE](LICENSE).
Komponenten Dritter: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Unterstützen

Wenn dir die Dotationslisten Zeit sparen, freue ich mich über einen Kaffee:
https://buymeacoffee.com/rvalley98
