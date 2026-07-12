"""
Build an inventory from a Google Photos Takeout folder (CSV or SQLite).

Walks -f/--folder recursively, pairs each media file with its Takeout sidecar
JSON (when present), and writes relative path, filesystem dates, Google
timestamps, and a Google unique ID (from URL when available).

Output format is chosen by -o extension: .csv → CSV; .db / .sqlite / .sqlite3 → SQLite.

Run: python gpht2db.py -h
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

IMAGE_EXT = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
        ".heic",
        ".heif",
        ".raw",
        ".cr2",
        ".nef",
        ".dng",
        ".arw",
    }
)
VIDEO_EXT = frozenset(
    {
        ".mp4",
        ".mov",
        ".m4v",
        ".avi",
        ".mkv",
        ".webm",
        ".wmv",
        ".mpg",
        ".mpeg",
        ".3gp",
    }
)
# Album / folder metadata — not per-media sidecars
SKIP_JSON_NAMES = frozenset({"metadata.json", "métadata.json"})

SQLITE_EXTS = frozenset({".db", ".sqlite", ".sqlite3"})

COLUMNS = [
    "relative_path",
    "media_type",
    "filename",
    "title",
    "file_ctime_utc",
    "file_mtime_utc",
    "photo_taken_ts",
    "photo_taken_utc",
    "creation_ts",
    "creation_utc",
    "modification_ts",
    "modification_utc",
    "google_unique_id",
    "google_url",
    "sidecar_path",
    "description",
    "latitude",
    "longitude",
    "image_views",
]


def _utc_iso_from_epoch(ts: float | int | None) -> str:
    if ts is None:
        return ""
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OSError, OverflowError, ValueError):
        return ""


def _file_ctime_mtime(path: Path) -> tuple[float, float]:
    st = path.stat()
    mtime = float(st.st_mtime)
    # Prefer birth time when available (macOS/BSD); on Windows st_ctime is creation.
    if hasattr(st, "st_birthtime"):
        ctime = float(st.st_birthtime)  # type: ignore[attr-defined]
    else:
        ctime = float(st.st_ctime)
    return ctime, mtime


def _media_type(ext: str) -> str:
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    return "other"


def _json_time_fields(block: Any) -> tuple[str, str]:
    """Return (timestamp_str, formatted_utc_iso) from a Takeout time object."""
    if not isinstance(block, dict):
        return "", ""
    raw = block.get("timestamp")
    if raw is None or raw == "":
        return "", ""
    ts_str = str(raw)
    try:
        iso = _utc_iso_from_epoch(int(ts_str))
    except ValueError:
        iso = ""
    return ts_str, iso


def _google_id_from_url(url: str) -> str:
    if not url:
        return ""
    # Common: https://photos.google.com/photo/AF1Qip...
    m = re.search(r"/photo/([^/?#]+)", url)
    if m:
        return m.group(1)
    # Fallback: last non-empty path segment if it looks like an ID
    path = urlparse(url).path.rstrip("/")
    if path:
        seg = path.split("/")[-1]
        if len(seg) >= 8 and seg not in ("photo", "photos", "lh3", "lh4"):
            return seg
    return ""


def _synthesize_id(photo_taken_ts: str, title: str, relative_path: str) -> str:
    base = photo_taken_ts or "0"
    name = title or Path(relative_path).name
    return f"{base}_{name}"


def _load_sidecar(path: Path) -> dict[str, Any] | None:
    try:
        # utf-8-sig tolerates BOM from some Windows editors / PowerShell Set-Content
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    # Album metadata.json uses albumData — skip
    if "albumData" in data and "photoTakenTime" not in data and "title" not in data:
        return None
    return data


def _candidate_sidecar_paths(media: Path) -> list[Path]:
    """
    Takeout sidecar naming varies by export vintage and OS path limits:
      photo.jpg.json
      photo.jpg.supplemental-metadata.json
      photo.supplemental-metadata.json
      photo(1).jpg.json  /  photo.jpg(1).json
    Also try truncated basename prefixes (Windows historically ~46 chars).
    """
    parent = media.parent
    name = media.name
    stem = media.stem
    suffix = media.suffix  # includes dot

    candidates: list[Path] = [
        parent / f"{name}.json",
        parent / f"{name}.supplemental-metadata.json",
        parent / f"{stem}.supplemental-metadata.json",
        parent / f"{stem}.json",
    ]

    # Duplicate suffix patterns: IMG.jpg(1).json vs IMG(1).jpg.json
    m = re.match(r"^(.*?)(\(\d+\))$", stem)
    if m:
        base_stem, num = m.group(1), m.group(2)
        candidates.extend(
            [
                parent / f"{base_stem}{suffix}{num}.json",
                parent / f"{base_stem}{suffix}.json",
                parent / f"{base_stem}{num}{suffix}.json",
            ]
        )

    # Truncated sidecar: same dir, *.json whose name starts like media name
    # Prefer exact matches first; truncation handled in find_sidecar via scan.
    return candidates


def find_sidecar(media: Path) -> Path | None:
    for cand in _candidate_sidecar_paths(media):
        if cand.is_file() and cand.name.lower() not in SKIP_JSON_NAMES:
            data = _load_sidecar(cand)
            if data is not None:
                return cand

    # Slow path: truncated / oddly named sidecars in the same folder.
    # Match if JSON title equals media name, or filename is a prefix of media+.json.
    parent = media.parent
    media_name_lower = media.name.lower()
    media_stem_lower = media.stem.lower()
    try:
        json_files = list(parent.glob("*.json"))
    except OSError:
        return None

    for jp in json_files:
        if jp.name.lower() in SKIP_JSON_NAMES:
            continue
        jn = jp.name.lower()
        if jn.startswith(media_name_lower) or jn.startswith(media_stem_lower):
            data = _load_sidecar(jp)
            if data is not None:
                return jp

    for jp in json_files:
        if jp.name.lower() in SKIP_JSON_NAMES:
            continue
        data = _load_sidecar(jp)
        if not data:
            continue
        title = str(data.get("title") or "")
        if title and title.lower() == media_name_lower:
            return jp
        # Title may be original name before Takeout rename
        if title and Path(title).stem.lower() == media_stem_lower:
            return jp

    return None


def row_for_media(
    path_root: Path,
    media: Path,
    verbose: bool = False,
) -> dict[str, str]:
    """Build one inventory row; paths are relative to path_root."""
    rel = media.relative_to(path_root).as_posix()
    ext = media.suffix.lower()
    ctime, mtime = _file_ctime_mtime(media)

    row: dict[str, str] = {
        "relative_path": rel,
        "media_type": _media_type(ext),
        "filename": media.name,
        "title": "",
        "file_ctime_utc": _utc_iso_from_epoch(ctime),
        "file_mtime_utc": _utc_iso_from_epoch(mtime),
        "photo_taken_ts": "",
        "photo_taken_utc": "",
        "creation_ts": "",
        "creation_utc": "",
        "modification_ts": "",
        "modification_utc": "",
        "google_unique_id": "",
        "google_url": "",
        "sidecar_path": "",
        "description": "",
        "latitude": "",
        "longitude": "",
        "image_views": "",
    }

    sidecar = find_sidecar(media)
    if sidecar is None:
        if verbose:
            print(f"No sidecar: {rel}", file=sys.stderr)
        row["google_unique_id"] = _synthesize_id("", media.name, rel)
        return row

    data = _load_sidecar(sidecar) or {}
    row["sidecar_path"] = sidecar.relative_to(path_root).as_posix()
    row["title"] = str(data.get("title") or "")
    row["description"] = str(data.get("description") or "")
    row["image_views"] = str(data.get("imageViews") or "")

    pt_ts, pt_utc = _json_time_fields(data.get("photoTakenTime"))
    cr_ts, cr_utc = _json_time_fields(data.get("creationTime"))
    mo_ts, mo_utc = _json_time_fields(data.get("modificationTime"))
    row["photo_taken_ts"] = pt_ts
    row["photo_taken_utc"] = pt_utc
    row["creation_ts"] = cr_ts
    row["creation_utc"] = cr_utc
    row["modification_ts"] = mo_ts
    row["modification_utc"] = mo_utc

    url = str(data.get("url") or "")
    row["google_url"] = url
    gid = _google_id_from_url(url)
    if not gid:
        gid = _synthesize_id(pt_ts or cr_ts, row["title"] or media.name, rel)
    row["google_unique_id"] = gid

    geo = data.get("geoData") or data.get("geoDataExif") or {}
    if isinstance(geo, dict):
        lat, lon = geo.get("latitude"), geo.get("longitude")
        # Takeout often uses 0.0 for "no location"
        if lat not in (None, 0, 0.0) or lon not in (None, 0, 0.0):
            if lat is not None:
                row["latitude"] = str(lat)
            if lon is not None:
                row["longitude"] = str(lon)

    return row


def scan_folder(root: Path) -> tuple[list[Path], dict[str, int], dict[str, int]]:
    """
    Walk root once. Return (media_files, category_counts, extension_counts).

    Categories: image, video, json, other. Extension keys are lowercase suffixes
    (e.g. '.jpg') or '(no extension)'.
    """
    media_files: list[Path] = []
    by_category: dict[str, int] = {"image": 0, "video": 0, "json": 0, "other": 0}
    by_ext: dict[str, int] = {}

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower() or "(no extension)"
        by_ext[ext] = by_ext.get(ext, 0) + 1

        if ext in IMAGE_EXT:
            by_category["image"] += 1
            media_files.append(p)
        elif ext in VIDEO_EXT:
            by_category["video"] += 1
            media_files.append(p)
        elif ext == ".json":
            by_category["json"] += 1
        else:
            by_category["other"] += 1

    media_files.sort(key=lambda x: x.as_posix().lower())
    return media_files, by_category, by_ext


def _print_folder_summary(
    folder: Path,
    by_category: dict[str, int],
    by_ext: dict[str, int],
    path_root: Path | None = None,
) -> None:
    total = sum(by_category.values())
    print(f"Folder: {folder}")
    if path_root is not None and path_root != folder:
        print(f"Path root: {path_root}")
    print(f"Total files: {total}")
    print(
        "By type: "
        f"image={by_category['image']}, "
        f"video={by_category['video']}, "
        f"json={by_category['json']}, "
        f"other={by_category['other']}"
    )
    parts = [f"{ext}={n}" for ext, n in sorted(by_ext.items(), key=lambda x: (-x[1], x[0]))]
    print("By extension: " + ", ".join(parts))


def collect_rows(
    path_root: Path,
    media_files: list[Path],
    verbose: bool = False,
) -> tuple[list[dict[str, str]], int]:
    rows: list[dict[str, str]] = []
    matched = 0
    for i, media in enumerate(media_files, 1):
        row = row_for_media(path_root, media, verbose=verbose)
        if row["sidecar_path"]:
            matched += 1
        rows.append(row)
        if verbose and i % 500 == 0:
            print(f"… {i}/{len(media_files)}", file=sys.stderr)
    return rows, matched


def write_csv(output: Path, rows: list[dict[str, str]]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_sqlite(output: Path, rows: list[dict[str, str]]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    col_defs = ", ".join(f"{c} TEXT" for c in COLUMNS)
    placeholders = ", ".join("?" for _ in COLUMNS)
    col_names = ", ".join(COLUMNS)

    conn = sqlite3.connect(str(output))
    try:
        conn.execute(
            f"CREATE TABLE media (\n"
            f"  id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
            f"  {col_defs}\n"
            f")"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_media_google_unique_id "
            "ON media (google_unique_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_media_relative_path "
            "ON media (relative_path)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_media_photo_taken_ts "
            "ON media (photo_taken_ts)"
        )
        conn.executemany(
            f"INSERT INTO media ({col_names}) VALUES ({placeholders})",
            [tuple(row.get(c, "") for c in COLUMNS) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()


def output_format(path: Path) -> str:
    """Return 'csv' or 'sqlite' based on file extension."""
    ext = path.suffix.lower()
    if ext == ".csv" or ext == "":
        return "csv"
    if ext in SQLITE_EXTS:
        return "sqlite"
    raise ValueError(
        f"Unsupported output extension {ext!r}; use .csv, .db, .sqlite, or .sqlite3"
    )


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{int(m)}m {s:.1f}s"
    h, m = divmod(int(m), 60)
    return f"{h}h {m}m {s:.0f}s"


def build_inventory(
    folder: Path,
    output: Path,
    path_root: Path | None = None,
    verbose: bool = False,
) -> int:
    """
    Scan folder for media; write inventory with paths relative to path_root
    (defaults to folder).
    """
    t0 = time.perf_counter()
    path_root = path_root or folder
    try:
        folder.relative_to(path_root)
    except ValueError:
        print(
            f"Error: -f folder must be inside -r root.\n"
            f"  folder: {folder}\n"
            f"  root:   {path_root}",
            file=sys.stderr,
        )
        return 1

    t_scan = time.perf_counter()
    media_files, by_category, by_ext = scan_folder(folder)
    scan_s = time.perf_counter() - t_scan
    _print_folder_summary(folder, by_category, by_ext, path_root=path_root)

    if not media_files:
        print(f"No media files found under {folder}", file=sys.stderr)
        print(f"Elapsed: {_format_elapsed(time.perf_counter() - t0)}")
        return 1

    try:
        fmt = output_format(output)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Default bare name → .csv
    if output.suffix == "":
        output = output.with_suffix(".csv")
        fmt = "csv"

    t_meta = time.perf_counter()
    rows, matched = collect_rows(path_root, media_files, verbose=verbose)
    meta_s = time.perf_counter() - t_meta

    t_write = time.perf_counter()
    if fmt == "csv":
        write_csv(output, rows)
    else:
        write_sqlite(output, rows)
    write_s = time.perf_counter() - t_write

    total_s = time.perf_counter() - t0
    print(
        f"Wrote {len(rows)} media row(s) to {output} "
        f"({matched} with sidecar metadata)."
    )
    print(
        f"Timing: scan={_format_elapsed(scan_s)}, "
        f"metadata={_format_elapsed(meta_s)}, "
        f"write={_format_elapsed(write_s)}, "
        f"total={_format_elapsed(total_s)}"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a CSV or SQLite inventory from a Google Photos Takeout folder.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python gpht2db.py -f "D:/Takeout/Google Photos" -o gpht_inventory.csv
  python gpht2db.py -f ./Takeout -o gpht.db
  python gpht2db.py -f ./Takeout -o out.sqlite -v

  # Scan one album; store paths relative to the Takeout root
  python gpht2db.py -f "G:/Takeout/Boston 8_4_24" -r "G:/Takeout" -o boston.db

Format is chosen by -o extension:
  .csv                     CSV
  .db / .sqlite / .sqlite3 SQLite (table: media)

Columns include relative_path, filesystem ctime/mtime, Google photoTakenTime /
creationTime / modificationTime, and google_unique_id (from Takeout URL when
present; otherwise synthesized from timestamp + title).

With -r, relative_path and sidecar_path are relative to that root; otherwise
they are relative to -f.
        """,
    )
    parser.add_argument(
        "-f",
        "--folder",
        required=True,
        metavar="DIR",
        help="Folder to scan recursively for media",
    )
    parser.add_argument(
        "-r",
        "--root",
        metavar="DIR",
        default=None,
        help="Path root for relative_path / sidecar_path (default: same as -f)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="gpht_inventory.csv",
        help="Output path: .csv or .db/.sqlite/.sqlite3 (default: gpht_inventory.csv)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose progress")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"Error: Not a directory: {args.folder}", file=sys.stderr)
        sys.exit(1)

    path_root = None
    if args.root is not None:
        path_root = Path(args.root)
        if not path_root.is_dir():
            print(f"Error: Not a directory: {args.root}", file=sys.stderr)
            sys.exit(1)
        path_root = path_root.resolve()

    code = build_inventory(
        folder.resolve(),
        Path(args.output),
        path_root=path_root,
        verbose=args.verbose,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
