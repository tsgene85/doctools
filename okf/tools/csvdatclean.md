---
type: CLI Tool
title: csvdatclean
description: Trim empty CSV edges/columns; flatten money cells; optional -cs currency standardization (paren negatives).
resource: file:///M:/LCode/doctools/csvdatclean.py
tags: [cli, csv, clean, currency]
timestamp: 2026-08-09T14:00:00Z
---


# Usage

```bash
python csvdatclean.py -d data.csv
python csvdatclean.py -d data.csv -o cleaned.csv -v
python csvdatclean.py -d history.csv -cs -v
```

Keeps the leading contiguous table (stops at the first blank row, dropping footer boilerplate). Truncates trailing empty columns and rows, removes fully empty columns, and rewrites cells like `+$1,234.56` / `-$10.00` / `$0.00` as plain numbers. Default output: `<stem>_clean.csv` beside the input.

## `-cs` / `--currency-standardize`

Detects currency columns via header keywords (`Amount`, `Balance`, `Debit`, …) plus cell patterns, then normalizes those columns:

- `(1,234.56)` / `($1,234.56)` → `-1234.56`
- strips `$` and thousands commas on signed/unsigned amounts

Use `-v` to print which columns were detected.
