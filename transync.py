"""
Bank transaction sync: append new CSV exports into a history CSV without duplicates.

Config-driven (YAML). ``banks`` is a dictionary of profiles; each append file's name
is matched with ``fnmatch`` against that profile's ``glob`` to select column maps /
constants / format. Formats differ by bank (e.g. Bank of America preamble).

Run: python transync.py -h
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class BankProfile:
    """One bank/export profile selected by filename glob."""

    key: str
    glob: str
    # history_column -> source_column (empty / omitted = leave blank unless constants)
    column_map: dict[str, str] = field(default_factory=dict)
    # Fixed values written into history columns (after column_map)
    constants: dict[str, str] = field(default_factory=dict)
    # Reader / normalizer: generic | bofa
    format: str = "generic"
    encoding: str | None = None  # override job encoding if set
    # Optional label for reports
    label: str = ""


@dataclass
class SyncConfig:
    """Resolved sync job from YAML (+ CLI)."""

    config_path: Path
    history: Path
    banks: dict[str, BankProfile]
    append: Path | None = None
    append_dir: Path | None = None
    # Optional outer filter when using append_dir (applied before bank globs)
    append_glob: str = "*.csv"
    dedupe_keys: list[str] = field(default_factory=list)
    encoding: str = "utf-8-sig"
    account: str = ""
    # If set (e.g. "Id"), assign next integer ids on append
    auto_id: str | None = None
    # Write append-vs-history duplicates (YAML appdups: true|path)
    appdups: bool = False
    appdups_path: str | None = None
    # Write internal history duplicates (YAML hist_dups: true|path)
    hist_dups: bool = False
    hist_dups_path: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _resolve_path(base: Path, value: str | Path | None) -> Path | None:
    if value is None or value == "":
        return None
    p = Path(value)
    if not p.is_absolute():
        p = (base / p).resolve()
    else:
        p = p.resolve()
    return p


def _parse_bank_profiles(data: dict[str, Any]) -> dict[str, BankProfile]:
    """
    Prefer ``banks:`` mapping. Legacy single ``bank`` + ``column_map`` still works
    (treated as one profile with glob ``*``).
    """
    banks_raw = data.get("banks")
    profiles: dict[str, BankProfile] = {}

    if banks_raw is not None:
        if not isinstance(banks_raw, dict) or not banks_raw:
            raise ValueError("'banks' must be a non-empty mapping of name -> profile")
        for key, prof in banks_raw.items():
            if not isinstance(prof, dict):
                raise ValueError(f"banks.{key} must be a mapping")
            glob_pat = str(prof.get("glob") or "").strip()
            if not glob_pat:
                raise ValueError(f"banks.{key} requires 'glob' (filename pattern)")
            column_map = prof.get("column_map") or {}
            if not isinstance(column_map, dict):
                raise ValueError(f"banks.{key}.column_map must be a mapping")
            column_map = {str(k): str(v) for k, v in column_map.items() if v is not None and str(v) != ""}
            constants = prof.get("constants") or {}
            if not isinstance(constants, dict):
                raise ValueError(f"banks.{key}.constants must be a mapping")
            # Convenience: account_number / account_type shortcuts
            constants = {str(k): str(v) for k, v in constants.items()}
            if prof.get("account_number") is not None and "AccountNumber" not in constants:
                constants["AccountNumber"] = str(prof["account_number"])
            if prof.get("account_type") is not None and "AccountType" not in constants:
                constants["AccountType"] = str(prof["account_type"])
            fmt = str(prof.get("format") or "generic").strip().lower()
            enc = prof.get("encoding")
            profiles[str(key)] = BankProfile(
                key=str(key),
                glob=glob_pat,
                column_map=column_map,
                constants=constants,
                format=fmt,
                encoding=str(enc) if enc else None,
                label=str(prof.get("label") or key),
            )
        return profiles

    # Legacy: bank + column_map
    bank = str(data.get("bank") or "generic").strip().lower()
    column_map = data.get("column_map") or {}
    if not isinstance(column_map, dict):
        raise ValueError("'column_map' must be a mapping")
    column_map = {str(k): str(v) for k, v in column_map.items() if v}
    profiles[bank] = BankProfile(
        key=bank,
        glob="*",
        column_map=column_map,
        format="generic",
        label=bank,
    )
    return profiles


def _parse_optional_dup_flag(data: dict[str, Any], key: str) -> tuple[bool, str | None]:
    """
    Parse YAML ``appdups`` / ``hist_dups``:
      true / yes / 1  -> enabled, default filename
      false / null    -> disabled
      "path.csv"      -> enabled with that path
    """
    if key not in data:
        return False, None
    val = data.get(key)
    if val is None or val is False:
        return False, None
    if val is True:
        return True, None
    if isinstance(val, str):
        s = val.strip()
        if not s or s.lower() in ("false", "no", "0", "off"):
            return False, None
        if s.lower() in ("true", "yes", "1", "on"):
            return True, None
        return True, s
    raise ValueError(f"'{key}' must be true, false, or a file path string")


def load_config(path: Path) -> SyncConfig:
    try:
        import yaml
    except ImportError as e:
        raise SystemExit(
            "PyYAML is required. Install with: uv sync   (or pip install pyyaml)"
        ) from e

    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping")

    base = path.parent
    history = _resolve_path(base, data.get("history"))
    if history is None:
        raise ValueError("Config requires 'history' (path to transaction history CSV)")

    append = _resolve_path(base, data.get("append"))
    append_dir = _resolve_path(base, data.get("append_dir") or data.get("append_folder"))
    if append is None and append_dir is None:
        raise ValueError("Config requires 'append' (file) or 'append_dir' (folder)")
    if append is not None and append_dir is not None:
        raise ValueError("Specify only one of 'append' or 'append_dir'")

    banks = _parse_bank_profiles(data)

    dedupe = data.get("dedupe_keys") or data.get("dedupe") or []
    if isinstance(dedupe, str):
        dedupe = [s.strip() for s in dedupe.split(",") if s.strip()]
    if not isinstance(dedupe, list) or not dedupe:
        raise ValueError(
            "Config requires non-empty 'dedupe_keys' (list of history column names)"
        )
    dedupe_keys = [str(x) for x in dedupe]

    auto_id = data.get("auto_id")
    auto_id_s = str(auto_id).strip() if auto_id else None

    appdups, appdups_path = _parse_optional_dup_flag(data, "appdups")
    hist_dups, hist_dups_path = _parse_optional_dup_flag(data, "hist_dups")
    # Relative dup paths are relative to the config file
    if appdups_path:
        resolved = _resolve_path(base, appdups_path)
        appdups_path = str(resolved) if resolved else appdups_path
    if hist_dups_path:
        resolved = _resolve_path(base, hist_dups_path)
        hist_dups_path = str(resolved) if resolved else hist_dups_path

    return SyncConfig(
        config_path=path,
        history=history,
        banks=banks,
        append=append,
        append_dir=append_dir,
        append_glob=str(data.get("append_glob") or "*.csv"),
        dedupe_keys=dedupe_keys,
        encoding=str(data.get("encoding") or "utf-8-sig"),
        account=str(data.get("account") or data.get("label") or ""),
        auto_id=auto_id_s or None,
        appdups=appdups,
        appdups_path=appdups_path,
        hist_dups=hist_dups,
        hist_dups_path=hist_dups_path,
        raw=data,
    )


def match_bank_profile(cfg: SyncConfig, path: Path) -> BankProfile:
    """
    Pick the bank profile whose glob matches the filename.
    First match in config insertion order wins; more specific globs should be listed first.
    """
    name = path.name
    for prof in cfg.banks.values():
        if fnmatch.fnmatch(name, prof.glob) or fnmatch.fnmatch(name.lower(), prof.glob.lower()):
            return prof
    known = ", ".join(f"{k} ({p.glob})" for k, p in cfg.banks.items())
    raise ValueError(f"No banks.*.glob matches {name!r}. Configured: {known}")


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _norm_cell(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).replace("\ufeff", "").strip()


def parse_amount(value: str | None) -> str | None:
    """
    Parse history-style ``(1,234.56)`` / BoA ``-1,234.56`` / ``1234.56`` to a
    canonical signed decimal string without commas (e.g. ``-1234.56``).
    """
    if value is None:
        return None
    s = _norm_cell(value).replace("$", "").replace(",", "").replace(" ", "")
    if not s:
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return f"{float(s):.2f}"
    except ValueError:
        return None


def format_amount_history(canonical: str | None) -> str:
    """Format canonical signed amount as history style: (123.45) or 123.45."""
    if canonical is None:
        return ""
    try:
        v = float(canonical)
    except ValueError:
        return canonical
    if v < 0:
        return f"({abs(v):,.2f})"
    return f"{v:,.2f}"


def format_balance_history(value: str | None) -> str:
    """BoA running bal ``10,024.41`` → history-style plain ``10,024.41`` (no $)."""
    s = _norm_cell(value).replace("$", "").replace(",", "").replace(" ", "")
    if not s:
        return ""
    try:
        v = float(s)
    except ValueError:
        return _norm_cell(value)
    return f"{v:,.2f}"


_DATE_FMTS = ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%Y/%m/%d")


def parse_date(value: str | None):
    """Parse common bank/history date strings → datetime.date, or None."""
    from datetime import datetime

    s = _norm_cell(value)
    if not s:
        return None
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def format_date_history(value: str | None) -> str:
    """Write dates like history for this ledger: ``5/4/2026`` (no leading zeros)."""
    d = parse_date(value)
    if d is None:
        return _norm_cell(value)
    return f"{d.month}/{d.day}/{d.year}"


def canonicalize_date(value: str | None) -> str:
    """Stable dedupe form: ``YYYY-MM-DD``."""
    d = parse_date(value)
    if d is None:
        return _norm_cell(value)
    return d.isoformat()


# Digits and history redaction masks (X…) collapse to one token for soft match
_ID_LIKE = re.compile(r"[X\d]+", re.IGNORECASE)


def canonicalize_description(value: str | None) -> str:
    """
    Soft description key so redacted history IDs match full BoA IDs.

    History:  ID:XXXXXXXXXX00362 ... CO ID:XXXXX02284
    BoA:      ID:202605040000362 ... CO ID:7046002284

    Digit / ``X`` runs are collapsed to ``#``.
    """
    s = _norm_cell(value).upper()
    if not s:
        return ""
    s = _ID_LIKE.sub("#", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
# ---------------------------------------------------------------------------
# Row mapping
# ---------------------------------------------------------------------------


class MappedBankAdapter:
    """Map a source export row into the history schema using a BankProfile."""

    def __init__(self, profile: BankProfile):
        self.profile = profile

    def map_row(
        self,
        source_row: dict[str, str],
        history_fields: Sequence[str],
    ) -> dict[str, str]:
        out: dict[str, str] = {h: "" for h in history_fields}
        for hcol, src in self.profile.column_map.items():
            if hcol not in out:
                continue
            raw = source_row.get(src, "")
            out[hcol] = self._transform_field(hcol, raw)
        for hcol, val in self.profile.constants.items():
            if hcol in out:
                out[hcol] = str(val)
        return out

    def _transform_field(self, history_col: str, raw: str) -> str:
        fmt = self.profile.format
        col_l = history_col.lower()
        if col_l == "amount":
            canon = parse_amount(raw)
            if canon is None:
                return _norm_cell(raw)
            # Always store history-style amounts for schema consistency
            return format_amount_history(canon)
        if col_l in ("transdate", "posteddate") or col_l.endswith("date"):
            # History uses unpadded m/d/yyyy (e.g. 5/4/2026 not 05/04/2026)
            return format_date_history(raw)
        if col_l == "balance" and fmt == "bofa":
            return format_balance_history(raw)
        return _norm_cell(raw)

    def fingerprint(
        self,
        history_row: dict[str, str],
        dedupe_keys: Sequence[str],
    ) -> tuple[str, ...]:
        """
        Canonical fingerprint so exports match existing history rows despite
        formatting differences (date zero-padding, amount parens, redacted IDs).
        """
        parts: list[str] = []
        for k in dedupe_keys:
            val = history_row.get(k, "")
            kl = k.lower()
            if kl == "amount":
                canon = parse_amount(val)
                parts.append(canon if canon is not None else _norm_cell(val))
            elif kl in ("transdate", "posteddate") or kl.endswith("date"):
                parts.append(canonicalize_date(val))
            elif kl == "description":
                parts.append(canonicalize_description(val))
            else:
                parts.append(_norm_cell(val))
        return tuple(parts)

# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------


@dataclass
class HistoryTable:
    path: Path
    fieldnames: list[str]
    rows: list[dict[str, str]]
    encoding: str
    dialect: type


def _make_dialect(delimiter: str) -> type:
    class _Dialect(csv.excel):
        pass

    _Dialect.delimiter = delimiter
    return _Dialect


def read_csv_table(
    path: Path,
    encoding: str,
    *,
    format: str = "generic",
) -> tuple[list[str], list[dict[str, str]], type]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")
    raw = path.read_bytes()
    if not raw.strip():
        raise ValueError(f"CSV is empty: {path}")

    text = raw.decode(encoding)
    sample = text[:8192]
    try:
        sniffed = csv.Sniffer().sniff(sample, delimiters=",\t;")
        delimiter = sniffed.delimiter
    except csv.Error:
        delimiter = ","
    dialect = _make_dialect(delimiter)

    with open(path, newline="", encoding=encoding) as f:
        reader = csv.reader(f, dialect=dialect)
        rows_raw = list(reader)

    if not rows_raw:
        raise ValueError(f"CSV has no rows: {path}")

    header_idx = 0
    if format == "bofa":
        header_idx = _find_bofa_header_index(rows_raw)
        if header_idx < 0:
            raise ValueError(
                f"BoA transaction header not found in {path.name} "
                f"(expected a row like: Date, Description, Amount, Running Bal.)"
            )

    header = rows_raw[header_idx]
    fieldnames = [_norm_cell(h) for h in header]
    # BoA sometimes has empty header cells; keep positions stable with placeholders
    fixed_names: list[str] = []
    used: set[str] = set()
    for i, name in enumerate(fieldnames):
        if not name:
            name = f"_col{i}"
        base = name
        n = 2
        while name in used:
            name = f"{base}_{n}"
            n += 1
        used.add(name)
        fixed_names.append(name)
    fieldnames = fixed_names

    rows: list[dict[str, str]] = []
    for cells in rows_raw[header_idx + 1 :]:
        if not any(_norm_cell(c) for c in cells):
            continue
        if len(cells) < len(fieldnames):
            cells = cells + [""] * (len(fieldnames) - len(cells))
        row = {fieldnames[i]: cells[i] for i in range(len(fieldnames))}
        if format == "bofa" and _is_bofa_non_transaction(row):
            continue
        rows.append(row)
    return fieldnames, rows, dialect


def _find_bofa_header_index(rows: list[list[str]]) -> int:
    for i, cells in enumerate(rows):
        norm = [_norm_cell(c).lower() for c in cells]
        if not norm:
            continue
        # Checking: Date, Description, Amount, Running Bal.
        if norm[0] == "date" and "description" in norm and "amount" in norm:
            return i
        # Business CC (BA_BCC): CardHolder Name, … Trans. Date, Reference ID, Description, Amount
        if (
            "description" in norm
            and "amount" in norm
            and ("trans. date" in norm or "posting date" in norm)
        ):
            return i
    return -1


def _is_bofa_non_transaction(row: dict[str, str]) -> bool:
    """Skip beginning-balance / empty-amount lines in BoA detail section."""
    desc = _norm_cell(row.get("Description", "")).lower()
    amt = _norm_cell(row.get("Amount", ""))
    if not amt:
        return True
    if desc.startswith("beginning balance"):
        return True
    return False


def load_history(cfg: SyncConfig) -> HistoryTable:
    fieldnames, rows, dialect = read_csv_table(cfg.history, cfg.encoding, format="generic")
    missing = [k for k in cfg.dedupe_keys if k not in fieldnames]
    if missing:
        raise ValueError(
            f"dedupe_keys not in history header: {missing}. "
            f"History columns: {fieldnames}"
        )
    if cfg.auto_id and cfg.auto_id not in fieldnames:
        raise ValueError(f"auto_id column {cfg.auto_id!r} not in history header")
    return HistoryTable(
        path=cfg.history,
        fieldnames=fieldnames,
        rows=rows,
        encoding=cfg.encoding,
        dialect=dialect,
    )


def list_append_files(cfg: SyncConfig) -> list[Path]:
    if cfg.append is not None:
        if not cfg.append.is_file():
            raise FileNotFoundError(f"Append CSV not found: {cfg.append}")
        return [cfg.append]
    assert cfg.append_dir is not None
    if not cfg.append_dir.is_dir():
        raise FileNotFoundError(f"Append folder not found: {cfg.append_dir}")

    # Outer filter, then keep only files that match at least one bank glob
    candidates = sorted(p for p in cfg.append_dir.glob(cfg.append_glob) if p.is_file())
    hist = cfg.history.resolve()
    out: list[Path] = []
    for p in candidates:
        if p.resolve() == hist:
            continue
        try:
            match_bank_profile(cfg, p)
        except ValueError:
            continue
        out.append(p)
    return out


def next_auto_id(history: HistoryTable, col: str) -> int:
    mx = 0
    for row in history.rows:
        s = _norm_cell(row.get(col, ""))
        if s.isdigit():
            mx = max(mx, int(s))
    return mx + 1


def append_rows_to_history(
    history: HistoryTable,
    new_rows: Sequence[dict[str, str]],
) -> None:
    if not new_rows:
        return
    with open(history.path, "a", newline="", encoding=history.encoding) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=history.fieldnames,
            extrasaction="ignore",
            dialect=history.dialect,
            lineterminator="\n",
        )
        for row in new_rows:
            ordered = {k: row.get(k, "") for k in history.fieldnames}
            writer.writerow(ordered)


# ---------------------------------------------------------------------------
# Sync engine
# ---------------------------------------------------------------------------


@dataclass
class FileSyncResult:
    path: Path
    bank_key: str
    bank_label: str
    account_number: str
    account_type: str
    source_rows: int
    new_rows: list[dict[str, str]]
    duplicate_count: int
    # Append-file transaction date range (history-style m/d/yyyy)
    append_date_first: str = ""
    append_date_last: str = ""
    # Latest history row for the same AccountNumber (before this sync)
    history_latest_date: str = ""
    history_latest_amount: str = ""
    history_latest_description: str = ""
    skipped_non_txn: int = 0
    error: str = ""


@dataclass
class SyncResult:
    history: HistoryTable
    history_rows_before: int
    files: list[FileSyncResult]
    appended: list[dict[str, str]]
    # Rows for -df: history schema + DupSrc (H or append stem)
    dup_rows: list[dict[str, str]] = field(default_factory=list)
    dup_file: Path | None = None
    # Rows for -dh: internal history duplicates only (DupSrc=H)
    hist_dup_rows: list[dict[str, str]] = field(default_factory=list)
    hist_dup_file: Path | None = None
    hist_dup_groups: int = 0

    @property
    def new_count(self) -> int:
        return len(self.appended)

    @property
    def duplicate_count(self) -> int:
        return sum(f.duplicate_count for f in self.files)


def latest_history_for_account(
    history: HistoryTable,
    account_number: str,
) -> dict[str, str] | None:
    """Newest history row for AccountNumber (by TransDate, then Id)."""
    acct = _norm_cell(account_number)
    if not acct:
        return None
    best: dict[str, str] | None = None
    best_key: tuple = ()
    for row in history.rows:
        if _norm_cell(row.get("AccountNumber", "")) != acct:
            continue
        d = parse_date(row.get("TransDate") or row.get("PostedDate"))
        try:
            rid = int(_norm_cell(row.get("Id", "")) or "0")
        except ValueError:
            rid = 0
        key = (d.toordinal() if d else -1, rid)
        if best is None or key > best_key:
            best = row
            best_key = key
    return best


def date_range_labels(mapped_rows: Sequence[dict[str, str]]) -> tuple[str, str]:
    """Return (first, last) TransDate/PostedDate labels for mapped rows."""
    dates = []
    for row in mapped_rows:
        d = parse_date(row.get("TransDate") or row.get("PostedDate"))
        if d is not None:
            dates.append(d)
    if not dates:
        return "", ""
    return format_date_history(min(dates).isoformat()), format_date_history(
        max(dates).isoformat()
    )


def _profile_account(profile: BankProfile) -> tuple[str, str]:
    acct = profile.constants.get("AccountNumber", "")
    atype = profile.constants.get("AccountType", "")
    return _norm_cell(acct), _norm_cell(atype)


def _short_dup_src(path: Path) -> str:
    """Short appendant label for DupSrc (filename stem)."""
    return path.stem


def _history_row_copy(row: dict[str, str], fieldnames: Sequence[str]) -> dict[str, str]:
    return {k: row.get(k, "") for k in fieldnames}


def write_dup_file(
    path: Path,
    history_fields: Sequence[str],
    dup_rows: Sequence[dict[str, str]],
    encoding: str,
    dialect: type,
) -> None:
    """Write duplicates CSV: history columns + DupSrc."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(history_fields) + ["DupSrc"]
    with open(path, "w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
            dialect=dialect,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in dup_rows:
            ordered = {k: row.get(k, "") for k in fieldnames}
            writer.writerow(ordered)


def resolve_dup_file_path(cfg: SyncConfig, dup_file: str | Path | None) -> Path:
    """Default: <history_stem>_appdups.csv beside the history file."""
    if dup_file is None or str(dup_file).strip() == "":
        return cfg.history.parent / f"{cfg.history.stem}_appdups.csv"
    p = Path(dup_file)
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    return p


def resolve_hist_dup_file_path(cfg: SyncConfig, hist_dup_file: str | Path | None) -> Path:
    """Default: <history_stem>_hist_dups.csv beside the history file."""
    if hist_dup_file is None or str(hist_dup_file).strip() == "":
        return cfg.history.parent / f"{cfg.history.stem}_hist_dups.csv"
    p = Path(hist_dup_file)
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    return p


def find_history_duplicates(
    history: HistoryTable,
    dedupe_keys: Sequence[str],
) -> tuple[list[dict[str, str]], int]:
    """
    Find rows inside history that share a dedupe fingerprint (2+ copies).

    Returns (rows with DupSrc=H, number of duplicate groups).
    Append exports are ignored.
    """
    fp_helper = MappedBankAdapter(BankProfile(key="_", glob="*"))
    groups: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for row in history.rows:
        fp = fp_helper.fingerprint(row, dedupe_keys)
        groups.setdefault(fp, []).append(_history_row_copy(row, history.fieldnames))

    out: list[dict[str, str]] = []
    n_groups = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        n_groups += 1
        for m in members:
            row = dict(m)
            row["DupSrc"] = "H"
            out.append(row)
    return out, n_groups


def sync(
    cfg: SyncConfig,
    *,
    dry_run: bool = False,
    verbose: bool = False,
    dup_file: str | Path | None = None,
    hist_dup_file: str | Path | None = None,
) -> SyncResult:
    del verbose  # used only in report
    history = load_history(cfg)

    hist_dup_rows: list[dict[str, str]] = []
    hist_dup_groups = 0
    written_hist_dup: Path | None = None
    if hist_dup_file is not None:
        hist_dup_rows, hist_dup_groups = find_history_duplicates(
            history, cfg.dedupe_keys
        )
        written_hist_dup = resolve_hist_dup_file_path(cfg, hist_dup_file)
        write_dup_file(
            written_hist_dup,
            history.fieldnames,
            hist_dup_rows,
            history.encoding,
            history.dialect,
        )

    append_files = list_append_files(cfg)
    # Allow -dh-only runs when the buffer has nothing matching bank globs
    if not append_files:
        if hist_dup_file is None and dup_file is None:
            patterns = ", ".join(f"{k}:{p.glob}" for k, p in cfg.banks.items())
            raise FileNotFoundError(
                f"No append CSV files matched bank globs [{patterns}] "
                f"under {cfg.append_dir or cfg.append}"
            )
        return SyncResult(
            history=history,
            history_rows_before=len(history.rows),
            files=[],
            appended=[],
            hist_dup_rows=hist_dup_rows,
            hist_dup_file=written_hist_dup,
            hist_dup_groups=hist_dup_groups,
        )

    # Fingerprint -> (DupSrc label, row in history schema)
    fp_helper = MappedBankAdapter(BankProfile(key="_", glob="*"))
    seen: dict[tuple[str, ...], tuple[str, dict[str, str]]] = {}
    for row in history.rows:
        fp = fp_helper.fingerprint(row, cfg.dedupe_keys)
        if fp not in seen:
            seen[fp] = ("H", _history_row_copy(row, history.fieldnames))

    next_id = next_auto_id(history, cfg.auto_id) if cfg.auto_id else None

    file_results: list[FileSyncResult] = []
    to_append: list[dict[str, str]] = []
    dup_rows: list[dict[str, str]] = []
    collect_dups = dup_file is not None

    for path in append_files:
        short = _short_dup_src(path)
        try:
            profile = match_bank_profile(cfg, path)
            enc = profile.encoding or cfg.encoding
            # bofa_cc is a plain header CSV (no preamble); reader format = generic
            reader_fmt = "bofa" if profile.format == "bofa" else "generic"
            _fields, src_rows, _ = read_csv_table(path, enc, format=reader_fmt)
            adapter = MappedBankAdapter(profile)
            acct, atype = _profile_account(profile)
            latest = latest_history_for_account(history, acct) if acct else None
        except Exception as e:
            file_results.append(
                FileSyncResult(
                    path=path,
                    bank_key="?",
                    bank_label="",
                    account_number="",
                    account_type="",
                    source_rows=0,
                    new_rows=[],
                    duplicate_count=0,
                    error=str(e),
                )
            )
            continue

        new_from_file: list[dict[str, str]] = []
        considered: list[dict[str, str]] = []
        dup = 0
        for src in src_rows:
            mapped = adapter.map_row(src, history.fieldnames)
            # Skip rows that mapped to empty amount (non-transactions that slipped through)
            if "Amount" in history.fieldnames and not _norm_cell(mapped.get("Amount", "")):
                continue
            considered.append(mapped)
            fp = adapter.fingerprint(mapped, cfg.dedupe_keys)
            if fp in seen:
                dup += 1
                if collect_dups:
                    existing_src, existing_row = seen[fp]
                    h_out = dict(existing_row)
                    h_out["DupSrc"] = existing_src
                    a_out = _history_row_copy(mapped, history.fieldnames)
                    a_out["DupSrc"] = short
                    dup_rows.append(h_out)
                    dup_rows.append(a_out)
                continue
            # Register as coming from this append file (for later within-run dups)
            seen[fp] = (short, _history_row_copy(mapped, history.fieldnames))
            if cfg.auto_id and next_id is not None:
                mapped[cfg.auto_id] = str(next_id)
                next_id += 1
            new_from_file.append(mapped)

        d0, d1 = date_range_labels(considered)
        file_results.append(
            FileSyncResult(
                path=path,
                bank_key=profile.key,
                bank_label=profile.label or profile.key,
                account_number=acct,
                account_type=atype,
                source_rows=len(considered),
                new_rows=new_from_file,
                duplicate_count=dup,
                append_date_first=d0,
                append_date_last=d1,
                history_latest_date=_norm_cell((latest or {}).get("TransDate", "")),
                history_latest_amount=_norm_cell((latest or {}).get("Amount", "")),
                history_latest_description=_norm_cell(
                    (latest or {}).get("Description", "")
                ),
            )
        )
        to_append.extend(new_from_file)

    if not dry_run and to_append:
        append_rows_to_history(history, to_append)

    written_dup: Path | None = None
    if collect_dups:
        written_dup = resolve_dup_file_path(cfg, dup_file)
        write_dup_file(
            written_dup,
            history.fieldnames,
            dup_rows,
            history.encoding,
            history.dialect,
        )

    return SyncResult(
        history=history,
        history_rows_before=len(history.rows),
        files=file_results,
        appended=to_append,
        dup_rows=dup_rows,
        dup_file=written_dup,
        hist_dup_rows=hist_dup_rows,
        hist_dup_file=written_hist_dup,
        hist_dup_groups=hist_dup_groups,
    )


def print_report(
    cfg: SyncConfig,
    result: SyncResult,
    *,
    dry_run: bool,
    verbose: bool,
) -> None:
    history = result.history
    label = f" ({cfg.account})" if cfg.account else ""
    print(f"transync{label}")
    print(f"  config:   {cfg.config_path}")
    print(f"  banks:    {', '.join(f'{k} [{p.glob}]' for k, p in cfg.banks.items())}")
    print(f"  history:  {cfg.history}")
    print(
        f"            {result.history_rows_before} existing row(s); "
        f"schema ({len(history.fieldnames)} cols)"
    )
    print(f"  dedupe:   {', '.join(cfg.dedupe_keys)}")
    if cfg.auto_id:
        print(f"  auto_id:  {cfg.auto_id}")
    if cfg.append:
        print(f"  append:   {cfg.append}")
    else:
        print(f"  append:   {cfg.append_dir} / {cfg.append_glob}")
    print(f"  sources:  {len(result.files)} file(s)")
    print()

    for i, fr in enumerate(result.files, 1):
        name = fr.path.name
        print(f"  [{i}/{len(result.files)}] {name}")
        if fr.error:
            print(f"    ERROR: {fr.error}")
            print()
            continue
        acct_bits = fr.account_number or "?"
        if fr.account_type:
            acct_bits = f"{acct_bits} / {fr.account_type}"
        print(f"    bank:     {fr.bank_key} ({fr.bank_label})")
        print(f"    account:  {acct_bits}")
        if fr.history_latest_date or fr.history_latest_amount:
            desc = fr.history_latest_description
            if len(desc) > 72:
                desc = desc[:69] + "..."
            print(
                f"    history:  latest {fr.history_latest_date}  "
                f"{fr.history_latest_amount}  {desc}"
            )
        else:
            print("    history:  (no prior rows for this AccountNumber)")
        if fr.append_date_first or fr.append_date_last:
            print(
                f"    append:   {fr.append_date_first} .. {fr.append_date_last}  "
                f"({fr.source_rows} txn)"
            )
        else:
            print(f"    append:   ({fr.source_rows} txn; no dates parsed)")
        print(
            f"    result:   {len(fr.new_rows)} new, {fr.duplicate_count} duplicate(s)"
        )
        if verbose and fr.new_rows:
            for row in fr.new_rows[:5]:
                bits = [f"{k}={row.get(k, '')!r}" for k in cfg.dedupe_keys]
                print(f"       + {', '.join(bits)}")
            if len(fr.new_rows) > 5:
                print(f"       ... {len(fr.new_rows) - 5} more")
        print()

    if dry_run:
        print(
            f"Dry-run: would append {result.new_count} row(s) "
            f"({result.duplicate_count} duplicate(s) skipped). "
            f"History not modified."
        )
    else:
        print(
            f"Appended {result.new_count} row(s) "
            f"({result.duplicate_count} duplicate(s) skipped). "
            f"History now has {result.history_rows_before + result.new_count} row(s)."
        )
    if result.dup_file is not None:
        # Each skipped append txn contributes 2 rows (existing + appendant)
        pairs = len(result.dup_rows) // 2
        print(
            f"App dups: {result.dup_file}  "
            f"({pairs} pair(s), {len(result.dup_rows)} row(s); DupSrc=H|append-stem)"
        )
    if result.hist_dup_file is not None:
        print(
            f"Hist dups: {result.hist_dup_file}  "
            f"({result.hist_dup_groups} group(s), {len(result.hist_dup_rows)} row(s); "
            f"DupSrc=H; append ignored)"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _merge_dup_option(
    cli_value: str | None,
    cfg_enabled: bool,
    cfg_path: str | None,
) -> str | None:
    """
    CLI wins when -df/-dh is passed (including bare flag -> "").
    Otherwise use YAML appdups/hist_dups.
    Returns None to skip, or path string ("" = use default filename).
    """
    if cli_value is not None:
        return cli_value  # "" means default path
    if cfg_enabled:
        return cfg_path if cfg_path is not None else ""
    return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sync bank transaction CSV exports into a history CSV without duplicates. "
            "Bank profile is chosen by matching the append filename to banks.*.glob."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python transync.py -c _GTNotes/transync.yaml -n
  python transync.py -c _GTNotes/transync.yaml -n -df
  python transync.py -c _GTNotes/transync.yaml -dh
  python transync.py -c _GTNotes/transync.yaml -n -df -dh

YAML (optional; CLI -df/-dh overrides):
  appdups: true              # -> <history_stem>_appdups.csv
  hist_dups: true            # -> <history_stem>_hist_dups.csv
  # or set an explicit path string instead of true

-n / --dry-run            Do not write history.
-df / --dup-file          Append-vs-history duplicates; default <stem>_appdups.csv
-dh / --history-dup-file  History-only duplicates; default <stem>_hist_dups.csv
        """,
    )
    parser.add_argument("-c", "--config", default=None, metavar="FILE", help="YAML config file")
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Show what would be appended; do not modify history",
    )
    parser.add_argument(
        "-df",
        "--dup-file",
        nargs="?",
        const="",
        default=None,
        metavar="FILE",
        help=(
            "Write CSV of skipped append duplicates (history schema + DupSrc). "
            "Default: <history_stem>_appdups.csv beside history. "
            "Also enabled via YAML appdups: true"
        ),
    )
    parser.add_argument(
        "-dh",
        "--history-dup-file",
        nargs="?",
        const="",
        default=None,
        metavar="FILE",
        help=(
            "Write CSV of duplicates found inside history only (ignore appends). "
            "Default: <history_stem>_hist_dups.csv beside history. "
            "Also enabled via YAML hist_dups: true"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show sample of new rows (dedupe key fields)",
    )
    parser.add_argument(
        "--list-banks",
        action="store_true",
        help="With -c: list bank keys and globs from that config",
    )
    args = parser.parse_args(argv)

    if args.list_banks:
        if not args.config:
            parser.error("--list-banks requires -c/--config")
        cfg = load_config(Path(args.config))
        for key, prof in cfg.banks.items():
            print(f"{key}\tglob={prof.glob}\tformat={prof.format}")
        return

    if not args.config:
        parser.error("the following arguments are required: -c/--config")

    try:
        cfg = load_config(Path(args.config))
    except Exception as e:
        print(f"Error: config: {e}", file=sys.stderr)
        raise SystemExit(1) from e

    dup_file = _merge_dup_option(args.dup_file, cfg.appdups, cfg.appdups_path)
    hist_dup_file = _merge_dup_option(
        args.history_dup_file, cfg.hist_dups, cfg.hist_dups_path
    )

    try:
        result = sync(
            cfg,
            dry_run=args.dry_run,
            verbose=args.verbose,
            dup_file=dup_file,
            hist_dup_file=hist_dup_file,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1) from e

    print_report(cfg, result, dry_run=args.dry_run, verbose=args.verbose)
    if any(f.error for f in result.files):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
