"""
Download a YouTube video with yt-dlp.
Requires: uv sync --group video, a JS runtime (Deno recommended), ffmpeg optional.
Run: python downvideo.py -h
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


def _find_js_runtime() -> dict[str, dict] | None:
    """
    yt-dlp needs a JS runtime for YouTube (EJS challenges).
    Deno is enabled by default; Node needs explicit enable.
    Returns js_runtimes mapping: {runtime: {path?: ...}} or None.
    """

    def with_path(name: str, path: str) -> dict[str, dict]:
        return {name: {"path": path}}

    for name in ("deno", "deno.exe"):
        path = shutil.which(name)
        if path:
            return with_path("deno", path)
    for candidate in (
        Path.home() / ".deno" / "bin" / "deno.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "deno.exe",
        Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" / "deno" / "bin" / "deno.exe",
    ):
        if candidate.is_file():
            return with_path("deno", str(candidate))

    node = shutil.which("node")
    if node:
        return with_path("node", node)
    bun = shutil.which("bun")
    if bun:
        return with_path("bun", bun)
    return None


def download_youtube_video(url: str, output_dir: str = "downloads") -> None:
    try:
        import yt_dlp
    except ImportError:
        print(
            "Error: yt-dlp is not installed.\n"
            "  uv sync --group video\n"
            "  (uses yt-dlp[default], which includes YouTube EJS scripts)",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    js_runtimes = _find_js_runtime()
    if not js_runtimes:
        print(
            "Error: No JavaScript runtime found. YouTube downloads need Deno (recommended) or Node.\n"
            "  winget install DenoLand.Deno\n"
            "  See https://github.com/yt-dlp/yt-dlp/wiki/EJS",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Prefer best quality (video+audio merged); needs ffmpeg installed
    ydl_opts: dict = {
        "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "js_runtimes": js_runtimes,
        # Allow fetching EJS if the python package is missing/outdated
        "remote_components": ["ejs:github"],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        msg = str(e).lower()
        if "ffmpeg" in msg:
            print("ffmpeg not found. Downloading single format (no merge)...")
            ydl_opts["format"] = "best[ext=mp4]/best"
            ydl_opts.pop("merge_output_format", None)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        else:
            print(f"Download failed: {e}", file=sys.stderr)
            raise SystemExit(1) from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download a YouTube video using yt-dlp. Needs Deno/Node; ffmpeg optional for best merge.",
        epilog=(
            "Setup: uv sync --group video && winget install DenoLand.Deno\n"
            "Example: python downvideo.py 'https://www.youtube.com/watch?v=...' -o downloads"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", default=None, help="YouTube URL (optional; will prompt if omitted)")
    parser.add_argument("-o", "--output-dir", default="downloads", help="Output directory (default: downloads)")
    args = parser.parse_args()
    video_url = args.url
    if not video_url:
        video_url = input("Enter YouTube URL: ").strip()
    if not video_url:
        print("Error: No URL provided.", file=sys.stderr)
        raise SystemExit(1)
    download_youtube_video(video_url, output_dir=args.output_dir)
