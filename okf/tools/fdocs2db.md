---
type: CLI Tool
title: fdocs2db
description: Inventory all files under a folder into SQLite table files or CSV.
resource: file:///M:/LCode/doctools/fdocs2db.py
tags: [cli, sqlite, inventory, documents]
timestamp: 2026-07-13T16:00:00Z
---

# Usage

```bash
python fdocs2db.py -h
python fdocs2db.py -f DIR -o out.db
python fdocs2db.py -f DIR -r ROOT -o out.db -v
```

| Flag | Meaning |
|------|---------|
| `-f` | Folder to scan recursively |
| `-r` | Path root for `relative_path` (default = `-f`) |
| `-o` | `.db` / `.sqlite` / `.csv` |
| `-v` | Progress |

# Schema

See [fdocs files](/schemas/fdocs-files.md). Table name is **`files`**.

# Workflow

[Folder documents inventory](/workflows/folder-docs.md)
