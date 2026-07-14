"""
Process files listed in an inventory SQLite DB (from fdocs2db / gpht2db).

Filters rows by extension (-fex) and folder (-ffl), resolves paths via scan_meta
path_root (or -r), then runs a processing method (-m) on each match.

First method: doc2text — extract NLP JSON beside each file (same stem).

Run: python processdb.py -h
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

METHODS = ("doc2text", "pdfextract", "pdfocr")


def ocr_ext_path(pdf_path: Path) -> Path:
    """Searchable OCR sidecar: <stem>_ext.pdf next to the source PDF."""
    return pdf_path.parent / f"{pdf_path.stem}_ext.pdf"


def ensure_ocr_pdf(
    abs_path: Path,
    *,
    update: bool,
    verbose: bool,
) -> Path:
    """
    Ensure a searchable OCR PDF exists (<stem>_ext.pdf).
    Skips re-OCR when the sidecar already exists unless update=True.
    Raises RuntimeError on OCR failure.
    """
    dest = ocr_ext_path(abs_path)
    if dest.is_file() and not update:
        if verbose:
            print(f"  OCR sidecar exists: {dest.name}")
        return dest
    from pdfocr import run_ocr

    if verbose:
        print(f"  OCR -> {dest.name}")
    code = run_ocr(
        input_path=str(abs_path),
        output_path=str(dest),
        redo_ocr=update and dest.is_file(),
        force_ocr=False,
        progress_bar=verbose,
    )
    if code != 0 or not dest.is_file():
        raise RuntimeError(f"OCR failed for {abs_path.name} (exit {code})")
    return dest


def connect_ro(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def list_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()]


def resolve_table(conn: sqlite3.Connection, table: str | None) -> str:
    tables = [t for t in list_tables(conn) if t != "scan_meta"]
    if not tables:
        raise ValueError("Database has no inventory tables.")
    if table:
        if table not in list_tables(conn):
            raise ValueError(f"Table {table!r} not found. Available: {', '.join(list_tables(conn))}")
        return table
    if "files" in tables:
        return "files"
    if "media" in tables:
        return "media"
    if len(tables) == 1:
        return tables[0]
    raise ValueError(f"Multiple tables; pass -t/--table. Available: {', '.join(tables)}")


def read_scan_meta(conn: sqlite3.Connection) -> dict[str, str]:
    tables = list_tables(conn)
    if "scan_meta" not in tables:
        return {}
    rows = conn.execute("SELECT key, value FROM scan_meta").fetchall()
    return {r[0]: r[1] for r in rows}


def normalize_extensions(spec: str | None, default: frozenset[str] | None = None) -> set[str] | None:
    """
    Parse -fex into a set of lowercase extensions with leading dots.
    None / empty with default -> default; None without default -> no filter.
    """
    if spec is None or not str(spec).strip():
        return set(default) if default is not None else None
    parts = [p.strip() for p in spec.replace(";", ",").replace(" ", ",").split(",") if p.strip()]
    out: set[str] = set()
    for p in parts:
        e = p.lower()
        if not e.startswith("."):
            e = "." + e
        out.add(e)
    return out


def normalize_folder_filter(spec: str | None) -> str | None:
    if spec is None or not str(spec).strip():
        return None
    # POSIX-style relative prefix, no leading ./ 
    s = spec.strip().replace("\\", "/").strip("/")
    return s or None


def extension_of_row(row: sqlite3.Row, cols: list[str]) -> str:
    if "extension" in cols:
        ext = str(row["extension"] or "").lower()
        if ext and ext != "(none)":
            return ext if ext.startswith(".") else f".{ext}"
        if ext == "(none)":
            return ""
    rel = str(row["relative_path"] or "")
    return Path(rel).suffix.lower()


def folder_matches(relative_path: str, folder_filter: str | None) -> bool:
    if not folder_filter:
        return True
    rel = relative_path.replace("\\", "/").lstrip("/")
    fl = folder_filter
    if rel == fl or rel.startswith(fl + "/"):
        return True
    # Also allow matching a path segment anywhere (e.g. -ffl Contracts)
    parts = rel.split("/")
    if fl in parts:
        return True
    # Prefix match on any parent path
    for i in range(len(parts)):
        prefix = "/".join(parts[: i + 1])
        if prefix == fl or prefix.startswith(fl + "/"):
            return True
    return fl in rel


def select_rows(
    conn: sqlite3.Connection,
    table: str,
    extensions: set[str] | None,
    folder_filter: str | None,
    limit: int | None,
) -> list[sqlite3.Row]:
    cols = list_columns(conn, table)
    if "relative_path" not in cols:
        raise ValueError(f"Table {table!r} has no relative_path column.")

    # Prefer SQL filter when extension column exists
    sql = f"SELECT * FROM {qident(table)}"
    params: list = []
    clauses: list[str] = []
    if extensions is not None and "extension" in cols:
        # Match both .pdf and pdf if stored inconsistently
        placeholders = ",".join("?" for _ in extensions)
        # Also allow without dot variants in DB
        variants = set(extensions)
        for e in list(extensions):
            variants.add(e.lstrip("."))
            variants.add(e if e.startswith(".") else f".{e}")
        placeholders = ",".join("?" for _ in variants)
        clauses.append(f"lower(extension) IN ({placeholders})")
        params.extend(sorted(v.lower() for v in variants))

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY relative_path"

    rows = conn.execute(sql, params).fetchall()
    matched: list[sqlite3.Row] = []
    for row in rows:
        rel = str(row["relative_path"] or "")
        if not folder_matches(rel, folder_filter):
            continue
        if extensions is not None:
            ext = extension_of_row(row, cols)
            if ext not in extensions:
                # allow missing-dot compare
                if f".{ext.lstrip('.')}" not in extensions and ext not in {
                    e.lstrip(".") for e in extensions
                }:
                    continue
        matched.append(row)
        if limit is not None and len(matched) >= limit:
            break
    return matched


def resolve_path_root(
    meta: dict[str, str],
    root_arg: str | None,
) -> Path:
    if root_arg:
        p = Path(root_arg)
        if not p.is_dir():
            raise FileNotFoundError(f"Path root not a directory: {root_arg}")
        return p.resolve()
    for key in ("path_root", "folder"):
        if key in meta and meta[key]:
            p = Path(meta[key])
            if p.is_dir():
                return p.resolve()
    raise ValueError(
        "Cannot resolve file paths: pass -r/--root, or ensure scan_meta has path_root/folder."
    )


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{int(m)}m {s:.1f}s"
    h, m = divmod(int(m), 60)
    return f"{h}h {m}m {s:.0f}s"


def method_doc2text(
    abs_path: Path,
    *,
    skip_existing: bool,
    allow_empty: bool,
    ocr: bool,
    update: bool,
    verbose: bool,
) -> str:
    """Returns status: ok | skip | missing | no_text | error:..."""
    from doc2text import SUPPORTED, NoTextLayerError, extract_to_json

    if abs_path.suffix.lower() not in SUPPORTED:
        return f"skip: unsupported extension {abs_path.suffix}"
    if not abs_path.is_file():
        return "missing"
    dest = abs_path.with_suffix(".json")
    if skip_existing and dest.is_file():
        return "skip"

    source = abs_path
    if abs_path.suffix.lower() == ".pdf":
        sidecar = ocr_ext_path(abs_path)
        if sidecar.is_file() and not (ocr and update):
            source = sidecar

    try:
        out = extract_to_json(source, output_path=dest, allow_empty=allow_empty)
        if verbose:
            print(f"  -> {out}")
        return "ok"
    except NoTextLayerError as e:
        if ocr and abs_path.suffix.lower() == ".pdf":
            try:
                source = ensure_ocr_pdf(abs_path, update=True, verbose=verbose)
                out = extract_to_json(source, output_path=dest, allow_empty=allow_empty)
                if verbose:
                    print(f"  -> {out}")
                return "ok"
            except NoTextLayerError as e2:
                return f"no_text: {e2}"
            except Exception as e2:
                return f"error: {e2}"
        return f"no_text: {e}"
    except Exception as e:
        return f"error: {e}"


def method_pdfextract(
    abs_path: Path,
    *,
    allow_empty: bool,
    update: bool,
    ocr: bool,
    verbose: bool,
) -> str:
    """
    Create same-stem .json next to PDFs.
    By default skips PDFs that already have a JSON pair; -u overwrites.
    With --ocr, image-only PDFs get OCR'd to <stem>_ext.pdf then extracted.
    """
    if abs_path.suffix.lower() != ".pdf":
        return f"skip: not a pdf ({abs_path.suffix})"
    if not abs_path.is_file():
        return "missing"
    dest = abs_path.with_suffix(".json")
    if dest.is_file() and not update:
        return "skip"  # already has JSON pair
    from doc2text import NoTextLayerError, extract_to_json

    source = abs_path
    sidecar = ocr_ext_path(abs_path)
    if sidecar.is_file() and not (ocr and update):
        source = sidecar

    try:
        out = extract_to_json(source, output_path=dest, allow_empty=allow_empty)
        if verbose:
            print(f"  -> {out}")
        return "ok"
    except NoTextLayerError as e:
        if ocr:
            try:
                source = ensure_ocr_pdf(abs_path, update=True, verbose=verbose)
                out = extract_to_json(source, output_path=dest, allow_empty=allow_empty)
                if verbose:
                    print(f"  -> {out}")
                return "ok"
            except NoTextLayerError as e2:
                return f"no_text: {e2}"
            except Exception as e2:
                return f"error: {e2}"
        return f"no_text: {e}"
    except Exception as e:
        return f"error: {e}"


def method_pdfocr(
    abs_path: Path,
    *,
    update: bool,
    verbose: bool,
) -> str:
    """OCR PDF to sibling <stem>_ext.pdf. Skip existing sidecar unless -u."""
    if abs_path.suffix.lower() != ".pdf":
        return f"skip: not a pdf ({abs_path.suffix})"
    if not abs_path.is_file():
        return "missing"
    dest = ocr_ext_path(abs_path)
    if dest.is_file() and not update:
        return "skip"
    try:
        out = ensure_ocr_pdf(abs_path, update=update, verbose=verbose)
        if verbose:
            print(f"  -> {out}")
        return "ok"
    except Exception as e:
        return f"error: {e}"


def filter_missing_json_pairs(
    rows: list,
    root: Path,
) -> list:
    """Keep only rows whose on-disk file has no sibling .json."""
    out = []
    for row in rows:
        rel = str(row["relative_path"] or "").replace("\\", "/")
        abs_path = (root / rel).resolve()
        if not abs_path.with_suffix(".json").is_file():
            out.append(row)
    return out


def run_process(
    db_path: Path,
    method: str,
    *,
    table: str | None,
    path_root: str | None,
    fex: str | None,
    ffl: str | None,
    limit: int | None,
    skip_existing: bool,
    allow_empty: bool,
    update: bool,
    ocr: bool,
    verbose: bool,
) -> int:
    t0 = time.perf_counter()
    conn = connect_ro(db_path)
    try:
        tbl = resolve_table(conn, table)
        meta = read_scan_meta(conn)
        root = resolve_path_root(meta, path_root)

        if method == "doc2text":
            from doc2text import SUPPORTED

            extensions = normalize_extensions(fex, default=SUPPORTED)
        elif method in ("pdfextract", "pdfocr"):
            extensions = normalize_extensions(fex, default=frozenset({".pdf"}))
        else:
            extensions = normalize_extensions(fex, default=None)

        folder_filter = normalize_folder_filter(ffl)
        # For pdfextract without -u, fetch all PDF matches then drop ones that already have .json
        select_limit = None if method == "pdfextract" else limit
        rows = select_rows(conn, tbl, extensions, folder_filter, select_limit)
    finally:
        conn.close()

    # pdfextract: only PDFs missing a .json pair unless -u/--update
    already_paired = 0
    if method == "pdfextract" and not update:
        before = len(rows)
        rows = filter_missing_json_pairs(rows, root)
        already_paired = before - len(rows)
        if limit is not None:
            rows = rows[:limit]
    elif method == "pdfextract" and limit is not None:
        rows = rows[:limit]

    print(f"Database: {db_path}")
    print(f"Table:    {tbl}")
    print(f"Root:     {root}")
    print(f"Method:   {method}")
    if update:
        print("Update:   overwrite existing outputs (-u)")
    if ocr and method in ("doc2text", "pdfextract"):
        print("OCR:      enabled (--ocr) for image-only PDFs")
    if extensions is not None:
        print(f"Filter -fex: {', '.join(sorted(extensions))}")
    if folder_filter:
        print(f"Filter -ffl: {folder_filter}")
    if method == "pdfextract" and already_paired:
        print(f"Already have JSON pair: {already_paired} (skipped)")
    print(f"Matched:  {len(rows)} row(s)")

    if not rows:
        print("Nothing to process.")
        return 0

    # -u means overwrite; ignore --skip-existing
    effective_skip = False if update else skip_existing

    counts = {"ok": 0, "skip": 0, "missing": 0, "no_text": 0, "error": 0}
    for i, row in enumerate(rows, 1):
        rel = str(row["relative_path"] or "").replace("\\", "/")
        abs_path = (root / rel).resolve()
        print(f"[{i}/{len(rows)}] {rel}")

        if method == "doc2text":
            status = method_doc2text(
                abs_path,
                skip_existing=effective_skip,
                allow_empty=allow_empty,
                ocr=ocr,
                update=update,
                verbose=verbose,
            )
        elif method == "pdfextract":
            status = method_pdfextract(
                abs_path,
                allow_empty=allow_empty,
                update=update,
                ocr=ocr,
                verbose=verbose,
            )
        elif method == "pdfocr":
            status = method_pdfocr(
                abs_path,
                update=update,
                verbose=verbose,
            )
        else:
            status = f"error: unknown method {method}"

        if status == "ok":
            counts["ok"] += 1
        elif status == "skip" or status.startswith("skip:"):
            counts["skip"] += 1
            if verbose:
                print(f"  {status}")
        elif status == "missing":
            counts["missing"] += 1
            print(f"  missing: {abs_path}", file=sys.stderr)
        elif status.startswith("no_text"):
            counts["no_text"] += 1
            print(f"  {status}", file=sys.stderr)
        else:
            counts["error"] += 1
            print(f"  {status}", file=sys.stderr)

    print(
        f"Done: ok={counts['ok']}, skip={counts['skip']}, "
        f"missing={counts['missing']}, no_text={counts['no_text']}, "
        f"error={counts['error']}, "
        f"elapsed={_format_elapsed(time.perf_counter() - t0)}"
    )
    return 0 if counts["error"] == 0 and counts["missing"] == 0 and counts["no_text"] == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process inventory DB rows with a method (filters: extension, folder).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python processdb.py -d testdocs/fdocs.db -m doc2text
  python processdb.py -d testdocs/fdocs.db -m doc2text -fex pdf,docx -ffl 2021/Contracts
  python processdb.py -d testdocs/fdocs.db -m pdfextract
  python processdb.py -d testdocs/fdocs.db -m pdfextract --ocr -u -ffl Contracts -v
  python processdb.py -d testdocs/fdocs.db -m pdfocr -ffl Contracts -v

Methods:
  doc2text    Extract text JSON beside each file (pdf/docx/doc; see doc2text.py)
  pdfextract  Create .json next to PDFs missing a JSON pair (-u overwrites; --ocr for scans)
  pdfocr      Create searchable <stem>_ext.pdf via OCR (-u re-OCRs)

Path root comes from scan_meta.path_root (fdocs2db) unless -r is set.
        """,
    )
    parser.add_argument("-d", "--database", required=True, metavar="FILE", help="SQLite inventory DB")
    parser.add_argument(
        "-m",
        "--method",
        required=True,
        choices=METHODS,
        help="Processing method",
    )
    parser.add_argument(
        "-fex",
        "--file-extension",
        default=None,
        metavar="EXTS",
        help="Extension filter (default: doc2text=pdf,docx,doc; pdfextract/pdfocr=pdf)",
    )
    parser.add_argument(
        "-ffl",
        "--folder-filter",
        default=None,
        metavar="PATH",
        help="Folder filter: relative path prefix or segment (e.g. 2021/Contracts)",
    )
    parser.add_argument(
        "-r",
        "--root",
        default=None,
        metavar="DIR",
        help="Filesystem root for relative_path (default: scan_meta path_root/folder)",
    )
    parser.add_argument(
        "-t",
        "--table",
        default=None,
        help="Inventory table (default: files, else media, else only table)",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Process at most N matching rows (0 = all)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="For doc2text: skip if .json already exists (ignored with -u)",
    )
    parser.add_argument(
        "-u",
        "--update",
        action="store_true",
        help="Overwrite existing JSON / OCR sidecars",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="For pdfextract/doc2text: OCR image-only PDFs to <stem>_ext.pdf then extract",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="For doc2text/pdfextract: write JSON even when PDF has no text layer",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    limit = None if args.limit == 0 else max(0, args.limit)
    try:
        code = run_process(
            Path(args.database),
            args.method,
            table=args.table,
            path_root=args.root,
            fex=args.file_extension,
            ffl=args.folder_filter,
            limit=limit,
            skip_existing=args.skip_existing,
            allow_empty=args.allow_empty,
            update=args.update,
            ocr=args.ocr,
            verbose=args.verbose,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except sqlite3.Error as e:
        print(f"Error querying database: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
