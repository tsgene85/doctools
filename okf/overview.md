---
type: Project
title: doctools
description: Local CLI toolkit for PDFs, Google Photos Takeout inventory, folder-document DBs, and related media helpers.
resource: file:///M:/LCode/doctools
tags: [doctools, cli, pdf, photos, sqlite]
timestamp: 2026-07-13T16:00:00Z
---

# Purpose

**doctools** is a Python project of standalone scripts (run from `.venv`) for everyday document and media chores:

- PDF merge / extract / decrypt / OCR
- Google Photos Takeout → inventory DB/CSV ([gpht2db](/tools/gpht2db.md))
- Generic folder file inventory for organization workflows ([fdocs2db](/tools/fdocs2db.md))
- PDF/Word → NLP JSON ([doc2text](/tools/doc2text.md))
- SQLite duplicate summaries ([dbstat](/tools/dbstat.md))
- Optional Google Photos API demo, faces/CVAT helpers, video download, Q&A

Human-oriented command examples also live in repo root `COMMAND_LINE.md` and `README.md`. This OKF bundle is the agent-friendly, linkable knowledge graph.

# Entry points

| Need | Start here |
|------|------------|
| Install | [Setup](/setup.md) |
| Organize a folder of docs | [Folder docs workflow](/workflows/folder-docs.md) |
| Inventory Google Takeout | [Photos Takeout workflow](/workflows/photos-takeout.md) |
| Decrypt a PDF | [Decrypt PDF playbook](/playbooks/decrypt-pdf.md) |
| Tool reference | [Tools index](/tools/) |

# Design notes

- Scripts are mostly flat `*.py` at repo root; invoke with `python script.py -h`.
- Optional deps are split into uv groups / extras (`ocr`, `ai`, `gphoto`, `faces`, …).
- Inventory tools default to SQLite (`.db`) or CSV based on `-o` extension.
