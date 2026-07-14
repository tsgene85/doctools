---
type: Workflow
title: Google Photos Takeout inventory
description: Walk a Takeout export, write all files to SQLite/CSV with Takeout sidecar enrichment for photos/videos, then analyze duplicates.
tags: [photos, takeout, sqlite, workflow]
timestamp: 2026-07-13T16:00:00Z
---

# Goal

Build a searchable inventory of a Google Photos Takeout tree, including sidecar metadata (photo taken time, Google IDs) for media.

# Steps

1. Unzip / place Takeout under a stable root (example: `G:/.../takeout-...`).
2. Run [gpht2db](/tools/gpht2db.md):

```bash
python gpht2db.py -f "G:/path/to/takeout" -o testdocs/gpht_all.db
```

Optional: scan one album but keep paths relative to Takeout root:

```bash
python gpht2db.py -f "G:/takeout/Album" -r "G:/takeout" -o album.db
```

3. Inspect duplicates with [dbstat](/tools/dbstat.md):

```bash
python dbstat.py -d testdocs/gpht_all.db -s dup -c google_unique_id
python dbstat.py -d album.db -d2 testdocs/gpht_all.db -s dup2 -c google_unique_id
```

# Outputs

- SQLite table `media` (see [gpht media schema](/schemas/gpht-media.md)) — one row per **file** (photos, videos, JSON sidecars, other).
- Sidecar fields populated only for photo/video rows.

# Related

- API demo (not Takeout): [gphoto_api_demo](/tools/gphoto_api_demo.md)
- Generic folder inventory (no Takeout JSON): [folder-docs workflow](/workflows/folder-docs.md)
