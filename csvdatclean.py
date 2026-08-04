"""
Clean tabular CSV exports: trim empty edges, drop empty columns, flatten money cells.

Institutional downloads (e.g. Fidelity positions) often append blank rows and legal
boilerplate after the table, and emit gains as ``+$1,234.56`` / ``-$10.00``. This tool
keeps the contiguous table at the top, right- and bottom-truncates empty cells, removes
fully empty columns, and rewrites currency cells as plain numbers.

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


def clean_csv_rows(rows: list[list[str]]) -> list[list[str]]:
    """Extract table, trim empty edges/columns, flatten money cells."""
    table = extract_table_rows(rows)
    table = truncate_bottom_empty_rows(table)
    table = truncate_right_empty_columns(table)
    table = remove_empty_columns(table)
    return [[flatten_money(c) if isinstance(c, str) else c for c in row] for row in table]


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
) -> Path:
    if not input_path.is_file():
        raise FileNotFoundError(f"File not found: {input_path}")
    raw = read_csv(input_path, encoding=encoding)
    cleaned = clean_csv_rows(raw)
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
        description="Clean CSV table data: trim empty rows/columns and flatten +$/-$ money cells.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python csvdatclean.py -d positions.csv
  python csvdatclean.py -d positions.csv -o positions_clean.csv -v
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
        "--encoding",
        default="utf-8-sig",
        help="Input encoding (default: utf-8-sig); output is always utf-8-sig",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Print size change summary")
    args = parser.parse_args(argv)

    in_path = Path(args.data)
    out_path = Path(args.output) if args.output else None
    try:
        written = clean_file(in_path, out_path, encoding=args.encoding, verbose=args.verbose)
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
