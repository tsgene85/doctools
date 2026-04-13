"""
Build a browser-based slideshow (HTML + copied media) from images and videos in a folder.
Open in Chrome; for video, serving over HTTP is most reliable (see --help).

Run: python folder2html.py -h
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HTTP_SERVER_PORT = 8765

IMAGE_EXT = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"})
VIDEO_EXT = frozenset({".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v", ".wmv"})

_MIME_FALLBACK = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".wmv": "video/x-ms-wmv",
}


def _file_data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = _MIME_FALLBACK.get(path.suffix.lower()) or "application/octet-stream"
    raw = path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _guess_lan_ipv4() -> str | None:
    """Best-effort LAN address for URLs (same Wi‑Fi as this PC). Not sent over the network."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None
    if ip.startswith(("127.", "0.")):
        return None
    return ip


def _natural_key(s: str) -> list:
    parts = re.split(r"(\d+)", s.lower())
    return [int(p) if p.isdigit() else p for p in parts]


def _parse_exif_datetime(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s[:19], fmt)
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def _exif_timestamp(path: Path) -> float | None:
    try:
        from PIL import Image
        from PIL.ExifTags import IFD
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            exif = im.getexif()
    except OSError:
        return None
    if not exif:
        return None
    dt_str: str | bytes | None = None
    try:
        if IFD.Exif in exif:
            sub = exif.get_ifd(IFD.Exif)
            dt_str = sub.get(36867) or sub.get(36868)
    except Exception:
        pass
    if not dt_str:
        dt_str = exif.get(306)
    if isinstance(dt_str, bytes):
        dt_str = dt_str.decode("utf-8", errors="ignore")
    if not dt_str or not isinstance(dt_str, str):
        return None
    return _parse_exif_datetime(dt_str)


def _parse_iso_timestamp(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = None
    if dt is None and len(s) >= 19 and s[4] == "-":
        chunk = s[:19].replace("T", " ")
        try:
            dt = datetime.strptime(chunk, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _ffprobe_tags_dict(data: dict) -> dict:
    out: dict = {}
    fmt = data.get("format") or {}
    for k, v in (fmt.get("tags") or {}).items():
        if v is not None:
            out[k] = v
    for stream in data.get("streams") or []:
        for k, v in (stream.get("tags") or {}).items():
            if v is not None and k not in out:
                out[k] = v
    return out


def _ffprobe_creation_timestamp(path: Path) -> float | None:
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    try:
        r = subprocess.run(
            [
                exe,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if r.returncode != 0 or not r.stdout:
            return None
        data = json.loads(r.stdout)
        tags = _ffprobe_tags_dict(data)
        for key in (
            "creation_time",
            "com.apple.quicktime.creationdate",
            "date",
            "ENCODED_DATE",
        ):
            raw = tags.get(key)
            if raw:
                t = _parse_iso_timestamp(str(raw))
                if t is not None:
                    return t
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        return None
    return None


_MAC_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc).timestamp()


def _mvhd_body_to_timestamp(body: bytes) -> float | None:
    if len(body) < 4:
        return None
    ver = body[0]
    if ver == 0 and len(body) >= 20:
        ctime = int.from_bytes(body[4:8], "big")
    elif ver == 1 and len(body) >= 32:
        ctime = int.from_bytes(body[4:12], "big")
    else:
        return None
    if ctime == 0:
        return None
    return _MAC_EPOCH + float(ctime)


def _mp4_scan_atoms(data: bytes, depth: int = 0) -> float | None:
    if depth > 24:
        return None
    o = 0
    n = len(data)
    while o + 8 <= n:
        size = int.from_bytes(data[o : o + 4], "big")
        typ = data[o + 4 : o + 8]
        header = 8
        if size == 1:
            if o + 16 > n:
                break
            size = int.from_bytes(data[o + 8 : o + 16], "big")
            header = 16
        if size < header or o + size > n:
            break
        start = o + header
        end = o + size
        body = data[start:end]
        if typ == b"moov":
            t = _mp4_scan_atoms(body, depth + 1)
            if t is not None:
                return t
        elif typ == b"mvhd":
            t = _mvhd_body_to_timestamp(body)
            if t is not None:
                return t
        else:
            if typ in (b"trak", b"mdia", b"minf", b"stbl", b"edts", b"udta", b"meta", b"clip"):
                t = _mp4_scan_atoms(body, depth + 1)
                if t is not None:
                    return t
        o = end
    return None


def _mp4_mvhd_timestamp(path: Path) -> float | None:
    if path.suffix.lower() not in {".mp4", ".m4v", ".mov"}:
        return None
    try:
        sz = path.stat().st_size
    except OSError:
        return None
    max_full_read = 100 * 1024 * 1024
    try:
        with path.open("rb") as f:
            if sz <= max_full_read:
                t = _mp4_scan_atoms(f.read())
                if t is not None:
                    return t
            head_n = min(sz, 6 * 1024 * 1024)
            f.seek(0)
            blob = f.read(head_n)
            t = _mp4_scan_atoms(blob)
            if t is not None:
                return t
            if sz > head_n:
                tail_n = min(sz, 16 * 1024 * 1024)
                f.seek(max(0, sz - tail_n))
                t = _mp4_scan_atoms(f.read())
                if t is not None:
                    return t
    except OSError:
        return None
    return None


def _video_metadata_timestamp(path: Path) -> float | None:
    t = _ffprobe_creation_timestamp(path)
    if t is not None:
        return t
    return _mp4_mvhd_timestamp(path)


def _capture_timestamp(path: Path) -> float:
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        t = _exif_timestamp(path)
        if t is not None:
            return t
    elif ext in VIDEO_EXT:
        t = _video_metadata_timestamp(path)
        if t is not None:
            return t
    return path.stat().st_mtime


def _timeline_sort_key(path: Path, *, reverse: bool) -> tuple:
    """Order by capture/metadata/mtime; break ties so videos are not listed after all photos."""
    ts = _capture_timestamp(path)
    is_vid = path.suffix.lower() in VIDEO_EXT
    type_tie = 0 if is_vid else 1
    nk = _natural_key(path.name)
    if reverse:
        return (-ts, type_tie, nk)
    return (ts, type_tie, nk)


def collect_media(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    files: list[Path] = []
    for p in folder.glob(pattern):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in IMAGE_EXT or ext in VIDEO_EXT:
            files.append(p)
    return files


def _safe_asset_filename(index: int, src: Path) -> str:
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", src.stem).strip("_")[:100] or "file"
    return f"{index:04d}_{stem}{src.suffix.lower()}"


def _build_index_html(
    title: str,
    slides: list[dict],
    *,
    auto_slideshow: bool,
    image_interval_sec: float,
    video_autoplay: bool,
) -> str:
    slides_js = json.dumps(slides, ensure_ascii=False)
    title_esc = html.escape(title)
    autoplay_js = "true" if video_autoplay else "false"
    auto_js = "true" if auto_slideshow else "false"
    dwell_ms = max(500, int(image_interval_sec * 1000))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title_esc}</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      height: 100%;
      background: #111;
      color: #eee;
      font-family: system-ui, Segoe UI, Roboto, sans-serif;
    }}
    #app {{
      display: flex;
      flex-direction: column;
      height: 100%;
    }}
    #stage-wrap {{
      flex: 1;
      display: flex;
      align-items: stretch;
      justify-content: stretch;
      padding: 8px;
      min-height: 0;
      width: 100%;
    }}
    #stage {{
      width: 100%;
      height: 100%;
      min-height: 0;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    #stage img {{
      max-width: 100%;
      max-height: 100%;
      width: auto;
      height: auto;
      object-fit: contain;
      vertical-align: middle;
    }}
    #stage video {{
      max-width: 100%;
      max-height: 100%;
      width: auto;
      height: auto;
      object-fit: contain;
      background: #000;
      vertical-align: middle;
    }}
    #bar {{
      flex-shrink: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      padding: 12px 16px;
      background: #1a1a1a;
      border-top: 1px solid #333;
      flex-wrap: wrap;
    }}
    button {{
      background: #333;
      color: #eee;
      border: 1px solid #555;
      padding: 10px 18px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 15px;
    }}
    button:hover {{ background: #444; }}
    #counter {{ min-width: 5em; text-align: center; font-variant-numeric: tabular-nums; }}
    #btn-pause {{ min-width: 7em; }}
    .hidden {{ display: none !important; }}
  </style>
</head>
<body>
  <div id="app">
    <div id="stage-wrap">
      <div id="stage"></div>
    </div>
    <div id="bar">
      <button type="button" id="btn-prev" aria-label="Previous">← Prev</button>
      <span id="counter"></span>
      <button type="button" id="btn-next" aria-label="Next">Next →</button>
      <button type="button" id="btn-pause" class="hidden" aria-label="Pause slideshow">Pause</button>
      <button type="button" id="btn-fs" aria-label="Fullscreen">Fullscreen</button>
    </div>
  </div>
  <script>
    const SLIDES = {slides_js};
    const VIDEO_AUTOPLAY = {autoplay_js};
    const AUTO_SLIDESHOW = {auto_js};
    const IMAGE_DWELL_MS = {dwell_ms};
    let i = 0;
    let slideTimer = null;
    let slideshowPaused = false;
    const stage = document.getElementById("stage");
    const counter = document.getElementById("counter");
    const btnPause = document.getElementById("btn-pause");

    function clearSlideTimer() {{
      if (slideTimer !== null) {{
        clearTimeout(slideTimer);
        slideTimer = null;
      }}
    }}

    function pauseAllVideos() {{
      stage.querySelectorAll("video").forEach(v => {{ v.pause(); try {{ v.currentTime = 0; }} catch (e) {{}} }});
    }}

    function configureVideoEl(v) {{
      v.controls = true;
      v.playsInline = true;
      v.setAttribute("playsinline", "");
      v.setAttribute("webkit-playsinline", "");
      v.preload = "auto";
    }}

    /** iOS / many tablets block unmuted programmatic play(); mute and retry so the show can run. */
    function tryPlayVideo(v, onStillFailed) {{
      if (!VIDEO_AUTOPLAY) return;
      const bail = typeof onStillFailed === "function" ? onStillFailed : () => {{}};
      const p = v.play();
      if (p === undefined) return;
      p.catch(() => {{
        v.muted = true;
        v.play().catch(bail);
      }});
    }}

    function scheduleAutoAdvance() {{
      clearSlideTimer();
      if (!AUTO_SLIDESHOW || slideshowPaused || !SLIDES.length) return;
      const s = SLIDES[i];
      if (s.type === "image") {{
        slideTimer = setTimeout(() => show(i + 1), IMAGE_DWELL_MS);
      }} else {{
        const v = stage.querySelector("video");
        if (!v) {{
          slideTimer = setTimeout(() => show(i + 1), IMAGE_DWELL_MS);
          return;
        }}
        const onEnd = () => {{
          v.removeEventListener("ended", onEnd);
          v.removeEventListener("error", onErr);
          show(i + 1);
        }};
        const onErr = () => {{
          v.removeEventListener("ended", onEnd);
          v.removeEventListener("error", onErr);
          slideTimer = setTimeout(() => show(i + 1), IMAGE_DWELL_MS);
        }};
        v.addEventListener("ended", onEnd);
        v.addEventListener("error", onErr, {{ once: true }});
        if (VIDEO_AUTOPLAY) {{
          tryPlayVideo(v, () => {{
            slideTimer = setTimeout(() => show(i + 1), IMAGE_DWELL_MS);
          }});
        }} else {{
          slideTimer = setTimeout(() => show(i + 1), IMAGE_DWELL_MS);
        }}
      }}
    }}

    function show(idx) {{
      if (!SLIDES.length) return;
      clearSlideTimer();
      i = (idx + SLIDES.length) % SLIDES.length;
      pauseAllVideos();
      const s = SLIDES[i];
      stage.innerHTML = "";
      if (s.type === "image") {{
        const img = document.createElement("img");
        img.src = s.src;
        img.alt = s.title || "";
        stage.appendChild(img);
      }} else {{
        const v = document.createElement("video");
        v.src = s.src;
        configureVideoEl(v);
        stage.appendChild(v);
        if (VIDEO_AUTOPLAY && !AUTO_SLIDESHOW) {{
          tryPlayVideo(v, () => {{}});
        }}
      }}
      counter.textContent = (i + 1) + " / " + SLIDES.length;
      scheduleAutoAdvance();
    }}

    function togglePause() {{
      if (!AUTO_SLIDESHOW) return;
      slideshowPaused = !slideshowPaused;
      btnPause.textContent = slideshowPaused ? "Resume" : "Pause";
      if (slideshowPaused) {{
        clearSlideTimer();
        pauseAllVideos();
      }} else {{
        scheduleAutoAdvance();
      }}
    }}

    if (AUTO_SLIDESHOW) {{
      btnPause.classList.remove("hidden");
      btnPause.textContent = "Pause";
    }}

    document.getElementById("btn-prev").onclick = () => show(i - 1);
    document.getElementById("btn-next").onclick = () => show(i + 1);
    btnPause.onclick = () => togglePause();
    document.getElementById("btn-fs").onclick = () => {{
      const el = document.documentElement;
      if (!document.fullscreenElement) el.requestFullscreen().catch(() => {{}});
      else document.exitFullscreen();
    }};

    document.addEventListener("keydown", (e) => {{
      if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") {{
        e.preventDefault();
        show(i + 1);
      }} else if (e.key === "ArrowLeft" || e.key === "PageUp") {{
        e.preventDefault();
        show(i - 1);
      }} else if (e.key === "p" || e.key === "P") {{
        e.preventDefault();
        togglePause();
      }} else if (e.key === "Home") show(0);
      else if (e.key === "End") show(SLIDES.length - 1);
    }});

    let tx = null;
    document.getElementById("stage-wrap").addEventListener("touchstart", (e) => {{
      tx = e.changedTouches[0].clientX;
    }}, {{ passive: true }});
    document.getElementById("stage-wrap").addEventListener("touchend", (e) => {{
      if (tx == null) return;
      const dx = e.changedTouches[0].clientX - tx;
      tx = null;
      if (dx < -50) show(i + 1);
      else if (dx > 50) show(i - 1);
    }}, {{ passive: true }});

    show(0);
  </script>
</body>
</html>
"""


def build_slideshow(
    source: Path,
    out_dir: Path,
    *,
    recursive: bool = False,
    sort_by: str = "name",
    sort_reverse: bool = False,
    title: str | None = None,
    auto_slideshow: bool = True,
    image_interval_sec: float = 5.0,
    video_autoplay: bool = True,
    offline: bool = False,
    embed_videos_max_mb: float = 0.0,
    verbose: bool = False,
) -> int:
    if not source.is_dir():
        print(f"Error: Not a directory: {source}", file=sys.stderr)
        return 1

    files = collect_media(source, recursive)
    if not files:
        print(f"No images or videos found in {source}", file=sys.stderr)
        return 1

    if sort_by == "mtime":
        files.sort(
            key=lambda p: (p.stat().st_mtime, _natural_key(p.name)),
            reverse=sort_reverse,
        )
    elif sort_by in ("date", "taken"):
        files.sort(key=lambda p: _timeline_sort_key(p, reverse=sort_reverse))
    else:
        files.sort(key=lambda p: _natural_key(p.name), reverse=sort_reverse)

    out_dir = out_dir.resolve()
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    embed_video_bytes = (
        int(embed_videos_max_mb * 1024 * 1024) if embed_videos_max_mb and embed_videos_max_mb > 0 else 0
    )

    slides: list[dict] = []
    used_names: set[str] = set()
    embedded_source_bytes = 0
    for idx, path in enumerate(files):
        is_video = path.suffix.lower() in VIDEO_EXT
        try:
            sz = path.stat().st_size
        except OSError as e:
            print(f"Error: {path}: {e}", file=sys.stderr)
            return 1

        inline = False
        if offline and not is_video:
            inline = True
        elif offline and is_video and embed_video_bytes > 0 and sz <= embed_video_bytes:
            inline = True

        if inline:
            try:
                src = _file_data_url(path)
            except OSError as e:
                print(f"Error reading {path}: {e}", file=sys.stderr)
                return 1
            embedded_source_bytes += sz
            if verbose:
                print(f"{path} -> embedded in HTML")
        else:
            name = _safe_asset_filename(idx, path)
            base = name
            n = 0
            while name in used_names:
                n += 1
                stem = Path(base).stem
                suf = Path(base).suffix
                name = f"{stem}_{n}{suf}"
            used_names.add(name)
            dest = assets_dir / name
            shutil.copy2(path, dest)
            src = "assets/" + name.replace("\\", "/")
            if verbose:
                print(f"{path} -> {dest}")

        slides.append(
            {
                "type": "video" if is_video else "image",
                "src": src,
                "title": path.name,
            }
        )

    if not any(assets_dir.iterdir()):
        assets_dir.rmdir()

    if offline and embedded_source_bytes > 80 * 1024 * 1024:
        print(
            f"Warning: offline page embeds ~{embedded_source_bytes / (1024 * 1024):.0f} MiB — "
            "some devices may load slowly or run out of memory.",
            file=sys.stderr,
        )

    ttl = title or f"Slideshow — {source.name}"
    index_path = out_dir / "index.html"
    index_path.write_text(
        _build_index_html(
            ttl,
            slides,
            auto_slideshow=auto_slideshow,
            image_interval_sec=image_interval_sec,
            video_autoplay=video_autoplay,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {index_path} ({len(slides)} slide(s))")
    uri = index_path.resolve().as_uri()

    if offline:
        mb = embedded_source_bytes / (1024 * 1024)
        print(f"Offline bundle: ~{mb:.1f} MiB of media embedded in the HTML (plus files in assets/ if any).")
        print(f"On this PC you can open: {uri}")
        print("")
        print("On a phone/tablet:")
        print(f"  1. Copy the whole folder to internal storage: {out_dir}")
        print("  2. Open index.html with Files / Chrome / “Open with” (keep assets/ next to it if present).")
        print("  3. Videos still need the assets/ folder unless you used --embed-videos-max-mb.")
        print("     Some mobile browsers block local video; then use a Wi‑Fi server instead.")
    else:
        print(f"Open file directly on this PC (videos may be flaky): {uri}")
        print("")
        print("Reliable playback (especially video): run a tiny server in this folder, then use http://")
        print(f'  cd "{out_dir}"')
        print(f"  py -3 -m http.server {HTTP_SERVER_PORT}")
        print("  (or: python -m http.server {})".format(HTTP_SERVER_PORT))
        print("")
        print("Then in the browser:")
        print(f"  • This PC only:        http://127.0.0.1:{HTTP_SERVER_PORT}/")
        lan = _guess_lan_ipv4()
        if lan:
            print(f"  • Phone/tablet (same Wi‑Fi): http://{lan}:{HTTP_SERVER_PORT}/")
        else:
            print(
                "  • Phone/tablet (same Wi‑Fi): Settings → Network → Wi‑Fi → your network → "
                "IPv4 address, then http://THAT_ADDRESS:{}/".format(HTTP_SERVER_PORT)
            )
        print("  (Do not use file:// on the tablet.)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a browser slideshow (index.html + assets/) from images and videos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python folder2html.py -d ./photos -o ./my_show
  python folder2html.py -d ./media -r -o ./gallery --interval 8
  python folder2html.py -d ./photos -o ./manual --no-auto
  python folder2html.py -d ./photos -o ./by_camera --sort taken
  python folder2html.py -d ./photos -o ./newest_first --sort taken --reverse
  python folder2html.py -d ./photos -o ./by_date --sort date
  python folder2html.py -d ./photos -o ./phone_show --offline
  python folder2html.py -d ./mix -o ./phone_show --offline --embed-videos-max-mb 12

Then either:
  - Open my_show/index.html on a PC only (videos often need the server below)
  - Or: cd my_show && py -3 -m http.server 8765
    this PC: http://127.0.0.1:8765/
    tablet (same Wi‑Fi): http://ADDRESS_PRINTED_BY_FOLDER2HTML:8765/
        """,
    )
    parser.add_argument("-d", "--directory", required=True, help="Folder with images and/or videos")
    parser.add_argument(
        "-o",
        "--output",
        default="html_slideshow",
        help="Output directory (default: html_slideshow). Will contain index.html and assets/",
    )
    parser.add_argument("-r", "--recursive", action="store_true", help="Include subfolders")
    parser.add_argument(
        "--sort",
        dest="sort_by",
        choices=("name", "mtime", "date", "taken"),
        default="name",
        help="Order slides: name (natural); mtime (filesystem modified only, Explorer column); "
        "date or taken (same): EXIF + ffprobe creation time when available, else modified — "
        "so videos are not stuck after older photos by mistake",
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Reverse sort order (e.g. newest-first with --sort taken)",
    )
    parser.add_argument("--title", default=None, help="HTML page title")
    parser.add_argument(
        "--no-auto",
        dest="auto_slideshow",
        action="store_false",
        default=True,
        help="Disable automatic advance; use Prev/Next only (P / Pause hidden)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        metavar="SEC",
        help="Seconds to show each image before advancing (default: 5). Videos advance when playback ends.",
    )
    parser.add_argument(
        "--no-video-autoplay",
        action="store_true",
        help="Do not call play() on video slides; with auto-advance on, videos still advance after the image interval",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Embed images in index.html (data URLs) for copying the folder to a device; "
        "large videos stay in assets/ unless --embed-videos-max-mb",
    )
    parser.add_argument(
        "--embed-videos-max-mb",
        type=float,
        default=0,
        metavar="MB",
        help="With --offline, embed each video up to this size (MiB) into the HTML; 0 = never (default)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    if args.embed_videos_max_mb and not args.offline:
        parser.error("--embed-videos-max-mb requires --offline")
    if args.embed_videos_max_mb < 0:
        parser.error("--embed-videos-max-mb must be >= 0")
    sys.exit(
        build_slideshow(
            Path(args.directory),
            Path(args.output),
            recursive=args.recursive,
            sort_by=args.sort_by,
            sort_reverse=args.reverse,
            title=args.title,
            auto_slideshow=args.auto_slideshow,
            image_interval_sec=args.interval,
            video_autoplay=not args.no_video_autoplay,
            offline=args.offline,
            embed_videos_max_mb=args.embed_videos_max_mb,
            verbose=args.verbose,
        )
    )


if __name__ == "__main__":
    main()
