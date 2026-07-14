---
type: CLI Tool
title: gphoto_api_demo
description: OAuth demo for Google Photos Library API (app-created only) and Picker API (user selection).
resource: file:///M:/LCode/doctools/gphoto_api_demo.py
tags: [cli, photos, oauth, api]
timestamp: 2026-07-13T16:00:00Z
---

Library API cannot list a user's full library (post-2025 scopes). Use **picker** to select items.

```bash
uv sync --group gphoto
python gphoto_api_demo.py auth -c client_secret.json
python gphoto_api_demo.py albums
python gphoto_api_demo.py media -n 20
python gphoto_api_demo.py picker -o picked.json
```

For offline Takeout inventory see [gpht2db](/tools/gpht2db.md).

# Citations

[1] [Google Photos Library get started](https://developers.google.com/photos/library/guides/get-started-library)
[2] [Photos Picker get started](https://developers.google.com/photos/picker/guides/get-started-picker)
