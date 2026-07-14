---
type: CLI Tool
title: dbstat
description: Read-only SQLite summaries — duplicate values in one DB or shared values across two DBs.
resource: file:///M:/LCode/doctools/dbstat.py
tags: [cli, sqlite, stats]
timestamp: 2026-07-13T16:00:00Z
---

# Usage

```bash
python dbstat.py -d FILE -s dup -c COLUMN
python dbstat.py -d A.db -d2 B.db -s dup2 -c COLUMN
python dbstat.py -d fdocs.db -s dup -c relative_path -t files
```

| Flag | Meaning |
|------|---------|
| `-d` / `-d2` | Primary / second database |
| `-s dup` | Duplicates within one DB |
| `-s dup2` | Values of `-c` present in both DBs |
| `-c` | Column name |
| `-t` / `-t2` | Table(s); auto if only one table |
| `-n` | Max groups to list (`0` = all) |
| `-e` | Example paths per value |

Uses Python `sqlite3` (no system sqlite CLI). Opens DB read-only.
