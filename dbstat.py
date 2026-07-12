"""
Common summaries for SQLite databases (e.g. gpht2db output).

Uses Python's sqlite3 (stdlib) — no sqlite3 CLI install required.

Run: python dbstat.py -h
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


SUMMARIES = ("dup", "dup2")


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_tables(conn: sqlite3.Connection, schema: str = "main") -> list[str]:
    rows = conn.execute(
        f"SELECT name FROM {qident(schema)}.sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def list_columns(conn: sqlite3.Connection, table: str, schema: str = "main") -> list[str]:
    rows = conn.execute(f'PRAGMA {qident(schema)}.table_info("{table}")').fetchall()
    return [r[1] for r in rows]


def resolve_table(
    conn: sqlite3.Connection,
    table: str | None,
    schema: str = "main",
    label: str = "database",
) -> str:
    tables = list_tables(conn, schema=schema)
    if not tables:
        raise ValueError(f"{label} has no user tables.")
    if table:
        if table not in tables:
            raise ValueError(
                f"Table {table!r} not found in {label}. Available: {', '.join(tables)}"
            )
        return table
    if len(tables) == 1:
        return tables[0]
    raise ValueError(
        f"Multiple tables in {label}; pass -t/--table"
        f"{' or -t2' if schema != 'main' else ''}. "
        f"Available: {', '.join(tables)}"
    )


def qident(name: str) -> str:
    """Quote a validated SQL identifier."""
    return '"' + name.replace('"', '""') + '"'


def _path_column(cols: list[str]) -> str | None:
    for candidate in ("relative_path", "filename", "title"):
        if candidate in cols:
            return candidate
    return None


def _truncate(val: object, width: int = 80) -> str:
    s = str(val)
    return s if len(s) <= width else s[: width - 3] + "..."


def summary_dup(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    limit: int | None,
    show_examples: int,
) -> int:
    cols = list_columns(conn, table)
    if column not in cols:
        print(
            f"Error: Column {column!r} not in {table}. "
            f"Available: {', '.join(cols)}",
            file=sys.stderr,
        )
        return 1

    t = qident(table)
    c = qident(column)

    total = conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
    non_null = conn.execute(
        f"SELECT COUNT(*) AS n FROM {t} WHERE {c} IS NOT NULL AND {c} != ''"
    ).fetchone()["n"]
    nullish = total - non_null
    distinct = conn.execute(
        f"SELECT COUNT(DISTINCT {c}) AS n FROM {t} "
        f"WHERE {c} IS NOT NULL AND {c} != ''"
    ).fetchone()["n"]

    dup_sql = (
        f"SELECT {c} AS value, COUNT(*) AS cnt FROM {t} "
        f"WHERE {c} IS NOT NULL AND {c} != '' "
        f"GROUP BY {c} HAVING COUNT(*) > 1 "
        f"ORDER BY cnt DESC, value"
    )
    dup_groups = conn.execute(dup_sql).fetchall()
    dup_group_count = len(dup_groups)
    dup_row_count = sum(r["cnt"] for r in dup_groups)
    extra_rows = dup_row_count - dup_group_count

    print(f"Database summary: dup")
    print(f"  table:           {table}")
    print(f"  column:          {column}")
    print(f"  total rows:      {total}")
    print(f"  non-empty:       {non_null}")
    print(f"  null/empty:      {nullish}")
    print(f"  distinct values: {distinct}")
    print(f"  duplicate groups:{dup_group_count}")
    print(f"  rows in groups:  {dup_row_count}")
    print(f"  extra rows:      {extra_rows}  (rows_in_groups - groups)")
    print(f"  check:           distinct + extra = {distinct + extra_rows} (should equal total if no null/empty)")

    if dup_group_count == 0:
        print("No duplicate values.")
        return 0

    shown = dup_groups if limit is None else dup_groups[:limit]
    print()
    print(f"Top duplicate values (showing {len(shown)} of {dup_group_count}):")
    print(f"{'count':>8}  value")
    print(f"{'-----':>8}  -----")
    for r in shown:
        print(f"{r['cnt']:>8}  {_truncate(r['value'])}")

    if show_examples > 0 and shown:
        path_col = _path_column(cols)
        print()
        print(f"Examples (up to {show_examples} row(s) per value):")
        for r in shown[: min(10, len(shown))]:
            val = r["value"]
            print(f"  [{r['cnt']}x] {val}")
            if path_col:
                ex_sql = (
                    f"SELECT {qident(path_col)} AS path FROM {t} "
                    f"WHERE {c} = ? LIMIT ?"
                )
                for ex in conn.execute(ex_sql, (val, show_examples)):
                    print(f"      - {ex['path']}")

    if limit is not None and dup_group_count > limit:
        print()
        print(f"(Use -n 0 to show all {dup_group_count} groups.)")

    return 0


def summary_dup2(
    conn: sqlite3.Connection,
    db1_label: str,
    db2_label: str,
    table1: str,
    table2: str,
    column: str,
    limit: int | None,
    show_examples: int,
) -> int:
    """Report values of column present in both databases."""
    cols1 = list_columns(conn, table1, schema="main")
    cols2 = list_columns(conn, table2, schema="db2")
    if column not in cols1:
        print(
            f"Error: Column {column!r} not in {db1_label}.{table1}. "
            f"Available: {', '.join(cols1)}",
            file=sys.stderr,
        )
        return 1
    if column not in cols2:
        print(
            f"Error: Column {column!r} not in {db2_label}.{table2}. "
            f"Available: {', '.join(cols2)}",
            file=sys.stderr,
        )
        return 1

    t1 = f"main.{qident(table1)}"
    t2 = f"db2.{qident(table2)}"
    c = qident(column)

    def _stats(table_ref: str) -> tuple[int, int]:
        total = conn.execute(f"SELECT COUNT(*) AS n FROM {table_ref}").fetchone()["n"]
        distinct = conn.execute(
            f"SELECT COUNT(DISTINCT {c}) AS n FROM {table_ref} "
            f"WHERE {c} IS NOT NULL AND {c} != ''"
        ).fetchone()["n"]
        return total, distinct

    total1, distinct1 = _stats(t1)
    total2, distinct2 = _stats(t2)

    overlap_sql = (
        f"SELECT a.value AS value, a.cnt AS cnt1, b.cnt AS cnt2 "
        f"FROM ("
        f"  SELECT {c} AS value, COUNT(*) AS cnt FROM {t1} "
        f"  WHERE {c} IS NOT NULL AND {c} != '' GROUP BY {c}"
        f") AS a "
        f"INNER JOIN ("
        f"  SELECT {c} AS value, COUNT(*) AS cnt FROM {t2} "
        f"  WHERE {c} IS NOT NULL AND {c} != '' GROUP BY {c}"
        f") AS b ON a.value = b.value "
        f"ORDER BY (a.cnt + b.cnt) DESC, a.value"
    )
    overlap = conn.execute(overlap_sql).fetchall()
    overlap_n = len(overlap)
    only1 = distinct1 - overlap_n
    only2 = distinct2 - overlap_n

    print(f"Database summary: dup2 (values of column present in both DBs)")
    print(f"  column:          {column}")
    print(f"  db1:             {db1_label}")
    print(f"    table:         {table1}")
    print(f"    total rows:    {total1}")
    print(f"    distinct:      {distinct1}")
    print(f"  db2:             {db2_label}")
    print(f"    table:         {table2}")
    print(f"    total rows:    {total2}")
    print(f"    distinct:      {distinct2}")
    print(f"  overlap values:  {overlap_n}")
    print(f"  only in db1:     {only1}")
    print(f"  only in db2:     {only2}")

    if overlap_n == 0:
        print("No shared values between databases.")
        return 0

    shown = overlap if limit is None else overlap[:limit]
    print()
    print(f"Shared values (showing {len(shown)} of {overlap_n}):")
    print(f"{'db1':>8} {'db2':>8}  value")
    print(f"{'---':>8} {'---':>8}  -----")
    for r in shown:
        print(f"{r['cnt1']:>8} {r['cnt2']:>8}  {_truncate(r['value'])}")

    if show_examples > 0 and shown:
        path1 = _path_column(cols1)
        path2 = _path_column(cols2)
        print()
        print(f"Examples (up to {show_examples} path(s) per DB per value):")
        for r in shown[: min(10, len(shown))]:
            val = r["value"]
            print(f"  [{r['cnt1']}+{r['cnt2']}x] {val}")
            if path1:
                ex_sql = (
                    f"SELECT {qident(path1)} AS path FROM {t1} "
                    f"WHERE {c} = ? LIMIT ?"
                )
                for ex in conn.execute(ex_sql, (val, show_examples)):
                    print(f"      db1: {ex['path']}")
            if path2:
                ex_sql = (
                    f"SELECT {qident(path2)} AS path FROM {t2} "
                    f"WHERE {c} = ? LIMIT ?"
                )
                for ex in conn.execute(ex_sql, (val, show_examples)):
                    print(f"      db2: {ex['path']}")

    if limit is not None and overlap_n > limit:
        print()
        print(f"(Use -n 0 to show all {overlap_n} shared values.)")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summaries for SQLite databases (duplicates, and more later).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python dbstat.py -d testdocs/gpht_all.db -s dup -c google_unique_id
  python dbstat.py -d testdocs/gpht_all.db -s dup -c google_unique_id -t media -n 20

  # Values of -c present in both databases
  python dbstat.py -d album.db -d2 all.db -s dup2 -c google_unique_id
  python dbstat.py -d a.db -d2 b.db -s dup2 -c google_unique_id -t media -t2 media -n 20

Uses Python sqlite3 (no external sqlite CLI). Databases are opened read-only.
        """,
    )
    parser.add_argument(
        "-d",
        "--database",
        required=True,
        metavar="FILE",
        help="SQLite database path (primary)",
    )
    parser.add_argument(
        "-d2",
        "--database2",
        default=None,
        metavar="FILE",
        help="Second SQLite database (required for -s dup2)",
    )
    parser.add_argument(
        "-s",
        "--summary",
        required=True,
        choices=SUMMARIES,
        help="Summary type: dup (within DB), dup2 (shared values across two DBs)",
    )
    parser.add_argument(
        "-c",
        "--column",
        default=None,
        help="Column name (required for dup / dup2)",
    )
    parser.add_argument(
        "-t",
        "--table",
        default=None,
        help="Table in -d (default: only table, or required if several)",
    )
    parser.add_argument(
        "-t2",
        "--table2",
        default=None,
        help="Table in -d2 (default: same as -t, else only table in -d2)",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=50,
        metavar="N",
        help="Max groups/values to list (default: 50; 0 = all)",
    )
    parser.add_argument(
        "-e",
        "--examples",
        type=int,
        default=3,
        metavar="N",
        help="Example row paths per value (default: 3; 0 = none)",
    )
    args = parser.parse_args()

    if args.summary in ("dup", "dup2") and not args.column:
        parser.error(f"-s {args.summary} requires -c/--column")
    if args.summary == "dup2" and not args.database2:
        parser.error("-s dup2 requires -d2/--database2")

    db_path = Path(args.database)
    try:
        conn = connect(db_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except sqlite3.Error as e:
        print(f"Error opening database: {e}", file=sys.stderr)
        sys.exit(1)

    limit = None if args.limit == 0 else max(0, args.limit)
    code = 1
    try:
        if args.summary == "dup":
            table = resolve_table(conn, args.table, label=str(db_path))
            code = summary_dup(
                conn,
                table,
                args.column,
                limit=limit,
                show_examples=max(0, args.examples),
            )
        elif args.summary == "dup2":
            db2_path = Path(args.database2)
            if not db2_path.is_file():
                print(f"Error: Database not found: {db2_path}", file=sys.stderr)
                sys.exit(1)
            # ATTACH second DB read-only for a single join query
            attach = db2_path.resolve().as_posix().replace("'", "''")
            conn.execute(f"ATTACH DATABASE 'file:{attach}?mode=ro' AS db2")
            table1 = resolve_table(conn, args.table, schema="main", label=str(db_path))
            table2_arg = args.table2 if args.table2 is not None else args.table
            table2 = resolve_table(
                conn, table2_arg, schema="db2", label=str(db2_path)
            )
            code = summary_dup2(
                conn,
                db1_label=str(db_path),
                db2_label=str(db2_path),
                table1=table1,
                table2=table2,
                column=args.column,
                limit=limit,
                show_examples=max(0, args.examples),
            )
        else:
            print(f"Error: Unknown summary {args.summary!r}", file=sys.stderr)
            code = 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        code = 1
    except sqlite3.Error as e:
        print(f"Error querying database: {e}", file=sys.stderr)
        code = 1
    finally:
        try:
            conn.execute("DETACH DATABASE db2")
        except sqlite3.Error:
            pass
        conn.close()

    sys.exit(code)


if __name__ == "__main__":
    main()
