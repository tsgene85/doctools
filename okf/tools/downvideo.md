---
type: CLI Tool
title: downvideo
description: Download a YouTube video with yt-dlp (ffmpeg optional for best merge quality).
resource: file:///M:/LCode/doctools/downvideo.py
tags: [cli, video, youtube]
timestamp: 2026-07-13T16:00:00Z
---

```bash
uv sync --group video
winget install DenoLand.Deno   # JS runtime required for YouTube (EJS)
python downvideo.py "https://www.youtube.com/watch?v=..." -o downloads
```

Uses `yt-dlp[default]` (includes EJS scripts). ffmpeg is optional for best quality merge.
