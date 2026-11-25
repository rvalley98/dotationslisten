"""Declarative map of every input cell of the template.

One source of truth for: blanking the template, the extraction prompts, the review UI and
filling the workbook. Cells not listed here are formulas or labels and are never written.
The map is checked against the template's unlocked cells (see tests/test_fields.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Value types and how they are written into Excel
TEXT = "text"          # plain string
INT = "int"            # whole number (e.g. Gliederungsnummer, km)
MONEY = "money"        # decimal euro amount
DATE = "date"          # dd.mm.yyyy -> real Excel date
TIME = "time"          # hh:mm -> real Excel time (fraction of a day)
PERCENT = "percent"    # 0-100 on paper -> 0.0-1.0 in Excel
JA_NEIN_UPPER = "JA/NEIN"
JA_NEIN_LOWER = "ja/nein"
IBAN = "iban"          # 22 chars, no spaces, upper case
ENUM = "enum"


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    cell: str
    type: str = TEXT
    options: tuple[str, ...] = ()
    default: str | None = None  # used when the paper leaves the field empty
    formula: str | None = None  # written instead when the paper leaves the field empty
    read: bool = True  # asked from the recognition model (False: the formula is the usual value)


@dataclass(frozen=True)
class Table:
    """Repeated rows, e.g. participants. Columns map key -> (column letter, type)."""

    key: str
    label: str
    first_row: int
    rows: int
    columns: tuple[tuple[str, str, str, str], ...]  # (key, label, column, type)
    row_step: int = 1


@dataclass(frozen=True)
class Sheet:
    key: str
    name: str            # worksheet name in the template
    title: str           # printed title, used to classify scanned pages
    fields: tuple[Field, ...] = ()
    tables: tuple[Table, ...] = ()
    shares_header: bool = True  # header (rows 3-9) is copied from Abrechnungsbogen by formulas
    # shown and editable in the review form, but computed by the app (not asked from the model)
    # and never written into the workbook
    extras: tuple[Field, ...] = ()


HEADER = (
    Field("thema", "Bezeichnung / Thema", "B3"),
    Field("art", "Veranstaltungsart", "B4", ENUM, ("Ausbildung", "Übung")),
    Field("ort", "Veranstaltungsort", "B5"),
    Field("gliederungsnummer", "Gliederungsnummer", "B6", INT),
    Field("beginn_datum", "Veranstaltungsbeginn (Datum)", "B8", DATE),
    Field("beginn_uhrzeit", "Veranstaltungsbeginn (Uhrzeit)", "D8", TIME),
    Field("ende_datum", "Veranstaltungsende (Datum)", "B9", DATE),
    Field("ende_uhrzeit", "Veranstaltungsende (Uhrzeit)", "D9", TIME),
)

ABRECHNUNG = Sheet(
    key="abrechnung",
    name="Abrechnungsbogen",
    title="Veranstaltungsabrechnung",
    shares_header=False,
    fields=HEADER + (
        Field("teilnehmergebuehren", "Gezahlte Teilnehmergebühren", "G12", MONEY),
        Field("materialausgaben", "Materialausgaben", "G13", MONEY),
        Field("mieten", "Mieten / Unterbringungskosten", "G14", MONEY),
        Field("reisekosten", "Erstattete Reisekosten", "G15", MONEY),
        # the template links G17 (Tagegelder) to the Tagegeld sheet but not G16 - done here
        Field("aufwandverguetungen", "Gezahlte Aufwandvergütungen", "G16", MONEY,
              formula="=Tagegeld_Aufwandsvergütung!H27"),
        # linked to the Tagegeld sheet; can be overwritten in Excel (imported Abrechnungen)
        Field("tagegelder", "Gezahlte Tagegelder", "G17", MONEY,
              formula="=Tagegeld_Aufwandsvergütung!H19", read=False),
        Field("anteil_kats", "Anteil KatS (%)", "G27", PERCENT, default="100"),
    ),
    tables=(
        Table(
            key="fahrzeuge",
            label="Fahrtkosten DLRG-eigene Fahrzeuge",
            first_row=20,
            rows=5,
            columns=(
                ("kennzeichen", "Kennzeichen", "B", TEXT),
                ("km", "gefahrene Kilometer", "C", INT),
                ("mitfahrer", "Mitfahrer im Kfz", "D", INT),
                ("anhaenger", "mit Anhänger", "E", JA_NEIN_LOWER),
            ),
        ),
    ),
)

TEILNEHMER = Sheet(
    key="teilnehmer",
    name="Teilnehmerliste",
    title="Teilnehmerliste",
    tables=(
        Table(
            key="teilnehmer",
            label="Teilnehmer",
            first_row=12,
            rows=20,
            columns=(
                ("name", "Name", "B", TEXT),
                ("vorname", "Vorname", "C", TEXT),
                ("wohnort", "Wohnort", "E", TEXT),
            ),
        ),
    ),
)

TAGEGELD = Sheet(
    key="tagegeld",
    name="Tagegeld_Aufwandsvergütung",
    title="Tagegeld / Aufwandsvergütung",
    fields=(
        Field("ausserhalb_gemeinde", "Veranstaltung außerhalb der Gemeinde", "E11", JA_NEIN_UPPER),
        Field("teilnehmer_tagegeld", "Teilnehmeranzahl Tagegeld", "F15", INT),
        Field("teilnehmer_aufwand", "Teilnehmeranzahl Aufwandsvergütung", "F23", INT),
    ),
    extras=(
        Field("unterschriften", "Unterschriften (gezählt)", "", INT),
    ),
)


def _fahrtkosten(n: int) -> Sheet:
    return Sheet(
        key=f"fahrtkosten_{n}",
        name=f"Fahrtkosten ({n})",
        title="Abrechnung Fahrtkosten KatS",
        fields=(
            Field("fahrer", "Fahrer", "B12"),
            Field("kennzeichen", "Kfz-Kennzeichen", "B13"),
            Field("iban", "IBAN", "B14", IBAN),
            Field("km", "gefahrene Kilometer", "C30", INT),
            Field("anhaenger", "mit Anhänger", "C32", JA_NEIN_LOWER),
        ),
        tables=(
            Table(
                key="mitfahrer",
                label="Mitfahrer",
                first_row=20,
                rows=8,
                columns=(("name", "Name", "B", TEXT),),
            ),
        ),
    )


FAHRTKOSTEN = tuple(_fahrtkosten(n) for n in range(1, 6))


def _trupp(n: int, first_row: int) -> tuple[tuple[Field, ...], Table]:
    prefix = f"trupp{n}"
    fields = (
        Field(f"{prefix}_signalmann", f"{n}. Tauchtrupp: Signalmann", f"B{first_row}"),
        Field(f"{prefix}_bemerkungen", f"{n}. Tauchtrupp: Aufgaben / Bemerkungen", f"A{first_row + 6}"),
    )
    table = Table(
        key=f"{prefix}_taucher",
        label=f"{n}. Tauchtrupp (Sicherheitstaucher, 1.-3. Taucher)",
        first_row=first_row + 1,
        rows=4,
        columns=(
            ("name", "Name", "B", TEXT),
            ("ein1", "Ein", "D", TIME),
            ("aus1", "Aus", "E", TIME),
            ("ein2", "Ein (2. Tauchgang)", "F", TIME),
            ("aus2", "Aus (2. Tauchgang)", "H", TIME),
        ),
    )
    return fields, table


_t1, _t2, _t3 = _trupp(1, 12), _trupp(2, 21), _trupp(3, 30)
TAUCHPROTOKOLL = Sheet(
    key="tauchprotokoll",
    name="Tauchprotokoll",
    title="Tauchprotokoll",
    fields=_t1[0] + _t2[0] + _t3[0],
    tables=(_t1[1], _t2[1], _t3[1]),
)

SHEETS: tuple[Sheet, ...] = (ABRECHNUNG, TEILNEHMER, TAGEGELD, *FAHRTKOSTEN, TAUCHPROTOKOLL)
SHEETS_BY_KEY = {s.key: s for s in SHEETS}


def table_cells(table: Table) -> list[tuple[int, str, str, str]]:
    """(row index, column key, cell, type) for every cell of a table."""
    cells = []
    for i in range(table.rows):
        row = table.first_row + i * table.row_step
        for key, _label, col, typ in table.columns:
            cells.append((i, key, f"{col}{row}", typ))
    return cells


def all_input_cells(sheet: Sheet) -> list[str]:
    cells = [f.cell for f in sheet.fields]
    for table in sheet.tables:
        cells += [c for _i, _k, c, _t in table_cells(table)]
    return cells
