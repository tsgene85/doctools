---
type: CLI Tool
title: adppay2csv
description: Extract ADP paystub fields from a folder of PDF earnings statements to CSV (upsert by advice number).
resource: file:///M:/LCode/doctools/adppay2csv.py
tags: [cli, pdf, csv, payroll, adp]
timestamp: 2026-08-04T22:00:00Z
---


# Usage

```bash
python adppay2csv.py -f testdocs/pay_statements_ADP
python adppay2csv.py -f testdocs/pay_statements_ADP -o testdocs/pay_statements_ADP/adp_pay.csv -v
python adppay2csv.py -f ./stubs -r -o adp_pay.csv
```

| Flag | Meaning |
|------|---------|
| `-f` / `--folder` | Folder of ADP paystub PDFs (required) |
| `-o` / `--output` | Output CSV (default: `<folder>/adp_pay.csv`) |
| `-r` / `--recursive` | Include PDFs in subfolders |
| `-v` / `--verbose` | Print per-file parse summary |

# Upsert behavior

Each statement is keyed by **advice number** (`record_key=advice:…`). If advice number is missing, fallback key is `pay_date|employee|period_ending`.

Re-running with the same `-o` **updates** rows whose key already exists and **appends** only new stubs. Rows are sorted by pay date.

# What it extracts

One CSV row per PDF. Fields include:

- Advice number, pay date, period beginning/ending
- Employee name/address; company name/address/phone; CO / file / clock codes
- Filing status, federal withholding note, MA taxable status
- Regular / holiday earnings (rate, hours, period, YTD); total hours; gross / net / direct deposit
- Statutory taxes (FIT, SS, Medicare, MA state, MA PFML / PML) period + YTD
- Other benefits: `401K W` wage amounts; `Chsupp` when present
- Masked deposit account; federal taxable wages

Requires **PyMuPDF** (`pymupdf`) for ADP layout. PDFs need a text layer.

# Related

[ngbill2csv](/tools/ngbill2csv.md), [pdfextract](/tools/pdfextract.md), [pdfocr](/tools/pdfocr.md)
