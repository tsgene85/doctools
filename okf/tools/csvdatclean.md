---
type: CLI Tool
title: csvdatclean
description: Trim empty CSV edges/columns and flatten +$/-$ money cells to plain numbers.
resource: file:///M:/LCode/doctools/csvdatclean.py
tags: [cli, csv, clean]
timestamp: 2026-08-04T16:00:00Z
---


# Usage

```bash
python csvdatclean.py -d data.csv
python csvdatclean.py -d data.csv -o cleaned.csv -v
```

Keeps the leading contiguous table (stops at the first blank row, dropping footer boilerplate). Truncates trailing empty columns and rows, removes fully empty columns, and rewrites cells like `+$1,234.56` / `-$10.00` / `$0.00` as plain numbers. Default output: `<stem>_clean.csv` beside the input.
