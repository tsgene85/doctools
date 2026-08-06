"""
Extract ADP earnings-statement (paystub) fields from PDFs → CSV.

Ingest a folder of ADP paystub PDFs (-f). One row per statement, keyed by
advice number (fallback: pay_date + employee + period_ending). Re-runs upsert:
existing keys are updated; new stubs are appended.

Requires PyMuPDF (``pymupdf``) for reliable ADP text layout.

Run: python adppay2csv.py -h
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

COLUMNS = [
    "record_key",
    "source_file",
    "advice_number",
    "pay_date",
    "period_beginning",
    "period_ending",
    "employee_name",
    "employee_address",
    "company_name",
    "company_address",
    "company_phone",
    "co_code",
    "file_dept_clock_vchr",
    "basis_of_pay",
    "filing_status",
    "federal_withholding",
    "taxable_marital_status_ma",
    "ma_exemptions",
    "regular_rate",
    "regular_hours",
    "regular_period",
    "regular_ytd",
    "holiday_rate",
    "holiday_hours",
    "holiday_period",
    "holiday_ytd",
    "total_hours",
    "gross_pay",
    "gross_pay_ytd",
    "federal_income_tax",
    "federal_income_tax_ytd",
    "social_security_tax",
    "social_security_tax_ytd",
    "medicare_tax",
    "medicare_tax_ytd",
    "ma_state_income_tax",
    "ma_state_income_tax_ytd",
    "ma_paid_family_leave",
    "ma_paid_family_leave_ytd",
    "ma_paid_medical_leave",
    "ma_paid_medical_leave_ytd",
    "benefit_401k_w_period",
    "benefit_401k_w_ytd",
    "chsupp_period",
    "chsupp_ytd",
    "net_pay",
    "direct_deposit",
    "net_check",
    "federal_taxable_wages",
    "deposit_account_masked",
    "parse_ok",
    "parse_notes",
]

# Label text (as in PDF) → (period_col, ytd_col)
TAX_LABELS = [
    ("Federal Income Tax", "federal_income_tax", "federal_income_tax_ytd"),
    ("Social Security Tax", "social_security_tax", "social_security_tax_ytd"),
    ("Medicare Tax", "medicare_tax", "medicare_tax_ytd"),
    ("MA State Income Tax", "ma_state_income_tax", "ma_state_income_tax_ytd"),
    ("MA Paid Family Leave Ins", "ma_paid_family_leave", "ma_paid_family_leave_ytd"),
    ("MA Paid Medical Leave Ins", "ma_paid_medical_leave", "ma_paid_medical_leave_ytd"),
]

# ADP spaced amounts — longest forms first so YTD "2 563 12" is not eaten by "-320 39 2".
_ADP_AMOUNT_RE = re.compile(
    r"""
    (?<![\w.])
    (
        -?\$\d{1,3}(?:\s+\d{3})+\s+\d{2}   # $3 000 00 / $2 297 78
      | -?\d+\s+\d{3}\s+\d{2}               # 2 563 12 / 3 000 00
      | -?\d+\s+\d{4}                       # 75 0000 (pay rate)
      | -?\d+\s+\d{2}                       # -320 39 / 40 00 / 348 00
    )
    (?![\w.])
    """,
    re.VERBOSE,
)


def _empty_row(source_file: str = "") -> dict[str, str]:
    return {c: "" for c in COLUMNS} | {"source_file": source_file, "parse_ok": "0"}


def parse_adp_number(token: str) -> str | None:
    """Normalize one ADP spaced amount token to a plain decimal string."""
    if not token:
        return None
    s = token.replace(",", "").strip()
    if not s:
        return None
    neg = s.startswith("-")
    s = s.lstrip("-").strip()
    if s.startswith("$"):
        s = s[1:].strip()
    bits = s.split()
    if not bits or not all(re.fullmatch(r"\d+", b) for b in bits):
        return None
    if len(bits) == 1:
        out = bits[0]
    elif len(bits) == 2 and len(bits[1]) == 4:
        out = f"{bits[0]}.{bits[1]}"
    elif len(bits) == 2 and len(bits[1]) <= 2:
        out = f"{bits[0]}.{bits[1].zfill(2)}"
    elif len(bits) >= 3 and len(bits[-1]) <= 2:
        out = f"{''.join(bits[:-1])}.{bits[-1].zfill(2)}"
    else:
        out = "".join(bits)
    try:
        float(out)
    except ValueError:
        return None
    return f"-{out}" if neg else out


def iter_adp_numbers(text: str) -> list[str]:
    """Parse all ADP spaced amounts from text in left-to-right order."""
    out: list[str] = []
    for m in _ADP_AMOUNT_RE.finditer(text.replace("\n", " ")):
        n = parse_adp_number(m.group(1))
        if n is not None:
            out.append(n)
    return out


def _money_pairs_in_text(text: str) -> list[tuple[str, str | None]]:
    """Extract (period[, ytd]) money pairs from a text blob."""
    vals = iter_adp_numbers(text)
    pairs: list[tuple[str, str | None]] = []
    i = 0
    while i < len(vals):
        period = vals[i]
        ytd = vals[i + 1] if i + 1 < len(vals) else None
        if ytd is not None:
            pairs.append((period, ytd))
            i += 2
        else:
            pairs.append((period, None))
            i += 1
    return pairs


def _blocks(page) -> list[tuple[float, float, float, float, str]]:
    out: list[tuple[float, float, float, float, str]] = []
    for b in page.get_text("blocks"):
        x0, y0, x1, y1, text, *_ = b
        t = (text or "").strip()
        if not t or "\x00" in t:
            continue
        out.append((float(y0), float(x0), float(x1), float(y1), t))
    return out


def _label_value(blocks: list[tuple[float, float, float, float, str]], label: str) -> str:
    """Value in same block after label, or nearest right-side block on similar y."""
    lab = label.rstrip(":")
    for y0, x0, _x1, _y1, text in blocks:
        flat = text.replace("\n", " ").strip()
        if flat.lower().startswith(lab.lower()):
            rest = flat[len(lab) :].lstrip(" :")
            if rest:
                return rest.strip()
            # look right
            best = None
            best_dx = 1e9
            for y2, x2, _x3, _y3, t2 in blocks:
                if abs(y2 - y0) > 3 or x2 <= x0 + 5:
                    continue
                dx = x2 - x0
                if dx < best_dx:
                    best_dx = dx
                    best = t2.replace("\n", " ").strip()
            return best or ""
    return ""


def _find_block_containing(
    blocks: list[tuple[float, float, float, float, str]], needle: str
) -> tuple[float, float, str] | None:
    for y0, x0, _x1, _y1, text in blocks:
        if needle.lower() in text.lower():
            return y0, x0, text
    return None


def _parse_earnings_line(text: str, name: str) -> tuple[str, str, str, str]:
    """Parse 'Regular 75 0000 40 00 3 000 00 24 000 00' → rate, hours, period, ytd."""
    flat = text.replace("\n", " ")
    m = re.search(
        rf"{re.escape(name)}\s+(.+)$",
        flat,
        re.I,
    )
    if not m:
        return "", "", "", ""
    nums = iter_adp_numbers(m.group(1))
    if len(nums) >= 4:
        return nums[0], nums[1], nums[2], nums[3]
    if len(nums) == 1:
        # YTD-only residual e.g. "Holiday 600 00" / "Holiday 1 200 00"
        return "", "", "", nums[0]
    if len(nums) == 2:
        return "", "", nums[0], nums[1]
    if len(nums) == 3:
        return nums[0], nums[1], nums[2], ""
    return "", "", "", ""


def _assign_tax_rows(
    blocks: list[tuple[float, float, float, float, str]], row: dict[str, str], notes: list[str]
) -> None:
    """Match tax labels to amount column by y; handle split PFML/PML layouts."""
    pending_extra: tuple[str, str | None] | None = None
    for label, col_p, col_y in TAX_LABELS:
        label_hits = [
            (y0, x0, text)
            for y0, x0, _x1, _y1, text in blocks
            if label.lower() in text.replace("\n", " ").lower() and x0 < 200
        ]
        if not label_hits:
            if pending_extra:
                row[col_p], row[col_y] = pending_extra[0], pending_extra[1] or ""
                pending_extra = None
            continue
        y0, _x0, text = min(label_hits, key=lambda t: t[0])
        # Amount column on same row (left of the right-hand info pane)
        amt_blocks = [
            (ay, ax, at)
            for ay, ax, _x1, _y1, at in blocks
            if abs(ay - y0) <= 2.5 and 180 <= ax <= 340 and _money_pairs_in_text(at)
        ]
        period = ytd = ""
        extras_in_label = _money_pairs_in_text(text)
        if amt_blocks:
            pairs = _money_pairs_in_text(amt_blocks[0][2])
            if pairs:
                period, ytd = pairs[0][0], pairs[0][1] or ""
            # Extra pair inside label block belongs to a following line missing amounts
            label_only_pairs = [
                p for p in extras_in_label if p[0] != period and (p[1] or "") != ytd
            ]
            if label_only_pairs:
                pending_extra = label_only_pairs[0]
        elif extras_in_label:
            period, ytd = extras_in_label[0][0], extras_in_label[0][1] or ""
        elif pending_extra:
            period, ytd = pending_extra[0], pending_extra[1] or ""
            pending_extra = None
        row[col_p] = period
        row[col_y] = ytd
        if not period:
            notes.append(f"missing {label}")


def parse_adp_stub(page, source_file: str) -> dict[str, str]:
    row = _empty_row(source_file)
    notes: list[str] = []
    blocks = _blocks(page)
    text = page.get_text("text") or ""

    row["period_beginning"] = _label_value(blocks, "Period Beginning")
    row["period_ending"] = _label_value(blocks, "Period Ending")
    row["pay_date"] = _label_value(blocks, "Pay Date") or _label_value(blocks, "Pay date")
    row["advice_number"] = _label_value(blocks, "Advice number")
    row["basis_of_pay"] = _label_value(blocks, "BASIS OF PAY").lstrip(": ").strip()
    phone_blk = _find_block_containing(blocks, "COMPANY")
    if phone_blk:
        m = re.search(r"PH#:\s*([+\d\s]+)", phone_blk[2].replace("\n", " "))
        if m:
            row["company_phone"] = re.sub(r"\s+", " ", m.group(1)).strip()

    # CO / FILE / DEPT / CLOCK / VCHR line under header codes
    for _y, _x, _x1, _y1, t in blocks:
        flat = t.replace("\n", " ").strip()
        if re.fullmatch(r"\d{5,}\s+\d{5,}\s+\d+", flat):
            row["file_dept_clock_vchr"] = flat
            row["co_code"] = flat.split()[0]
            break
    # Sometimes split across lines: 006259 / 0000210031 / 1
    if not row["file_dept_clock_vchr"]:
        for _y, x0, _x1, _y1, t in blocks:
            if x0 > 150:
                continue
            parts = [p.strip() for p in t.splitlines() if p.strip()]
            if len(parts) == 3 and all(re.fullmatch(r"\d+", p) for p in parts):
                row["file_dept_clock_vchr"] = " ".join(parts)
                row["co_code"] = parts[0]
                break

    # Employee name: large text near top-right (y ~ 100-120, x > 350)
    name_candidates = [
        (y0, t.replace("\n", " ").strip())
        for y0, x0, _x1, _y1, t in blocks
        if 100 < y0 < 130 and x0 > 350 and re.search(r"[A-Za-z]", t)
    ]
    if name_candidates:
        row["employee_name"] = sorted(name_candidates, key=lambda x: x[0])[0][1]

    # Employee address block (right column under name)
    addr_lines: list[str] = []
    for y0, x0, _x1, _y1, t in sorted(blocks, key=lambda b: b[0]):
        if x0 < 350 or y0 < 120 or y0 > 170:
            continue
        line = " ".join(t.split())
        if line in {row["employee_name"], "#1"} or line.startswith("Period"):
            continue
        if re.search(r"[A-Za-z]", line):
            addr_lines.append(line)
    row["employee_address"] = ", ".join(addr_lines)

    # Company name/address (left column)
    company_bits: list[str] = []
    for y0, x0, _x1, _y1, t in sorted(blocks, key=lambda b: b[0]):
        if x0 > 200 or y0 < 40 or y0 > 100:
            continue
        line = " ".join(t.split())
        if "CO." in line and "FILE" in line:
            continue
        if re.match(r"^ADG$", line):
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if re.search(r"[A-Za-z]", line):
            company_bits.append(line)
    if company_bits:
        row["company_name"] = company_bits[0]
        if len(company_bits) > 1:
            row["company_address"] = ", ".join(company_bits[1:])

    fs = _find_block_containing(blocks, "Filing Status:")
    if fs:
        m = re.search(r"Filing Status:\s*(.+)", fs[2].replace("\n", " "))
        if m:
            row["filing_status"] = m.group(1).strip()
    fw = _find_block_containing(blocks, "Federal:")
    if fw:
        row["federal_withholding"] = " ".join(fw[2].replace("\n", " ").split())
    ma = _find_block_containing(blocks, "MA:")
    # taxable marital status block
    for y0, x0, _x1, _y1, t in blocks:
        flat = t.replace("\n", " ")
        if "MA:" in flat and x0 > 300:
            m = re.search(r"MA:\s*(\w+)", flat)
            if m and not row["taxable_marital_status_ma"]:
                row["taxable_marital_status_ma"] = m.group(1)
            m2 = re.search(r"MA:\s*(\d+)", flat)
            if m2:
                row["ma_exemptions"] = m2.group(1)

    # Earnings
    earn = _find_block_containing(blocks, "Regular")
    if earn:
        r, h, p, y = _parse_earnings_line(earn[2], "Regular")
        row["regular_rate"], row["regular_hours"] = r, h
        row["regular_period"], row["regular_ytd"] = p, y
    hol = _find_block_containing(blocks, "Holiday")
    if hol and hol[1] < 200:
        r, h, p, y = _parse_earnings_line(hol[2], "Holiday")
        row["holiday_rate"], row["holiday_hours"] = r, h
        row["holiday_period"], row["holiday_ytd"] = p, y

    th = _find_block_containing(blocks, "Totl Hrs Worked")
    if th:
        nums = iter_adp_numbers(th[2])
        if nums:
            row["total_hours"] = nums[0]

    gp = _find_block_containing(blocks, "Gross Pay")
    if gp:
        nums = iter_adp_numbers(gp[2])
        if nums:
            row["gross_pay"] = nums[0]
    # YTD gross often sits near gross as a lone amount at similar y, x~290
    if gp:
        gy = gp[0]
        for y0, x0, _x1, _y1, t in blocks:
            if abs(y0 - gy) <= 2 and 250 <= x0 <= 330:
                n = parse_adp_number(t.replace("\n", " ").strip())
                if n:
                    row["gross_pay_ytd"] = n

    b401 = _find_block_containing(blocks, "401K W")
    if b401:
        nums = iter_adp_numbers(b401[2])
        if len(nums) >= 2:
            row["benefit_401k_w_period"], row["benefit_401k_w_ytd"] = nums[0], nums[1]
        elif len(nums) == 1:
            row["benefit_401k_w_period"] = nums[0]

    _assign_tax_rows(blocks, row, notes)

    ch = _find_block_containing(blocks, "Chsupp")
    if ch:
        nums = iter_adp_numbers(ch[2])
        if len(nums) >= 2:
            row["chsupp_period"], row["chsupp_ytd"] = nums[0], nums[1]
        elif len(nums) == 1:
            # Lone positive amount on later stubs is YTD carry (period $0)
            if nums[0].startswith("-"):
                row["chsupp_period"] = nums[0]
            else:
                row["chsupp_ytd"] = nums[0]

    np_ = _find_block_containing(blocks, "Net Pay")
    if np_:
        flat = np_[2].replace("\n", " ")
        m = re.search(r"Net Pay\s+(.+?)(?:Check\d|\Z)", flat, re.I)
        if m:
            nums = iter_adp_numbers(m.group(1))
            if nums:
                row["net_pay"] = nums[0]
        m = re.search(r"Check\d+\s+(.+?)(?:Net Check|\Z)", flat, re.I)
        if m:
            nums = iter_adp_numbers(m.group(1))
            if nums:
                # Check1 line is signed negative for a deposit; store magnitude
                row["direct_deposit"] = nums[0].lstrip("-")
    nc = _find_block_containing(blocks, "Net Check")
    if nc:
        nums = iter_adp_numbers(nc[2])
        if nums:
            row["net_check"] = nums[0]

    m = re.search(
        r"federal taxable wages this period are\s+(.+)",
        text.replace("\n", " "),
        re.I,
    )
    if m:
        nums = iter_adp_numbers(m.group(1))
        if nums:
            row["federal_taxable_wages"] = nums[0]

    # Masked deposit account near bottom
    for _y, _x, _x1, _y1, t in blocks:
        flat = t.strip()
        if re.fullmatch(r"x+\d+", flat, re.I):
            row["deposit_account_masked"] = flat
            break

    row["record_key"] = make_record_key(row)
    critical = [row["pay_date"], row["gross_pay"] or row["net_pay"], row["record_key"]]
    row["parse_ok"] = "1" if all(critical) else "0"
    if row["parse_ok"] != "1":
        notes.append("incomplete critical fields")
    row["parse_notes"] = "; ".join(notes)
    return row


def make_record_key(row: dict[str, str]) -> str:
    adv = (row.get("advice_number") or "").strip()
    if adv:
        return f"advice:{adv}"
    parts = [
        (row.get("pay_date") or "").strip(),
        (row.get("employee_name") or "").strip().upper(),
        (row.get("period_ending") or "").strip(),
    ]
    if all(parts):
        return "pay|" + "|".join(parts)
    src = (row.get("source_file") or "").strip()
    return f"file:{src}" if src else ""


def extract_pdf_row(path: Path) -> dict[str, str]:
    if fitz is None:
        raise RuntimeError("PyMuPDF is required. Install with: uv pip install pymupdf")
    doc = fitz.open(path)
    try:
        if len(doc) < 1:
            row = _empty_row(path.name)
            row["parse_notes"] = "empty pdf"
            return row
        return parse_adp_stub(doc[0], path.name)
    finally:
        doc.close()


def collect_pdfs(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(p for p in folder.glob(pattern) if p.is_file())


def load_existing_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = _empty_row()
            for c in COLUMNS:
                if c in raw and raw[c] is not None:
                    row[c] = raw[c]
            if not row["record_key"]:
                row["record_key"] = make_record_key(row)
            rows.append(row)
        return rows


def upsert_rows(existing: list[dict[str, str]], incoming: list[dict[str, str]]) -> tuple[list[dict[str, str]], int, int]:
    """Update rows with matching record_key; append new keys. Returns (rows, added, updated)."""
    by_key: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for row in existing:
        key = row.get("record_key") or make_record_key(row)
        row["record_key"] = key
        if key not in by_key:
            order.append(key)
        by_key[key] = row

    added = updated = 0
    for row in incoming:
        key = row.get("record_key") or make_record_key(row)
        row["record_key"] = key
        if not key:
            # still keep unparseable rows keyed by source file once
            key = f"file:{row.get('source_file', '')}"
            row["record_key"] = key
        if key in by_key:
            by_key[key] = row
            updated += 1
        else:
            by_key[key] = row
            order.append(key)
            added += 1

    def sort_key(r: dict[str, str]) -> tuple:
        # pay_date MM/DD/YYYY → sortable
        pd = r.get("pay_date") or ""
        m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", pd)
        iso = f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else pd
        return (iso, r.get("advice_number") or "", r.get("source_file") or "")

    rows = [by_key[k] for k in order]
    rows.sort(key=sort_key)
    return rows, added, updated


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def run(folder: Path, output: Path, recursive: bool, verbose: bool) -> int:
    if fitz is None:
        print("Error: PyMuPDF is required. Install with: uv pip install pymupdf", file=sys.stderr)
        return 1

    pdfs = collect_pdfs(folder, recursive)
    if not pdfs:
        print(f"No PDF files found in {folder}", file=sys.stderr)
        return 1

    existing = load_existing_csv(output)
    incoming: list[dict[str, str]] = []
    errors = 0
    for i, pdf in enumerate(pdfs, 1):
        if verbose:
            print(f"[{i}/{len(pdfs)}] {pdf.name}")
        try:
            row = extract_pdf_row(pdf)
            incoming.append(row)
            if row["parse_ok"] != "1":
                errors += 1
                if verbose:
                    print(f"  partial: {row['parse_notes']}")
            elif verbose:
                print(
                    f"  ok: key={row['record_key']} pay={row['pay_date']} "
                    f"gross={row['gross_pay']} net={row['net_pay']}"
                )
        except Exception as e:
            errors += 1
            row = _empty_row(pdf.name)
            row["parse_notes"] = f"error: {e}"
            row["record_key"] = f"file:{pdf.name}"
            incoming.append(row)
            print(f"  error: {pdf.name}: {e}", file=sys.stderr)

    merged, added, updated = upsert_rows(existing, incoming)
    write_csv(output, merged)
    ok = sum(1 for r in incoming if r.get("parse_ok") == "1")
    print(
        f"Wrote {len(merged)} row(s) to {output} "
        f"(scanned={len(incoming)} ok={ok} added={added} updated={updated} issues={errors})"
    )
    return 0 if errors == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract ADP paystub fields from a folder of PDFs to CSV (upsert by advice number).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python adppay2csv.py -f testdocs/pay_statements_ADP
  python adppay2csv.py -f testdocs/pay_statements_ADP -o testdocs/pay_statements_ADP/adp_pay.csv -v
  python adppay2csv.py -f ./stubs -r -o adp_pay.csv

Re-running against the same -o updates rows with the same advice number and
appends only new statements.
        """,
    )
    parser.add_argument(
        "-f",
        "--folder",
        required=True,
        metavar="DIR",
        help="Folder of ADP paystub PDFs",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="FILE",
        help="Output CSV path (default: <folder>/adp_pay.csv)",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recurse into subfolders",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"Error: not a directory: {folder}", file=sys.stderr)
        return 1
    output = Path(args.output).resolve() if args.output else folder / "adp_pay.csv"
    return run(folder, output, args.recursive, args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
