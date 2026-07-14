---
type: CLI Tool
title: doc2text
description: Extract text from PDF, DOCX, or DOC into same-stem JSON for NLP (sumai-compatible).
resource: file:///M:/LCode/doctools/doc2text.py
tags: [cli, nlp, pdf, docx, text]
timestamp: 2026-07-13T17:00:00Z
---

# Usage

```bash
python doc2text.py -i report.docx    # writes report.json beside it
python doc2text.py -i scan.pdf
python doc2text.py -i legacy.doc     # LibreOffice required
python doc2text.py -d ./inbox -r
python sumai.py -i report.json -q "Summarize"
```

# Behavior

| Input | Method |
|-------|--------|
| `.pdf` | Same page text helpers as [pdfextract](/tools/pdfextract.md) |
| `.docx` | `python-docx` (paragraphs + tables) |
| `.doc` | LibreOffice → DOCX (or PDF fallback), then extract |

Output JSON includes `source`, `format`, `pages` (for [sumai](/tools/sumai.md)), concatenated `text`, `has_text`, and `page_count`.

PDFs with no extractable text layer fail with an OCR hint (`python pdfocr.py -i … -O`). Use `--allow-empty` to write JSON anyway (`has_text: false`). [processdb](/tools/processdb.md) counts these as `no_text`.
