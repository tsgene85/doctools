---
type: SQLite Table
title: gpht2db media
description: Per-file Takeout inventory; photos/videos include sidecar-derived Google fields.
resource: file:///M:/LCode/doctools/gpht2db.py
tags: [sqlite, schema, gpht2db, photos]
timestamp: 2026-07-13T16:00:00Z
---

Producer: [gpht2db](/tools/gpht2db.md)

# Schema

Table: **`media`** (historical name; rows include all file types)

| Column | Description |
|--------|-------------|
| `relative_path` | Path relative to `-r` / `-f` |
| `media_type` | `image` / `video` / `json` / `other` |
| `filename` | Basename |
| `title` | From sidecar when present |
| `file_ctime_utc` / `file_mtime_utc` | Filesystem times |
| `photo_taken_ts` / `photo_taken_utc` | Takeout `photoTakenTime` |
| `creation_ts` / `creation_utc` | Takeout `creationTime` |
| `modification_ts` / `modification_utc` | Takeout `modificationTime` |
| `google_unique_id` | From Takeout URL path, else synthesized |
| `google_url` | Sidecar `url` |
| `sidecar_path` | Relative path to JSON sidecar |
| `description`, `latitude`, `longitude`, `image_views` | Sidecar extras |

Sidecar enrichment applies only when `media_type` is `image` or `video`.

# Related

- Dup analysis: [dbstat](/tools/dbstat.md)
- Workflow: [photos-takeout](/workflows/photos-takeout.md)
