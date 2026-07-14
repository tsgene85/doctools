---
type: CLI Tool
title: processdb
description: Process each inventory DB file with a method; filters by extension and folder.
resource: file:///M:/LCode/doctools/processdb.py
tags: [cli, sqlite, workflow, nlp]
timestamp: 2026-07-13T22:30:00Z
---

# Usage

```bash
python processdb.py -d testdocs/fdocs.db -m doc2text
python processdb.py -d testdocs/fdocs.db -m doc2text -fex pdf,docx -ffl Contracts
python processdb.py -d testdocs/fdocs.db -m doc2text -r "G:/Docs" --skip-existing
python processdb.py -d testdocs/fdocs.db -m pdfextract -u -ffl Contracts -v
python processdb.py -d testdocs/fdocs.db -m pdfextract --ocr -u -ffl Contracts -v
python processdb.py -d testdocs/fdocs.db -m pdfocr -ffl Contracts -v
```

| Flag | Meaning |
|------|---------|
| `-d` | Inventory SQLite DB |
| `-m` | Method (`doc2text`, `pdfextract`, `pdfocr`) |
| `-fex` | Extension filter (`pdf,docx,.doc`) |
| `-ffl` | Folder filter (path prefix or segment) |
| `-r` | Filesystem root (default: `scan_meta.path_root`) |
| `-t` | Table (`files` preferred) |
| `-n` | Limit rows |
| `-u` / `--update` | Overwrite existing JSON / OCR sidecars |
| `--ocr` | OCR image-only PDFs to `<stem>_ext.pdf` then extract (`pdfextract` / `doc2text`) |
| `--skip-existing` | Skip if output already exists (`doc2text`; ignored with `-u`) |
| `--allow-empty` | Write JSON for PDFs with no text layer |

# Methods

- **doc2text** — calls [doc2text](/tools/doc2text.md) for each match
- **pdfextract** — create `.json` next to PDFs missing a JSON pair; `-u` overwrites; `--ocr` for scans
- **pdfocr** — create searchable `<stem>_ext.pdf` via [pdfocr](/tools/pdfocr.md)

# Related

[fdocs2db](/tools/fdocs2db.md), [folder-docs workflow](/workflows/folder-docs.md)
