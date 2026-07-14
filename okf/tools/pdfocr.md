---
type: CLI Tool
title: pdfocr
description: Deskew and OCR scanned PDFs into searchable PDFs (Tesseract via OCRmyPDF; optional Paddle).
resource: file:///M:/LCode/doctools/pdfocr.py
tags: [cli, pdf, ocr]
timestamp: 2026-07-13T16:00:00Z
---

Requires Tesseract on PATH (optional Ghostscript for `--optimize`).

```bash
python pdfocr.py -i scanned.pdf -o searchable.pdf
python pdfocr.py -i scanned.pdf -O
python pdfocr.py -i form.pdf -O --engine paddle
```

Longer notes: repo `pdfocr.md`.
