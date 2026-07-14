---
type: CLI Tool
title: extractFaces
description: Detect faces, compute embeddings, cluster; write JSON manifests.
resource: file:///M:/LCode/doctools/extractFaces.py
tags: [cli, faces, cv]
timestamp: 2026-07-13T16:00:00Z
---

```bash
uv sync --group faces
python extractFaces.py -i photos/raw -o artifacts/manifests
```

Review: [reviewFaces](/tools/reviewFaces.md). Export: [export_cvat](/tools/export_cvat.md).
