"""
Inventory all files under a folder into CSV or SQLite (document-organization workflow).

First step: capture every file's relative path and basic filesystem metadata.
Later scripts can classify files and add stats against this DB.

Output format by -o extension: .csv -> CSV; .db / .sqlite / .sqlite3 -> SQLite.

Run: python fdocs2db.py -h
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SQLITE_EXTS = frozenset({".db", ".sqlite", ".sqlite3"})

# Inventory columns only (no Google/Takeout fields). Classification can ALTER later.
COLUMNS = [
    "relative_path",
    "extension",
    "size_bytes",
    "file_ctime_utc",
    "file_mtime_utc",
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
    if hasattr(st, "st_birthtime"):
        ctime = float(st.st_birthtime)  # type: ignore[attr-defined]
    else:
        ctime = float(st.st_ctime)
    return ctime, mtime


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{int(m)}m {s:.1f}s"
    h, m = divmod(int(m), 60)
    return f"{h}h {m}m {s:.0f}s"


def _format_bytes(n: int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if x < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(x)} {unit}"
            return f"{x:.1f} {unit}"
        x /= 1024
    return f"{n} B"


def row_for_file(path_root: Path, path: Path) -> dict[str, str]:
    rel = path.relative_to(path_root).as_posix()
    ext = path.suffix.lower()
    try:
        size = path.stat().st_size
        ctime, mtime = _file_ctime_mtime(path)
    except OSError:
        size = 0
        ctime, mtime = 0.0, 0.0

    return {
        "relative_path": rel,
        "extension": ext or "(none)",
        "size_bytes": str(size),
        "file_ctime_utc": _utc_iso_from_epoch(ctime) if ctime else "",
        "file_mtime_utc": _utc_iso_from_epoch(mtime) if mtime else "",
    }


def scan_folder(folder: Path) -> tuple[list[Path], dict[str, int], int]:
    """Return (files, extension_counts, total_bytes)."""
    files: list[Path] = []
    by_ext: dict[str, int] = {}
    total_bytes = 0
    for p in folder.rglob("*"):
        if not p.is_file():
            continue
        files.append(p)
        ext = p.suffix.lower() or "(none)"
        by_ext[ext] = by_ext.get(ext, 0) + 1
        try:
            total_bytes += p.stat().st_size
        except OSError:
            pass
    files.sort(key=lambda x: x.as_posix().lower())
    return files, by_ext, total_bytes


def _print_summary(
    folder: Path,
    by_ext: dict[str, int],
    total_bytes: int,
    path_root: Path | None = None,
) -> None:
    total = sum(by_ext.values())
    print(f"Folder: {folder}")
    if path_root is not None and path_root != folder:
        print(f"Path root: {path_root}")
    print(f"Total files: {total}")
    print(f"Total size:  {_format_bytes(total_bytes)}")
    parts = [f"{ext}={n}" for ext, n in sorted(by_ext.items(), key=lambda x: (-x[1], x[0]))]
    # Cap very long extension lists in the console summary
    if len(parts) > 40:
        shown = parts[:40]
        print("By extension: " + ", ".join(shown) + f", ... (+{len(parts) - 40} more)")
    else:
        print("By extension: " + ", ".join(parts))


def collect_rows(
    path_root: Path,
    files: list[Path],
    verbose: bool = False,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for i, path in enumerate(files, 1):
        rows.append(row_for_file(path_root, path))
        if verbose and i % 1000 == 0:
            print(f"... {i}/{len(files)}", file=sys.stderr)
    return rows


def write_csv(output: Path, rows: list[dict[str, str]]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_sqlite(
    output: Path,
    rows: list[dict[str, str]],
    *,
    folder: Path,
    path_root: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    col_defs = ", ".join(
        f"{c} INTEGER" if c == "size_bytes" else f"{c} TEXT" for c in COLUMNS
    )
    placeholders = ", ".join("?" for _ in COLUMNS)
    col_names = ", ".join(COLUMNS)

    def _coerce(col: str, val: str):
        if col == "size_bytes":
            try:
                return int(val) if val != "" else 0
            except ValueError:
                return 0
        return val

    conn = sqlite3.connect(str(output))
    try:
        conn.execute(
            "CREATE TABLE scan_meta (\n"
            "  key TEXT PRIMARY KEY,\n"
            "  value TEXT\n"
            ")"
        )
        meta = {
            "folder": str(folder),
            "path_root": str(path_root),
            "scanned_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "file_count": str(len(rows)),
            "schema_version": "2",
        }
        conn.executemany(
            "INSERT INTO scan_meta (key, value) VALUES (?, ?)",
            list(meta.items()),
        )

        conn.execute(
            f"CREATE TABLE files (\n"
            f"  id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
            f"  {col_defs}\n"
            f")"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_files_relative_path "
            "ON files (relative_path)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_files_extension ON files (extension)"
        )
        conn.executemany(
            f"INSERT INTO files ({col_names}) VALUES ({placeholders})",
            [tuple(_coerce(c, row.get(c, "")) for c in COLUMNS) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()


def output_format(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".csv" or ext == "":
        return "csv"
    if ext in SQLITE_EXTS:
        return "sqlite"
    raise ValueError(
        f"Unsupported output extension {ext!r}; use .csv, .db, .sqlite, or .sqlite3"
    )


def build_inventory(
    folder: Path,
    output: Path,
    path_root: Path | None = None,
    verbose: bool = False,
) -> int:
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
    files, by_ext, total_bytes = scan_folder(folder)
    scan_s = time.perf_counter() - t_scan
    _print_summary(folder, by_ext, total_bytes, path_root=path_root)

    if not files:
        print(f"No files found under {folder}", file=sys.stderr)
        print(f"Elapsed: {_format_elapsed(time.perf_counter() - t0)}")
        return 1

    try:
        fmt = output_format(output)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if output.suffix == "":
        output = output.with_suffix(".db")
        fmt = "sqlite"

    t_rows = time.perf_counter()
    rows = collect_rows(path_root, files, verbose=verbose)
    rows_s = time.perf_counter() - t_rows

    t_write = time.perf_counter()
    if fmt == "csv":
        write_csv(output, rows)
    else:
        write_sqlite(output, rows, folder=folder, path_root=path_root)
    write_s = time.perf_counter() - t_write

    total_s = time.perf_counter() - t0
    print(f"Wrote {len(rows)} file row(s) to {output}.")
    print(
        f"Timing: scan={_format_elapsed(scan_s)}, "
        f"rows={_format_elapsed(rows_s)}, "
        f"write={_format_elapsed(write_s)}, "
        f"total={_format_elapsed(total_s)}"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create a CSV or SQLite inventory of all files under a folder "
            "(first step of a document-organization workflow)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fdocs2db.py -f "G:/Docs/archive" -o testdocs/fdocs.db
  python fdocs2db.py -f ./inbox -o inbox.csv -v

  # Scan a subfolder; store paths relative to a parent root
  python fdocs2db.py -f "G:/Docs/2021" -r "G:/Docs" -o docs_2021.db

SQLite tables:
  files      relative_path, extension, size_bytes, file_ctime_utc, file_mtime_utc
  scan_meta  folder, path_root, scanned_at_utc, file_count

Classification / stats scripts can join or ALTER this DB later.
        """,
    )
    parser.add_argument(
        "-f",
        "--folder",
        required=True,
        metavar="DIR",
        help="Folder to scan recursively for all files",
    )
    parser.add_argument(
        "-r",
        "--root",
        metavar="DIR",
        default=None,
        help="Path root for relative_path (default: same as -f)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="fdocs.db",
        help="Output path: .db/.sqlite/.sqlite3 or .csv (default: fdocs.db)",
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
