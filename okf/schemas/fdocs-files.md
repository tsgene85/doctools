---
type: SQLite Table
title: fdocs2db files
description: Lean per-file inventory written by fdocs2db (table name files, not media).
resource: file:///M:/LCode/doctools/fdocs2db.py
tags: [sqlite, schema, fdocs2db]
timestamp: 2026-07-13T16:00:00Z
---

Producer: [fdocs2db](/tools/fdocs2db.md)

# Schema

Table: **`files`**

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `relative_path` | TEXT | Path relative to `-r` / `-f` (unique) |
| `extension` | TEXT | Lowercase suffix, or `(none)` |
| `size_bytes` | INTEGER | File size |
| `file_ctime_utc` | TEXT | Creation/birth time UTC ISO |
| `file_mtime_utc` | TEXT | Modification time UTC ISO |

Table: **`scan_meta`**

| key | value example |
|-----|----------------|
| `folder` | Absolute scan folder |
| `path_root` | Absolute path root for relatives |
| `scanned_at_utc` | ISO timestamp |
| `file_count` | Row count |
| `schema_version` | `2` |

# Examples

```sql
SELECT extension, COUNT(*), SUM(size_bytes)
FROM files
GROUP BY extension
ORDER BY COUNT(*) DESC;
```
