---
type: CLI Tool
title: sumai
description: Answer a question about a .txt or .json document using the OpenAI API.
resource: file:///M:/LCode/doctools/sumai.py
tags: [cli, openai, qa]
timestamp: 2026-07-13T16:00:00Z
---

Requires `OPENAI_API_KEY`.

```bash
python sumai.py -i document.txt -q "What is the main conclusion?"
python sumai.py -i out.json -q "Summarize key points" --model gpt-4o
```

Pairs well with text from [pdfextract](/tools/pdfextract.md) `-t`.
