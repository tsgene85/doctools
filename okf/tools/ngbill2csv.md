---
type: CLI Tool
title: ngbill2csv
description: Extract National Grid electric bill fields from a folder of PDF statements to CSV.
resource: file:///M:/LCode/doctools/ngbill2csv.py
tags: [cli, pdf, csv, utility, national-grid]
timestamp: 2026-08-03T14:30:00Z
---

# Usage

```bash
python ngbill2csv.py -f testdocs/NGBills
python ngbill2csv.py -f testdocs/NGBills -o testdocs/NGBills/ng_bills.csv -v
python ngbill2csv.py -f ./bills -r -o ng_bills.csv
```

| Flag | Meaning |
|------|---------|
| `-f` / `--folder` | Folder of National Grid bill PDFs (required) |
| `-o` / `--output` | Output CSV (default: `<folder>/ng_bills.csv`) |
| `-r` / `--recursive` | Include PDFs in subfolders |
| `-v` / `--verbose` | Print per-file parse summary |

# What it extracts

One CSV row per PDF. Fields include:

- Account number, customer name, service address
- Bill issued date, billing period, due / auto-pay dates
- Amount due; previous balance / payments / current charges (NG delivery, other supplier, adjustments)
- Meter number, rate class, previous & current readings (Actual/Estimated), usage kWh, billing days
- Delivery rates and amounts (dist, transmission, efficiency, solar, EV, net-meter credit, …)
- Credit-balance / solar bill layout when present (`parse_notes` may include `solar`)

PDFs need a text layer (typical e-bills). Scanned image-only bills: OCR first with [pdfocr](/tools/pdfocr.md).

# Related

[pdfextract](/tools/pdfextract.md), [doc2text](/tools/doc2text.md), [pdfocr](/tools/pdfocr.md)
