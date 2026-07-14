---
type: Playbook
title: Setup
description: Create the Python environment and install optional dependency groups for doctools.
tags: [setup, uv, windows]
timestamp: 2026-07-13T16:00:00Z
---

# Steps

1. From the repo root:

```bash
uv venv .venv
uv sync
```

2. Windows activate:

```powershell
.venv\Scripts\Activate.ps1
```

3. Optional groups (examples):

```bash
uv sync --group common          # ocr + ai + ppt + video + paddle
uv sync --group ocr
uv sync --group gphoto          # Google Photos API demo
uv sync --group ai
uv sync --all-extras            # includes faces/insightface stack
```

# System tools (selected)

| Tool | Needed by | Notes |
|------|-----------|--------|
| Tesseract | [pdfocr](/tools/pdfocr.md) | Required for OCR |
| Ghostscript | [pdfocr](/tools/pdfocr.md) | Optional; smaller output with `--optimize` |
| Deno (or Node) | [downvideo](/tools/downvideo.md) | Required for YouTube (yt-dlp EJS) |
| ffmpeg | [downvideo](/tools/downvideo.md) | Optional; best quality audio+video merge |

# Citations

[1] Repo [README.md](/../README.md) (project root)
[2] [COMMAND_LINE.md](/../COMMAND_LINE.md)
