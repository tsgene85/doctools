# xlstool.py

Command-line utilities for Excel workbooks (`.xls`, `.xlsx`, `.xlsm`) and CSV files: sheet summaries, export to CSV, duplicate-row detection, and merging CSVs in a directory.

## Requirements

- Python 3 (uses `from __future__ import annotations` and modern typing).
- **xlrd** — legacy `.xls` read and export.
- **openpyxl** — `.xlsx` / `.xlsm` read and export.

Install dependencies as needed, for example:

```text
pip install xlrd openpyxl
```

## Invocation

```text
python xlstool.py -h
```

Exactly **one** of `--sum`, `--xc`, `--dup`, or `--merge-csv` must be chosen.

Input file:

- Positional `FILE`, or
- `-i` / `--input FILE`

## How counts and “used” cells work

Row and column counts are the size of the **tight bounding box** of cells that count as having content:

- `None` and empty strings do not count.
- Strings that are only whitespace do not count.
- `NaN` floats do not count.
- Numeric zero **does** count.

For `--sum` on workbooks, plain mode prints per-sheet row/column counts only. With `--sheets` / `-sh`, the tool also prints **column names** taken from the **top row of that same non-empty rectangle**. Empty header cells are shown as `(A)`, `(B)`, … using Excel column letters.

For `--sum` on a `.csv`, column names are **always** included (same header rule). `-sh` only controls whether that single “sheet” (the file stem) is listed.

## Sheet selection (`--sheets` / `-sh`)

Comma-separated tokens, applied to workbook sheet names in document order:

- **Sheet name** — exact match.
- **1-based index** — e.g. `1`, `3` (same order as the `#` column in `--sum` output).
- **Forced index** — `#2` or `@2` when the sheet might be named like a number.

Unknown tokens produce a warning; if nothing matches, the command fails.

## Modes

### `--sum` — Summarize workbook or CSV

Supported inputs: `.csv`, `.xls`, `.xlsx`, `.xlsm`.

- Without `-sh`: table of sheet index, name, rows, cols.
- With `-sh`: filtered sheets plus column names per sheet (workbooks) or filtered CSV “sheet”.

Optional `-o` / `--output FILE` writes the report as UTF-8 text.

### `--xc` — Export sheets to CSV

Supported inputs: `.xls`, `.xlsx`, `.xlsm` (not plain CSV).

Writes one UTF-8-with-BOM CSV per exported sheet:

- Default name: `{workbook_stem}_{sanitizedSheetName}.csv` next to the workbook.
- `--csv-dir DIR` puts files under `DIR`.
- Optional `--sheets` / `-sh` limits which sheets are exported.

Sheet names are sanitized for Windows paths (invalid characters replaced; trailing dots/spaces stripped). Colliding names get `_2`, `_3`, … suffixes.

`-o` / `--output` is **not** used with `--xc`.

### `--dup` — Find duplicate keys in a CSV

Requires `--keys SPEC`:

- **Numeric mode** — if `SPEC` is only integers and hyphen ranges (e.g. `1,3,5-7`): 1-based column indexes; **every row is data** (row 1 is not a header).
- **Header mode** — otherwise: first row is the header; `SPEC` is comma-separated column names (exact match, then case-folded; ambiguous names are an error).

Reads the CSV with `--encoding` (default `utf-8-sig`). Prints a report listing duplicate key values and participating 1-based row numbers. Optional `-o` writes the report as UTF-8.

### `--merge-csv DIR` — Concatenate CSVs in a directory

- Collects files under `DIR` matching `--merge-pattern` (default `*.csv`), sorted by name.
- First file’s first row is the **header** for the merged file; each later file’s first row is skipped if it matches that header (otherwise a warning and the header line is still skipped).
- Default output: `<parent of DIR>/<DIRname>_merged.csv`. Override with `-o`.
- Output is always UTF-8 with BOM. Reading uses `--encoding` (default `utf-8-sig`).

Do not pass `-i`, positional `FILE`, `--sheets`, `--keys`, or `--csv-dir` with `--merge-csv`.

## Options reference

| Option | Used with | Meaning |
|--------|-----------|---------|
| `--sum` | — | Summarize sheets or CSV |
| `--xc` | — | Export workbook sheets to CSV |
| `--dup` | — | Duplicate-key report for CSV |
| `--merge-csv DIR` | — | Merge CSVs under `DIR` |
| `--keys SPEC` | `--dup` | Key columns (indexes/ranges or header names) |
| `-i` / `--input FILE` | `--sum`, `--xc`, `--dup` | Input path |
| `FILE` (positional) | same | Same as `-i` if one path |
| `-o` / `--output FILE` | `--sum`, `--dup`, `--merge-csv` | Write report or merged CSV path |
| `--sheets` / `-sh NAMES` | `--sum`, `--xc` | Sheet filter / index tokens |
| `--csv-dir DIR` | `--xc` | Output directory for CSVs |
| `--merge-pattern GLOB` | `--merge-csv` | Glob under directory (default `*.csv`) |
| `--encoding ENC` | `--dup`, `--merge-csv` | Input encoding (default `utf-8-sig`) |

## argv aliases

These literal spellings are normalized before `argparse`:

- `-sum` → `--sum`
- `-xc` → `--xc`
- `-sh` → `--sheets`
- `-dup` → `--dup`
- `-merge-csv` → `--merge-csv`

## Examples

```text
python xlstool.py -sum data.xls
python xlstool.py --sum report.xlsx -o summary.txt
python xlstool.py -sum book.xlsx -sh "1,Summary"
python xlstool.py --sum export.csv
python xlstool.py -sum data.csv -sh 1

python xlstool.py -xc book.xlsx
python xlstool.py --xc data.xls --sheets "Sheet1,Totals"
python xlstool.py -xc book.xlsx -sh "#2"
python xlstool.py --xc report.xlsx --csv-dir ./out_csv

python xlstool.py -dup data.csv --keys "1,3-5"
python xlstool.py --dup -i data.csv --keys "Name,Email"
python xlstool.py --dup report.csv --keys "1,2" -o dup_report.txt

python xlstool.py --merge-csv ./out/bank_parts
python xlstool.py --merge-csv ./out/bank_parts -o combined.csv
python xlstool.py --merge-csv ./data --merge-pattern "part-*.csv"
```

## Programmatic use

The module exposes helpers such as:

- `summarize_workbook(path, sheet_tokens)` → `(list[SheetStat], bad_tokens)`
- `export_workbook_csv(path, sheet_tokens, out_dir)` → `list[Path]`

`SheetStat` has `index`, `name`, `rows`, `columns`, and optional `column_labels`.

## Exit status

Commands return `0` on success and `1` on usage or processing errors (missing file, bad keys, no matching sheets, etc.).
