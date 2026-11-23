"""Small Excel formula evaluator for the two templates (Abrechnung, Verwendungsnachweis).

The sums are computed here so neither LibreOffice nor Excel has to be installed. Only the
functions the templates use are implemented; anything else raises Unsupported and the caller
falls back to LibreOffice (if installed). Cells are evaluated lazily: only what the requested
cells depend on. tests/test_formulas.py compares the results with LibreOffice.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path
from typing import Any, Callable

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter


class Unsupported(Exception):
    """Formula construct not implemented - use LibreOffice instead."""


class XLError(str):
    """#N/A, #VALUE!, #DIV/0! ... - propagates like in Excel."""


NA, VALUE, DIV0, REF, NAME = (XLError(e) for e in ("#N/A", "#VALUE!", "#DIV/0!", "#REF!", "#NAME?"))
EPOCH = dt.datetime(1899, 12, 30)


def serial(d: dt.date | dt.datetime) -> float:
    if not isinstance(d, dt.datetime):
        d = dt.datetime(d.year, d.month, d.day)
    return (d - EPOCH).total_seconds() / 86400


def from_serial(n: float) -> dt.datetime:
    return EPOCH + dt.timedelta(days=n)


# --- tokenizer -------------------------------------------------------------------------------

_CELL = r"\$?[A-Z]{1,3}\$?\d+"
_TOKEN = re.compile(rf"""
    (?P<ws>\s+)
  | (?P<str>"(?:[^"]|"")*")
  | (?P<ref>(?:(?P<sheet>'(?:[^']|'')+'|[^\W\d][\w.]*)!)?(?P<a>{_CELL})(?::(?P<b>{_CELL}))?)(?![\w(])
  | (?P<num>\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+)
  | (?P<func>[A-Z][A-Z0-9.]*)\(
  | (?P<name>[^\W\d][\w.]*)
  | (?P<op><>|<=|>=|[-+*/^&=<>%(),;])
""", re.X)


def _tokens(src: str) -> list[tuple[str, Any]]:
    out, pos = [], 0
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m:
            raise Unsupported(f"Zeichen {src[pos:pos + 10]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        if m.group("ref"):
            sheet = m.group("sheet")
            if sheet and sheet.startswith("'"):
                sheet = sheet[1:-1].replace("''", "'")
            out.append(("ref", (sheet, m.group("a"), m.group("b"))))
        elif m.group("str") is not None:
            out.append(("str", m.group("str")[1:-1].replace('""', '"')))
        elif m.group("num") is not None:
            out.append(("num", float(m.group("num"))))
        elif m.group("func"):
            out.append(("func", m.group("func")))
        elif m.group("name"):
            n = m.group("name")
            out.append(("bool", n.upper() == "TRUE") if n.upper() in ("TRUE", "FALSE") else ("name", n))
        else:
            out.append(("op", m.group("op")))
    out.append(("end", None))
    return out


# --- parser: formula -> nested tuples ----------------------------------------------------------

class _Parser:
    def __init__(self, src: str):
        self.t = _tokens(src)
        self.i = 0

    def peek(self):
        return self.t[self.i]

    def take(self, kind=None, value=None):
        tok = self.t[self.i]
        if (kind and tok[0] != kind) or (value is not None and tok[1] != value):
            raise Unsupported(f"unerwartet {tok}")
        self.i += 1
        return tok

    def parse(self):
        node = self.compare()
        self.take("end")
        return node

    def binary(self, ops, sub):
        node = sub()
        while self.peek()[0] == "op" and self.peek()[1] in ops:
            op = self.take()[1]
            node = ("bin", op, node, sub())
        return node

    def compare(self):
        return self.binary(("=", "<>", "<", ">", "<=", ">="), self.concat)

    def concat(self):
        return self.binary(("&",), self.additive)

    def additive(self):
        return self.binary(("+", "-"), self.term)

    def term(self):
        return self.binary(("*", "/"), self.power)

    def power(self):
        return self.binary(("^",), self.unary)

    def unary(self):
        if self.peek() == ("op", "-"):
            self.take()
            return ("neg", self.unary())
        if self.peek() == ("op", "+"):
            self.take()
            return self.unary()
        node = self.primary()
        while self.peek() == ("op", "%"):
            self.take()
            node = ("bin", "/", node, ("lit", 100.0))
        return node

    def primary(self):
        kind, value = self.take()
        if kind in ("num", "str", "bool"):
            return ("lit", value)
        if kind == "ref":
            return ("ref", value)
        if kind == "name":
            return ("name", value)
        if kind == "func":
            args = []
            if self.peek() != ("op", ")"):
                while True:
                    if self.peek()[0] == "op" and self.peek()[1] in (",", ";", ")"):
                        args.append(("lit", None))  # empty argument
                    else:
                        args.append(self.compare())
                    if self.peek()[0] == "op" and self.peek()[1] in (",", ";"):
                        self.take()
                        continue
                    break
            self.take("op", ")")
            return ("func", value, args)
        if (kind, value) == ("op", "("):
            node = self.compare()
            self.take("op", ")")
            return node
        raise Unsupported(f"unerwartet {kind} {value!r}")


# --- values ------------------------------------------------------------------------------------

class Range:
    def __init__(self, book: "Book", sheet: str, r1: int, c1: int, r2: int, c2: int):
        self.book, self.sheet = book, sheet
        max_row = book.wb[sheet].max_row
        self.r1, self.c1, self.c2 = r1, c1, c2
        self.r2 = min(r2, max(max_row, r1))  # whole-column style ranges: stop at the last used row

    @property
    def rows(self) -> int:
        return self.r2 - self.r1 + 1

    @property
    def cols(self) -> int:
        return self.c2 - self.c1 + 1

    def cell(self, i: int, j: int = 0) -> Any:
        return self.book.value(self.sheet, self.r1 + i, self.c1 + j)

    def values(self):
        for i in range(self.rows):
            for j in range(self.cols):
                yield self.cell(i, j)

    def vector(self) -> list[Any]:
        """LOOKUP vector: a single row/column, or the first column of a taller block."""
        if self.cols == 1 or self.rows >= self.cols:
            return [self.cell(i, 0) for i in range(self.rows)]
        return [self.cell(0, j) for j in range(self.cols)]


def _num(v: Any) -> float | XLError:
    if isinstance(v, XLError):
        return v
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return serial(v)
    if isinstance(v, str):
        try:
            return float(v.strip().replace(",", ".")) if v.strip() else VALUE
        except ValueError:
            return VALUE
    return VALUE


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return _text(serial(v))
    return str(v)


def _bool(v: Any) -> bool | XLError:
    if isinstance(v, XLError):
        return v
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        if v.upper() in ("TRUE", "FALSE"):
            return v.upper() == "TRUE"
        return VALUE
    return VALUE


def _rank(v: Any) -> int:  # Excel ordering: numbers < text < booleans
    return 2 if isinstance(v, bool) else 1 if isinstance(v, str) else 0


def _compare(a: Any, b: Any) -> int:
    if a is None:
        a = "" if isinstance(b, str) else False if isinstance(b, bool) else 0.0
    if b is None:
        b = "" if isinstance(a, str) else False if isinstance(a, bool) else 0.0
    if isinstance(a, (dt.date, dt.datetime)):
        a = serial(a)
    if isinstance(b, (dt.date, dt.datetime)):
        b = serial(b)
    ra, rb = _rank(a), _rank(b)
    if ra != rb:
        return -1 if ra < rb else 1
    if ra == 1:
        a, b = a.casefold(), b.casefold()
    return (a > b) - (a < b)


# --- functions ---------------------------------------------------------------------------------

def _first_error(*vals):
    return next((v for v in vals if isinstance(v, XLError)), None)


def _scalar_args(fn: Callable) -> Callable:
    def wrapper(ev, args):
        vals = [ev.scalar(a) for a in args]
        return _first_error(*vals) or fn(*vals)
    return wrapper


def _f_if(ev, args):
    if len(args) not in (2, 3):
        raise Unsupported("IF")
    c = _bool(ev.scalar(args[0]))
    if isinstance(c, XLError):
        return c
    if c:
        return ev.scalar(args[1])
    return ev.scalar(args[2]) if len(args) == 3 else False


def _logic(args, ev, combine):
    vals = []
    for a in args:
        x = ev.eval(a)
        items = list(x.values()) if isinstance(x, Range) else [x]
        for v in items:
            if isinstance(x, Range) and (v is None or isinstance(v, str)):
                continue
            b = _bool(v)
            if isinstance(b, XLError):
                return b
            vals.append(b)
    return combine(vals) if vals else VALUE


def _f_sum(ev, args):
    total = 0.0
    for a in args:
        x = ev.eval(a)
        if isinstance(x, Range):
            for v in x.values():
                if isinstance(v, XLError):
                    return v
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    total += v
                elif isinstance(v, (dt.date, dt.datetime)):
                    total += serial(v)
        else:
            n = _num(x)
            if isinstance(n, XLError):
                return n
            total += n
    return total


def _criteria(c: Any) -> Callable[[Any], bool]:
    if isinstance(c, str):
        m = re.fullmatch(r"(<>|<=|>=|=|<|>)?(.*)", c, re.S)
        op, rhs = m[1] or "=", m[2]
        n = _num(rhs) if rhs.strip() else None
        target: Any = rhs if (n is None or isinstance(n, XLError)) else n
        if "*" in rhs or "?" in rhs:
            raise Unsupported("SUMIF mit Platzhaltern")
    else:
        op, target = "=", c
    numeric = isinstance(target, (int, float)) and not isinstance(target, bool)

    def test(v):
        if numeric and not (isinstance(v, (int, float)) and not isinstance(v, bool)):
            return op == "<>"
        if not numeric and op in ("=", "<>") and target == "":
            empty = v is None or v == ""
            return empty if op == "=" else not empty
        if not numeric and not isinstance(v, str) and op in ("=", "<>"):
            return op == "<>"
        r = _compare(v, target)
        return {"=": r == 0, "<>": r != 0, "<": r < 0, ">": r > 0, "<=": r <= 0, ">=": r >= 0}[op]
    return test


def _f_sumif(ev, args):
    rng = ev.eval(args[0])
    crit = ev.scalar(args[1])
    sum_rng = ev.eval(args[2]) if len(args) > 2 else rng
    if not isinstance(rng, Range) or not isinstance(sum_rng, Range):
        raise Unsupported("SUMIF ohne Bereich")
    if isinstance(crit, XLError):
        return crit
    test = _criteria(crit)
    total = 0.0
    for i in range(rng.rows):
        for j in range(rng.cols):
            if test(rng.cell(i, j)):
                v = sum_rng.book.value(sum_rng.sheet, sum_rng.r1 + i, sum_rng.c1 + j)
                if isinstance(v, XLError):
                    return v
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    total += v
    return total


def _f_counta(ev, args):
    n = 0
    for a in args:
        x = ev.eval(a)
        n += sum(v is not None for v in x.values()) if isinstance(x, Range) else (x is not None)
    return float(n)


def _f_lookup(ev, args):
    if len(args) not in (2, 3):
        raise Unsupported("LOOKUP")
    key = ev.scalar(args[0])
    if isinstance(key, XLError):
        return key
    lookup = ev.eval(args[1])
    result = ev.eval(args[2]) if len(args) == 3 else None
    if not isinstance(lookup, Range) or (result is not None and not isinstance(result, Range)):
        raise Unsupported("LOOKUP ohne Bereich")
    if result is None and lookup.cols > 1 and lookup.rows > 1:
        raise Unsupported("LOOKUP-Matrixform")
    vec = lookup.vector()
    # sorted vector: last entry of the key's type that is <= key (what Excel's binary search finds)
    found = None
    for i, v in enumerate(vec):
        if v is None or isinstance(v, XLError) or _rank(v) != _rank(key if key is not None else 0.0):
            continue
        if _compare(v, key) <= 0:
            found = i
        else:
            break
    if found is None:
        return NA
    if result is None:
        return vec[found]
    out = result.vector()
    return out[found] if found < len(out) else NA


def _f_mod(a, b):
    a, b = _num(a), _num(b)
    if e := _first_error(a, b):
        return e
    if b == 0:
        return DIV0
    return a - b * math.floor(a / b)


def _f_mid(s, start, n):
    start, n = _num(start), _num(n)
    if e := _first_error(start, n):
        return e
    if start < 1 or n < 0:
        return VALUE
    s = _text(s)
    return s[int(start) - 1:int(start) - 1 + int(n)]


def _f_right(s, n=1.0):
    n = _num(n)
    if isinstance(n, XLError):
        return n
    s = _text(s)
    return s[len(s) - int(n):] if n > 0 else ""


def _f_left(s, n=1.0):
    n = _num(n)
    if isinstance(n, XLError):
        return n
    return _text(s)[:int(n)]


def _f_text(v, fmt):
    n = _num(v)
    fmt = _text(fmt)
    if isinstance(n, XLError):
        return _text(v)
    if re.fullmatch(r"0+", fmt):
        return f"{int(round(n)):0{len(fmt)}d}"
    m = re.fullmatch(r"0([.,])(0+)(.*)", fmt)
    if m:  # 0,00 € / 0.00
        digits = len(m[2])
        s = f"{n:.{digits}f}"
        return (s.replace(".", ",") if m[1] == "," else s) + m[3]
    raise Unsupported(f"TEXT-Format {fmt!r}")


def _f_date(y, m, d):
    y, m, d = (_num(x) for x in (y, m, d))
    if e := _first_error(y, m, d):
        return e
    y, m, d = int(y), int(m), int(d)
    if y < 1900:
        y += 1900
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return serial(dt.datetime(y, m, 1)) + d - 1


def _f_round(v, digits=0.0):
    v, digits = _num(v), _num(digits)
    if e := _first_error(v, digits):
        return e
    q = 10 ** int(digits)
    return math.floor(abs(v) * q + 0.5) / q * (1 if v >= 0 else -1)


FUNCTIONS: dict[str, Callable] = {
    "IF": _f_if,
    "AND": lambda ev, a: _logic(a, ev, all),
    "OR": lambda ev, a: _logic(a, ev, any),
    "NOT": _scalar_args(lambda v: (lambda b: b if isinstance(b, XLError) else not b)(_bool(v))),
    "SUM": _f_sum,
    "SUMIF": _f_sumif,
    "COUNTA": _f_counta,
    "LOOKUP": _f_lookup,
    "MOD": _scalar_args(_f_mod),
    "LEN": _scalar_args(lambda s: float(len(_text(s)))),
    "MID": _scalar_args(_f_mid),
    "LEFT": _scalar_args(_f_left),
    "RIGHT": _scalar_args(_f_right),
    "TEXT": _scalar_args(_f_text),
    "CONCATENATE": _scalar_args(lambda *v: "".join(_text(x) for x in v)),
    "DATE": _scalar_args(_f_date),
    "ROUND": _scalar_args(_f_round),
}


# --- evaluation --------------------------------------------------------------------------------

def _rc(ref: str) -> tuple[int, int]:
    m = re.fullmatch(r"\$?([A-Z]{1,3})\$?(\d+)", ref)
    return int(m[2]), column_index_from_string(m[1])


class Book:
    def __init__(self, path: Path):
        self.wb = openpyxl.load_workbook(path)
        self.cache: dict[tuple[str, int, int], Any] = {}
        self.parsed: dict[str, Any] = {}
        self.stack: set[tuple[str, int, int]] = set()
        self.sheets = {name.casefold(): name for name in self.wb.sheetnames}

    def sheet_name(self, name: str) -> str:
        try:
            return self.sheets[name.casefold()]
        except KeyError:
            raise Unsupported(f"Blatt {name!r} fehlt")

    def value(self, sheet: str, row: int, col: int) -> Any:
        key = (sheet, row, col)
        if key in self.cache:
            return self.cache[key]
        raw = self.wb[sheet].cell(row, col).value
        if isinstance(raw, str) and raw.startswith("=") and len(raw) > 1:
            if key in self.stack:
                raise Unsupported(f"Zirkelbezug {sheet}!{get_column_letter(col)}{row}")
            self.stack.add(key)
            try:
                tree = self.parsed.get(raw)
                if tree is None:
                    tree = self.parsed[raw] = _Parser(raw[1:]).parse()
                v = _Eval(self, sheet).scalar(tree)
            finally:
                self.stack.discard(key)
        elif isinstance(raw, dt.timedelta):  # times of day / durations: fraction of a day
            v = raw.total_seconds() / 86400
        elif isinstance(raw, dt.time):
            v = (raw.hour * 3600 + raw.minute * 60 + raw.second) / 86400
        elif raw is not None and not isinstance(raw, (str, int, float, bool, dt.date, dt.datetime)):
            raise Unsupported(f"Zelltyp {type(raw).__name__}")
        else:
            v = float(raw) if isinstance(raw, int) and not isinstance(raw, bool) else raw
        self.cache[key] = v
        return v

    def get(self, ref: str, default_sheet: str | None = None) -> Any:
        """'Sheet!A1' -> value (dates stay as numbers if they come from a formula)."""
        sheet, _, cell = ref.rpartition("!")
        if sheet.startswith("'") and sheet.endswith("'"):
            sheet = sheet[1:-1].replace("''", "'")
        row, col = _rc(cell)
        return self.value(self.sheet_name(sheet or default_sheet), row, col)


class _Eval:
    def __init__(self, book: Book, sheet: str):
        self.book, self.sheet = book, sheet

    def eval(self, node):
        kind = node[0]
        if kind == "lit":
            v = node[1]
            return v
        if kind == "ref":
            sheet, a, b = node[1]
            sheet = self.book.sheet_name(sheet) if sheet else self.sheet
            r1, c1 = _rc(a)
            if b is None:
                return self.book.value(sheet, r1, c1)
            r2, c2 = _rc(b)
            return Range(self.book, sheet, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2))
        if kind == "name":
            dn = self.book.wb.defined_names.get(node[1])
            if dn is None:
                return NAME
            dest = list(dn.destinations)
            if len(dest) != 1:
                raise Unsupported(f"Name {node[1]}")
            sheet, ref = dest[0]
            a, _, b = ref.partition(":")
            return self.eval(("ref", (sheet, a, b or None)))
        if kind == "neg":
            v = _num(self.scalar(node[1]))
            return v if isinstance(v, XLError) else -v
        if kind == "bin":
            return self.binary(node[1], self.scalar(node[2]), self.scalar(node[3]))
        if kind == "func":
            fn = FUNCTIONS.get(node[1])
            if fn is None:
                raise Unsupported(f"Funktion {node[1]}")
            return fn(self, node[2])
        raise Unsupported(kind)

    def scalar(self, node):
        v = self.eval(node)
        if isinstance(v, Range):
            if v.rows == 1 and v.cols == 1:
                return v.cell(0, 0)
            raise Unsupported("Bereich als Einzelwert")
        return v

    @staticmethod
    def binary(op, a, b):
        if op == "&":
            return _first_error(a, b) or _text(a) + _text(b)
        if op in ("=", "<>", "<", ">", "<=", ">="):
            if e := _first_error(a, b):
                return e
            r = _compare(a, b)
            return {"=": r == 0, "<>": r != 0, "<": r < 0, ">": r > 0, "<=": r <= 0, ">=": r >= 0}[op]
        x, y = _num(a), _num(b)
        if e := _first_error(x, y):
            return e
        if op == "+":
            return x + y
        if op == "-":
            return x - y
        if op == "*":
            return x * y
        if op == "/":
            return DIV0 if y == 0 else x / y
        if op == "^":
            try:
                return float(x ** y)
            except (OverflowError, ZeroDivisionError, TypeError):
                return VALUE
        raise Unsupported(op)


def evaluate(path: Path, refs: list[str]) -> dict[str, Any]:
    """{'Sheet!A1': value} for the requested cells. Raises Unsupported for unknown constructs."""
    book = Book(path)
    return {ref: book.get(ref) for ref in refs}
