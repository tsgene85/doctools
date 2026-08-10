"""
Clean tabular CSV exports: trim empty edges, drop empty columns, flatten money cells.

Institutional downloads (e.g. Fidelity positions) often append blank rows and legal
boilerplate after the table, and emit gains as ``+$1,234.56`` / ``-$10.00``. This tool
keeps the contiguous table at the top, right- and bottom-truncates empty cells, removes
fully empty columns, and rewrites currency cells as plain numbers.

With ``-cs`` / ``--currency-standardize``, currency-like columns are detected
(header names + cell patterns) and accounting negatives like ``(1,234.56)`` become
``-1234.56``.

Run: python csvdatclean.py -h
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# Optional sign, $, optional sign again, digits with optional commas/decimals.
_MONEY_RE = re.compile(
    r"""
    ^\s*
    (?P<sign1>[+-])?
    \s*\$\s*
    (?P<sign2>[+-])?
    \s*
    (?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)
    \s*$
    """,
    re.VERBOSE,
)

# Accounting negative: (1,234.56) or ($1,234.56)
_PAREN_NEG_RE = re.compile(
    r"""
    ^\s*
    \(\s*
    \$?\s*
    (?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)
    \s*\)\s*
    $
    """,
    re.VERBOSE,
)

# Signed / unsigned number, optional $, optional commas (for currency-column cells)
_CURRENCY_CELL_RE = re.compile(
    r"""
    ^\s*
    (?P<sign>[+-])?
    \s*
    \$?\s*
    (?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)
    \s*$
    """,
    re.VERBOSE,
)

# Header tokens that usually mean money (word-ish boundaries for short tokens)
_CURRENCY_HEADER_RE = re.compile(
    r"(?:"
    r"\bamount\b|\bamt\b|\bbalance\b|\bbal\b|\bdebit\b|\bcredit\b|"
    r"\bprice\b|\bcost\b|\bfee\b|\bfees\b|\bpayment\b|\bpayments\b|"
    r"\bcurrency\b|\bmoney\b|\btotal\b|\bcharge\b|\bcharges\b|"
    r"\bproceeds\b|\bgain\b|\bloss\b|\bvalue\b|\bpnl\b|p&l|"
    r"running\s*bal|summary\s*amt|\bampos\b|\bprincipal\b|"
    r"\binterest\b|\btax\b|\bwage\b|\bwages\b|net\s*pay|\bgross\b|"
    r"market\s*value|quantity\s*value"
    r")",
    re.IGNORECASE,
)

# Headers that are usually NOT currency even if cells are numeric
_NON_CURRENCY_HEADER_RE = re.compile(
    r"(?:"
    r"\bqty\b|\bquantity\b|\bshares\b|\bunits\b|\bcount\b|\bid\b|"
    r"\baccount\b|\bacct\b|\byear\b|\bzip\b|\bphone\b|\bssn\b|"
    r"\bpayee\b|\bcheck\s*#?\b|\bref\b|\breference\b"
    r")",
    re.IGNORECASE,
)


def _cell_has_content(val: object) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    return True


def _row_is_empty(row: list[str]) -> bool:
    return not any(_cell_has_content(c) for c in row)


def flatten_money(cell: str) -> str:
    """Turn ``+$1,234.56`` / ``-$10`` / ``$0.00`` into plain numeric strings."""
    if not isinstance(cell, str):
        return cell
    m = _MONEY_RE.match(cell)
    if not m:
        return cell
    signs = [s for s in (m.group("sign1"), m.group("sign2")) if s]
    # Odd number of minuses → negative; lone '+' is ignored.
    negative = signs.count("-") % 2 == 1
    num = m.group("num").replace(",", "")
    return f"-{num}" if negative else num


def standardize_currency_cell(cell: str) -> str:
    """
    Normalize a currency cell to a plain signed number.

    ``(1,234.56)`` / ``($1,234.56)`` → ``-1234.56``
    ``+$1,234.56`` / ``-$10`` / ``$0.00`` / ``1,234.56`` → unsigned/signed plain
    """
    if not isinstance(cell, str):
        return cell
    s = cell.strip()
    if not s:
        return cell

    m = _PAREN_NEG_RE.match(s)
    if m:
        return f"-{m.group('num').replace(',', '')}"

    flat = flatten_money(s)
    if flat != s:
        return flat

    m = _CURRENCY_CELL_RE.match(s)
    if not m:
        return cell
    num = m.group("num").replace(",", "")
    if m.group("sign") == "-":
        return f"-{num}"
    return num


def looks_like_currency_value(cell: str) -> bool:
    """True if cell looks like a money / accounting amount (not bare IDs)."""
    if not isinstance(cell, str):
        return False
    s = cell.strip()
    if not s:
        return False
    if _PAREN_NEG_RE.match(s) or _MONEY_RE.match(s):
        return True
    m = _CURRENCY_CELL_RE.match(s)
    if not m:
        return False
    num = m.group("num")
    # Bare integers without $, comma, decimal, or sign are weak (IDs / qty).
    if "$" in s or "," in num or "." in num or m.group("sign"):
        return True
    return False


def detect_currency_columns(
    header: list[str],
    data_rows: list[list[str]],
    *,
    min_fraction: float = 0.45,
) -> list[int]:
    """
    Detect currency columns using header keywords and cell patterns.

    A column is selected if:
    - the header looks monetary and >= ~30% of non-empty cells look like currency, or
    - >= ``min_fraction`` of non-empty cells look like currency (even without a keyword).
    Non-currency headers (qty, payee, id, …) are skipped.
    """
    if not header and not data_rows:
        return []
    width = max(len(header), max((len(r) for r in data_rows), default=0))
    chosen: list[int] = []
    for c in range(width):
        name = header[c].strip() if c < len(header) and isinstance(header[c], str) else ""
        if name and _NON_CURRENCY_HEADER_RE.search(name):
            continue
        header_hit = bool(name and _CURRENCY_HEADER_RE.search(name))

        non_empty = 0
        currency_like = 0
        for row in data_rows:
            if c >= len(row):
                continue
            cell = row[c]
            if not _cell_has_content(cell):
                continue
            non_empty += 1
            if looks_like_currency_value(cell if isinstance(cell, str) else str(cell)):
                currency_like += 1

        if non_empty == 0:
            continue
        frac = currency_like / non_empty
        if header_hit and frac >= 0.30:
            chosen.append(c)
        elif frac >= min_fraction:
            chosen.append(c)
    return chosen


def standardize_currency_columns(
    rows: list[list[str]],
    *,
    verbose: bool = False,
) -> list[list[str]]:
    """Detect currency columns and rewrite cells (incl. parenthetical negatives)."""
    if not rows:
        return rows
    header = rows[0]
    data = rows[1:] if len(rows) > 1 else []
    cols = detect_currency_columns(header, data)
    if not cols:
        if verbose:
            print("  -cs: no currency columns detected")
        return rows

    if verbose:
        names = []
        for c in cols:
            label = header[c].strip() if c < len(header) else f"col{c}"
            names.append(label or f"col{c}")
        print(f"  -cs: currency columns: {', '.join(names)}")

    out = [list(r) for r in rows]
    for r in out[1:]:
        for c in cols:
            if c < len(r) and isinstance(r[c], str) and r[c].strip():
                r[c] = standardize_currency_cell(r[c])
    return out


def extract_table_rows(rows: list[list[str]]) -> list[list[str]]:
    """Keep the leading contiguous non-empty block (header + data); drop footer after blank."""
    if not rows:
        return []
    start = 0
    while start < len(rows) and _row_is_empty(rows[start]):
        start += 1
    if start >= len(rows):
        return []
    end = start
    while end < len(rows) and not _row_is_empty(rows[end]):
        end += 1
    return [list(r) for r in rows[start:end]]


def truncate_right_empty_columns(rows: list[list[str]]) -> list[list[str]]:
    """Drop trailing columns that are empty in every row."""
    if not rows:
        return rows
    width = max((len(r) for r in rows), default=0)
    if width == 0:
        return [[] for _ in rows]
    last = width - 1
    while last >= 0:
        if any(_cell_has_content(r[last] if last < len(r) else "") for r in rows):
            break
        last -= 1
    keep = last + 1
    return [(r[:keep] + [""] * max(0, keep - len(r)))[:keep] for r in rows]


def remove_empty_columns(rows: list[list[str]]) -> list[list[str]]:
    """Remove columns that are empty in every row (including interior)."""
    if not rows:
        return rows
    width = max((len(r) for r in rows), default=0)
    if width == 0:
        return [[] for _ in rows]
    keep_idx = [
        c
        for c in range(width)
        if any(_cell_has_content(r[c] if c < len(r) else "") for r in rows)
    ]
    if not keep_idx:
        return [[] for _ in rows]
    out: list[list[str]] = []
    for r in rows:
        out.append([r[c] if c < len(r) else "" for c in keep_idx])
    return out


def truncate_bottom_empty_rows(rows: list[list[str]]) -> list[list[str]]:
    """Drop trailing fully empty rows."""
    end = len(rows)
    while end > 0 and _row_is_empty(rows[end - 1]):
        end -= 1
    return rows[:end]


def clean_csv_rows(
    rows: list[list[str]],
    *,
    currency_standardize: bool = False,
    verbose: bool = False,
) -> list[list[str]]:
    """Extract table, trim empty edges/columns, flatten money cells."""
    table = extract_table_rows(rows)
    table = truncate_bottom_empty_rows(table)
    table = truncate_right_empty_columns(table)
    table = remove_empty_columns(table)
    # Always flatten +$/-$/$ forms everywhere (existing behavior)
    table = [
        [flatten_money(c) if isinstance(c, str) else c for c in row] for row in table
    ]
    if currency_standardize:
        table = standardize_currency_columns(table, verbose=verbose)
    return table


def read_csv(path: Path, encoding: str = "utf-8-sig") -> list[list[str]]:
    with path.open(newline="", encoding=encoding) as f:
        return list(csv.reader(f))


def write_csv(path: Path, rows: list[list[str]], encoding: str = "utf-8-sig") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding=encoding) as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_clean{input_path.suffix or '.csv'}")


def clean_file(
    input_path: Path,
    output_path: Path | None = None,
    encoding: str = "utf-8-sig",
    verbose: bool = False,
    currency_standardize: bool = False,
) -> Path:
    if not input_path.is_file():
        raise FileNotFoundError(f"File not found: {input_path}")
    raw = read_csv(input_path, encoding=encoding)
    cleaned = clean_csv_rows(
        raw,
        currency_standardize=currency_standardize,
        verbose=verbose,
    )
    out = output_path if output_path is not None else default_output_path(input_path)
    write_csv(out, cleaned, encoding="utf-8-sig")
    if verbose:
        in_rows = len(raw)
        in_cols = max((len(r) for r in raw), default=0)
        out_rows = len(cleaned)
        out_cols = max((len(r) for r in cleaned), default=0)
        print(f"{input_path} -> {out}")
        print(f"  rows {in_rows} -> {out_rows}, cols {in_cols} -> {out_cols}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Clean CSV table data: trim empty rows/columns and flatten money cells. "
            "Use -cs to standardize detected currency columns (e.g. (123.45) -> -123.45)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python csvdatclean.py -d positions.csv
  python csvdatclean.py -d positions.csv -o positions_clean.csv -v
  python csvdatclean.py -d history.csv -cs -v
  python csvdatclean.py -d "C:/path/Portfolio_Positions.csv" -v
        """,
    )
    parser.add_argument(
        "-d",
        "--data",
        required=True,
        metavar="CSV",
        help="Input CSV file to clean",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output CSV path (default: <stem>_clean.csv next to input)",
    )
    parser.add_argument(
        "-cs",
        "--currency-standardize",
        action="store_true",
        help=(
            "Detect currency columns (header keywords + cell patterns) and "
            "normalize amounts: (1,234.56) -> -1234.56; strip $ and commas"
        ),
    )
    parser.add_argument(
        "--encoding",
        default="utf-8-sig",
        help="Input encoding (default: utf-8-sig); output is always utf-8-sig",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Print size change summary")
    args = parser.parse_args(argv)

    in_path = Path(args.data)
    out_path = Path(args.output) if args.output else None
    try:
        written = clean_file(
            in_path,
            out_path,
            encoding=args.encoding,
            verbose=args.verbose,
            currency_standardize=args.currency_standardize,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except UnicodeDecodeError as e:
        print(f"Error decoding CSV (try --encoding): {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not args.verbose:
        print(f"Wrote {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
