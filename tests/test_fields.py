"""The field map must match exactly the unlocked (= input) cells of the template."""

import openpyxl

from app import fields as F

# unlocked in the template but a formula or an image area -> never written
NOT_INPUT = {("Abrechnungsbogen", "G17"), ("Belege", "A12")}


def unlocked_anchor_cells(ws):
    anchors = {}
    for m in ws.merged_cells.ranges:
        for r in range(m.min_row, m.max_row + 1):
            for c in range(m.min_col, m.max_col + 1):
                anchors[(r, c)] = (m.min_row, m.min_col)
    result = set()
    for row in ws.iter_rows():
        for c in row:
            if c.protection.locked is False and anchors.get((c.row, c.column), (c.row, c.column)) == (c.row, c.column):
                result.add(c.coordinate)
    return result


def test_field_map_matches_unlocked_cells(template_xlsx):
    wb = openpyxl.load_workbook(template_xlsx)
    for sheet in F.SHEETS:
        expected = unlocked_anchor_cells(wb[sheet.name]) - {c for s, c in NOT_INPUT if s == sheet.name}
        assert set(F.all_input_cells(sheet)) == expected, sheet.name


def test_no_input_cell_holds_a_formula(template_xlsx):
    wb = openpyxl.load_workbook(template_xlsx)
    for sheet in F.SHEETS:
        for cell in F.all_input_cells(sheet):
            v = wb[sheet.name][cell].value
            assert not (isinstance(v, str) and v.startswith("=")), f"{sheet.name}!{cell}"
