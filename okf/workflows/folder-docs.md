---
type: Workflow
title: Folder documents inventory
description: First step of a document-organization pipeline — inventory every file under a folder into SQLite table files.
tags: [documents, sqlite, workflow, inventory]
timestamp: 2026-07-13T16:00:00Z
---

# Goal

Capture a lean file inventory (path, extension, size, timestamps) as the base for later classification and stats scripts.

# Steps

1. Choose the folder to organize.
2. Run [fdocs2db](/tools/fdocs2db.md):

```bash
python fdocs2db.py -f "G:/Docs/archive" -o testdocs/fdocs.db
```

Paths relative to a parent root:

```bash
python fdocs2db.py -f "G:/Docs/2021" -r "G:/Docs" -o docs_2021.db
```

3. Summarize with [dbstat](/tools/dbstat.md) (e.g. duplicate paths):

```bash
python dbstat.py -d testdocs/fdocs.db -s dup -c relative_path -t files
```

4. Later: classification scripts can `ALTER TABLE files` or join new tables keyed by `relative_path`.

# Outputs

- SQLite table **`files`** — see [fdocs files schema](/schemas/fdocs-files.md)
- Table **`scan_meta`** — scan folder, path root, timestamp, counts
