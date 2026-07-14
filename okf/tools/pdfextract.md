---
type: CLI Tool
title: pdfextract
description: Extract page ranges from a PDF; optional text export to .txt/.json.
resource: file:///M:/LCode/doctools/pdfextract.py
tags: [cli, pdf]
timestamp: 2026-07-13T16:00:00Z
---

```bash
python pdfextract.py -i doc.pdf -o out.pdf -p 1,3-5
python pdfextract.py -i doc.pdf -o out.pdf -p 1-5 -t out.json
python pdfextract.py -d ./pdfs -p 1-3
```
