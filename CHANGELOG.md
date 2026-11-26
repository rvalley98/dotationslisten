# Änderungen

Alle Versionen der Dotationslisten-App. Die Downloads stehen auf der jeweiligen Release-Seite.
Beim Aktualisieren bleiben die Daten erhalten.

## 1.2.3 – 26.11.2026

- **Seiten verschieben.** Eine Seite, die im falschen Vorgang gelandet ist, lässt sich in einen
  anderen oder einen neuen Vorgang verschieben. Das geht auf Wunsch mit allen folgenden Seiten,
  so lässt sich ein falsch getrennter Stapel ab dieser Seite abtrennen. Erkannte und geprüfte
  Werte wandern mit. Vorgänge aus demselben Scan stehen in der Auswahl oben. Ein Vorgang ohne
  Seiten wird entfernt.
- **Reiter „Hilfe“** mit einer Schritt-für-Schritt-Anleitung von der Einrichtung bis zum
  Verwendungsnachweis und häufigen Fragen.
- **Ganzer Stapel in einem PDF.** Die Hilfe und die Startseite erklären jetzt deutlicher, wie
  so ein Stapel aufgebaut sein muss. Jede Veranstaltung beginnt mit ihrem Abrechnungsbogen, ihre
  übrigen Blätter folgen direkt dahinter.
- Diese Änderungsliste (CHANGELOG.md).

## 1.2.2 – 26.11.2026

- Eigener Reiter **„Raum- & Verwaltungskosten“**. Er zeigt eine Übersicht: Räume für die
  Verwaltung, weitere Verwaltungskosten, Verwaltung insgesamt, Anteil an der Zuwendung und
  Schulungsräume. Darunter steht der Editor für die Raumkosten.
- **„🐞 Fehler melden“** steht unten auf jeder Seite und im Menü des Symbols. Version und
  Betriebssystem sind im Formular schon eingetragen.

## 1.2.1 – 26.11.2026

- **Raumkosten in der App bearbeiten.** Die App liest Gebäude und Räume aus dem Blatt
  „Raumkosten“ des Verwendungsnachweises und zeigt die KatS-Kosten je Raum. Sie lassen sich
  ändern. Die Änderungen gehen in die neu erzeugte Datei, die hochgeladene bleibt unverändert.
- Die App meldet fehlende Nutzungsarten und Gesamtflächen, Anteile über 100 % und Eingaben, die
  keine Zahl sind.

## 1.2.0 – 25.11.2026

- **Handschrifterkennung eingebaut.** Ollama muss nicht mehr separat installiert werden.
  - Mac: Apple-Chip, macOS 14 oder neuer.
  - Windows: Nvidia (CUDA 12), Vulkan oder nur Prozessor.
- **Import korrigiert.** Eine importierte Excel gilt als fertige Excel des Vorgangs. Die Werte
  werden genau so übernommen, wie sie in der Datei stehen. Dieselbe Datei wird nur einmal
  importiert.
- Ausführlichere Anleitungen. Docker entfällt, es gibt nur noch die Mac- und die Windows-App.

## 1.1.0 – 23.11.2026

- Hinweis in der App, wenn es eine neue Version gibt (Abfrage einmal am Tag).

## 1.0.0 – 23.11.2026

- Erste Version:
  - Scans einlesen und Seiten den Blättern zuordnen.
  - Handschrift erkennen.
  - Prüfen mit Scan und Eingabefeldern nebeneinander.
  - Excel nach der Vorlage erzeugen.
  - Excel-Abrechnungen importieren.
  - Verwendungsnachweis.
