---
type: Playbook
title: Compare two inventory databases
description: Find values of a column that appear in both SQLite inventories (dup2).
tags: [sqlite, dbstat, playbook]
timestamp: 2026-07-13T16:00:00Z
---

# Steps

1. Build two DBs (e.g. album vs full Takeout) with [gpht2db](/tools/gpht2db.md) or [fdocs2db](/tools/fdocs2db.md).
2. Run:

```bash
python dbstat.py -d album.db -d2 all.db -s dup2 -c google_unique_id -n 50
```

For folder inventories:

```bash
python dbstat.py -d a.db -d2 b.db -s dup2 -c relative_path -t files -t2 files
```

# Related

[dbstat](/tools/dbstat.md), [photos-takeout workflow](/workflows/photos-takeout.md)
