---
type: Workflow
title: Extract document text for NLP
description: Turn PDF/DOCX/DOC into same-stem JSON, then optionally query with sumai.
tags: [nlp, pdf, docx, workflow]
timestamp: 2026-07-13T17:00:00Z
---

# Steps

1. Run [doc2text](/tools/doc2text.md) on a file or folder:

```bash
python doc2text.py -i contract.docx
python doc2text.py -d ./inbox -r
```

2. JSON appears beside each source (`contract.json`).
3. Optional Q&A with [sumai](/tools/sumai.md):

```bash
python sumai.py -i contract.json -q "What are the key obligations?"
```

# Notes

- Legacy `.doc` needs LibreOffice (`soffice`) installed.
- Encrypted PDFs: decrypt with [pdfdecrypt](/tools/pdfdecrypt.md) first.
- Image-only PDFs may need [pdfocr](/tools/pdfocr.md) before text extract.
