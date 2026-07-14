---
type: CLI Tool
title: gpht2db
description: Inventory a Google Photos Takeout tree (all files); enrich photos/videos from sidecar JSON.
resource: file:///M:/LCode/doctools/gpht2db.py
tags: [cli, sqlite, photos, takeout]
timestamp: 2026-07-13T16:00:00Z
---

# Usage

```bash
python gpht2db.py -h
python gpht2db.py -f "G:/Takeout" -o gpht.db
python gpht2db.py -f "G:/Takeout/Album" -r "G:/Takeout" -o album.db
```

Inventories **all files** (not only images/videos). Sidecar metadata is applied to photos/videos only. Console prints total count and extension breakdown (no image/video/json type summary).

# Schema

See [gpht media](/schemas/gpht-media.md).

# Workflow

[Photos Takeout inventory](/workflows/photos-takeout.md)
