"""
Extract National Grid electric bill fields from PDF statements → CSV.

Ingest a folder of NG bill PDFs (-f). Parses account #, dates, meter readings,
balances, fees, and per-kWh rates into one row per bill.

Run: python ngbill2csv.py -h
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# Canonical CSV columns (one row per bill PDF).
COLUMNS = [
    "source_file",
    "account_number",
    "customer_name",
    "service_address",
    "bill_issued_date",
    "billing_period_start",
    "billing_period_end",
    "due_date",
    "auto_pay_date",
    "amount_due_total",
    "payment_note",
    # Account balance (classic 4-column layout)
    "previous_balance_ng",
    "previous_balance_supplier",
    "previous_balance_adjustments",
    "previous_balance_total",
    "payments_ng",
    "payments_supplier",
    "payments_adjustments",
    "payments_total",
    "current_charges_ng",
    "current_charges_supplier",
    "current_charges_adjustments",
    "current_charges_total",
    "amount_due_ng",
    "amount_due_supplier",
    "amount_due_adjustments",
    # Credit / simplified balance layout
    "previous_balance",
    "payment_received",
    "balance_forward",
    "current_charges",
    "credit_balance",
    # Meter / usage
    "meter_number",
    "rate",
    "service_period_start",
    "service_period_end",
    "billing_days",
    "current_reading",
    "current_reading_type",
    "previous_reading",
    "previous_reading_type",
    "total_usage_kwh",
    "next_scheduled_read",
    # Delivery charge rates + amounts
    "customer_charge",
    "dist_chg_rate",
    "dist_chg_amount",
    "transition_charge_rate",
    "transition_charge_amount",
    "transmission_charge_rate",
    "transmission_charge_amount",
    "energy_efficiency_chg_rate",
    "energy_efficiency_chg_amount",
    "renewable_energy_chg_rate",
    "renewable_energy_chg_amount",
    "net_meter_recovery_chg_rate",
    "net_meter_recovery_chg_amount",
    "distributed_solar_charge_rate",
    "distributed_solar_charge_amount",
    "electric_vehicle_charge_rate",
    "electric_vehicle_charge_amount",
    "net_meter_credit_rate",
    "net_meter_credit_amount",
    "total_delivery_services",
    "paperless_billing_credit",
    "transferred_aob_credit",
    "total_other_charges_adjustments",
    # Usage history daily averages (when present)
    "daily_avg_kwh_prior",
    "daily_avg_kwh_current",
    "daily_avg_cost_prior",
    "daily_avg_cost_current",
    "parse_ok",
    "parse_notes",
]

# Charge line label → (rate_col, amount_col)
CHARGE_LINES = {
    "Customer Charge": ("customer_charge", None),  # amount only in "Customer Charge X.XX"
    "Dist Chg": ("dist_chg_rate", "dist_chg_amount"),
    "Transition Charge": ("transition_charge_rate", "transition_charge_amount"),
    "Transmission Charge": ("transmission_charge_rate", "transmission_charge_amount"),
    "Energy Efficiency Chg": ("energy_efficiency_chg_rate", "energy_efficiency_chg_amount"),
    "Renewable Energy Chg": ("renewable_energy_chg_rate", "renewable_energy_chg_amount"),
    "Net Meter Recovery Chg": ("net_meter_recovery_chg_rate", "net_meter_recovery_chg_amount"),
    "Distributed Solar Charge": ("distributed_solar_charge_rate", "distributed_solar_charge_amount"),
    "Electric Vehicle Charge": ("electric_vehicle_charge_rate", "electric_vehicle_charge_amount"),
    "Net Met Cr": ("net_meter_credit_rate", "net_meter_credit_amount"),
}

MONEY = r"-?\$?\s*-?[\d,]+\.\d{2}"
MONEY_CAP = re.compile(r"-?\$?\s*(-?[\d,]+\.\d{2})")
DATE_MDY = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}"
)
DATE_MD = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}"
)


def _money(s: str | None) -> str:
    if not s:
        return ""
    s = s.strip().replace(",", "").replace("$", "").replace(" ", "")
    # Handle "-$ 1,234.56" / "-$1234.56" already stripped partially
    return s


def _first_money(s: str) -> str:
    m = MONEY_CAP.search(s)
    return _money(m.group(1)) if m else ""


def _all_money(s: str) -> list[str]:
    return [_money(x) for x in MONEY_CAP.findall(s)]


def _empty_row(source: str) -> dict[str, str]:
    row = {c: "" for c in COLUMNS}
    row["source_file"] = source
    row["parse_ok"] = "0"
    return row


def extract_pdf_text(path: Path) -> str:
    from doc2text import extract_pdf_pages

    pages = extract_pdf_pages(path)
    return "\n".join(t for _, t in pages)


def parse_ng_bill(text: str, source_file: str) -> dict[str, str]:
    """Parse National Grid residential electric bill text into a flat dict."""
    row = _empty_row(source_file)
    notes: list[str] = []
    # Normalize odd spaces / NBSP
    text = text.replace("\xa0", " ").replace("\u2013", "-")

    # --- Account number (first occurrence after ACCOUNT NUMBER) ---
    m = re.search(
        r"ACCOUNT NUMBER\s+(\d{5}-\d{5})\s+(.+?)(?:\n|$)",
        text,
        re.IGNORECASE,
    )
    if m:
        row["account_number"] = m.group(1).strip()
        rest = m.group(2).strip()
        # Classic: "Jan 3, 2025 $ 375.73" or "No payment due $ 0.00"
        dm = DATE_MDY.search(rest)
        if dm:
            row["due_date"] = dm.group(0)
        if re.search(r"No\s+payment\s+due", rest, re.I):
            row["payment_note"] = "No payment due"
        amounts = _all_money(rest)
        if amounts:
            row["amount_due_total"] = amounts[-1]
    else:
        notes.append("account_number missing")

    # --- Billing period ---
    m = re.search(
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4})\s+to\s+"
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4})",
        text,
    )
    if m:
        row["billing_period_start"] = m.group(1)
        row["billing_period_end"] = m.group(2)
    else:
        notes.append("billing_period missing")

    # --- Bill issued ---
    m = re.search(r"DATE BILL ISSUED\s*\n\s*([^\n]+)", text, re.I)
    if m:
        row["bill_issued_date"] = m.group(1).strip()

    # --- Customer / service address (between SERVICE FOR and BILLING PERIOD or ACCOUNT BALANCE) ---
    m = re.search(
        r"SERVICE FOR\s*\n(.*?)(?:\nBILLING PERIOD|\nACCOUNT NUMBER|\nACCOUNT BALANCE)",
        text,
        re.S | re.I,
    )
    if m:
        lines = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
        if lines:
            row["customer_name"] = lines[0]
            # Drop *SOLAR* marker into notes; keep address lines
            addr = [ln for ln in lines[1:] if ln.upper() != "*SOLAR*"]
            if any(ln.upper() == "*SOLAR*" for ln in lines[1:]):
                notes.append("solar")
            row["service_address"] = ", ".join(addr)

    # --- Auto-pay date ---
    m = re.search(
        r"Automated Payment Transfer will occur on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
        re.I,
    )
    if m:
        row["auto_pay_date"] = m.group(1)

    # --- Classic 4-column balance block ---
    m = re.search(
        r"Previous Balance\s+(" + MONEY + r")\s+(" + MONEY + r")\s+(" + MONEY + r")\s+(" + MONEY + r")",
        text,
    )
    if m:
        row["previous_balance_ng"] = _money(m.group(1))
        row["previous_balance_supplier"] = _money(m.group(2))
        row["previous_balance_adjustments"] = _money(m.group(3))
        row["previous_balance_total"] = _money(m.group(4))
        row["previous_balance"] = row["previous_balance_total"]
    else:
        # Simplified: "Previous Balance      -1,076.33"
        m = re.search(r"Previous Balance\s+(" + MONEY + r")", text)
        if m:
            row["previous_balance"] = _money(m.group(1))

    m = re.search(
        r"Payment\(s\) Received\s+-\s*("
        + MONEY
        + r")\s+-\s*("
        + MONEY
        + r")\s+-\s*("
        + MONEY
        + r")\s+-\s*("
        + MONEY
        + r")",
        text,
    )
    if m:
        row["payments_ng"] = _money(m.group(1))
        row["payments_supplier"] = _money(m.group(2))
        row["payments_adjustments"] = _money(m.group(3))
        row["payments_total"] = _money(m.group(4))
        row["payment_received"] = row["payments_total"]
    else:
        m = re.search(
            r"Payment Received.*?-\s*(" + MONEY + r")",
            text,
            re.S,
        )
        if m:
            row["payment_received"] = _money(m.group(1))

    m = re.search(
        r"Current Charges\s+(" + MONEY + r")\s+(" + MONEY + r")\s+(" + MONEY + r")\s+(" + MONEY + r")",
        text,
    )
    if m:
        row["current_charges_ng"] = _money(m.group(1))
        row["current_charges_supplier"] = _money(m.group(2))
        row["current_charges_adjustments"] = _money(m.group(3))
        row["current_charges_total"] = _money(m.group(4))
        row["current_charges"] = row["current_charges_total"]
    else:
        m = re.search(r"Current Charges\s+(" + MONEY + r")", text)
        if m:
            row["current_charges"] = _money(m.group(1))

    m = re.search(
        r"Amount Due\s*\n\s*\$?\s*("
        + MONEY
        + r")\s+\$?\s*("
        + MONEY
        + r")\s+-?\$?\s*("
        + MONEY
        + r")\s+\$?\s*("
        + MONEY
        + r")",
        text,
    )
    if m:
        row["amount_due_ng"] = _money(m.group(1))
        row["amount_due_supplier"] = _money(m.group(2))
        row["amount_due_adjustments"] = _money(m.group(3))
        if not row["amount_due_total"]:
            row["amount_due_total"] = _money(m.group(4))

    m = re.search(r"Balance Forward\s+(" + MONEY + r")", text)
    if m:
        row["balance_forward"] = _money(m.group(1))

    m = re.search(r"Credit Balance\s*\n\s*-?\$?\s*(" + MONEY + r")", text, re.I)
    if m:
        # Preserve sign from surrounding "-$"
        val = _money(m.group(1))
        # Look at a slightly wider window for leading minus
        ctx = re.search(r"Credit Balance\s*\n\s*([^\n]+)", text, re.I)
        if ctx and "-" in ctx.group(1) and not val.startswith("-"):
            val = "-" + val
        row["credit_balance"] = val
        if not row["amount_due_total"]:
            row["amount_due_total"] = val

    # --- Meter / usage line ---
    # "Nov 7 - Dec 10     33 44031 Actual 43051 Actual 980 kWh"
    # "Jun 10 - Jul 13     34 999467 Actual 2257 Actual -2790 kWh"
    m = re.search(
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2})\s*-\s*"
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2})\s+"
        r"(\d+)\s+"
        r"(-?\d+)\s+(Actual|Estimated)\s+"
        r"(-?\d+)\s+(Actual|Estimated)\s+"
        r"(-?[\d,]+)\s*kWh",
        text,
        re.I,
    )
    if m:
        row["service_period_start"] = m.group(1)
        row["service_period_end"] = m.group(2)
        row["billing_days"] = m.group(3)
        row["current_reading"] = m.group(4)
        row["current_reading_type"] = m.group(5)
        row["previous_reading"] = m.group(6)
        row["previous_reading_type"] = m.group(7)
        row["total_usage_kwh"] = m.group(8).replace(",", "")
    else:
        notes.append("meter_readings missing")

    m = re.search(r"METER NUMBER\s+(\S+)", text, re.I)
    if m:
        row["meter_number"] = m.group(1)

    m = re.search(
        r"NEXT SCHEDULED READ DATE ON OR ABOUT\s+([A-Za-z]+\s+\d{1,2})",
        text,
        re.I,
    )
    if m:
        row["next_scheduled_read"] = m.group(1)

    m = re.search(r"RATE\s+(.+?)(?:\n|$)", text, re.I)
    if m:
        row["rate"] = re.sub(r"\s+", " ", m.group(1)).strip()

    # --- Charge lines: "Dist Chg 0.08549 x 980 kWh 83.77" or "Customer Charge 10.00" ---
    for label, (rate_col, amt_col) in CHARGE_LINES.items():
        if label == "Customer Charge":
            m = re.search(rf"{re.escape(label)}\s+({MONEY})", text)
            if m:
                row["customer_charge"] = _money(m.group(1))
            continue
        m = re.search(
            rf"{re.escape(label)}\s+(-?[\d.]+)\s+x\s+(-?[\d,]+)\s*kWh\s+({MONEY})",
            text,
        )
        if m:
            if rate_col:
                row[rate_col] = m.group(1)
            if amt_col:
                row[amt_col] = _money(m.group(3))

    m = re.search(r"Total Delivery Services\s+-?\$?\s*(" + MONEY + r")", text, re.I)
    if m:
        val = _money(m.group(1))
        ctx = re.search(r"Total Delivery Services\s+([^\n]+)", text, re.I)
        if ctx and "-" in ctx.group(1).replace(val, "") and not val.startswith("-"):
            # "-$ 878.21"
            if re.search(r"-\s*\$", ctx.group(1)) or ctx.group(1).strip().startswith("-"):
                val = "-" + val.lstrip("-")
        # Prefer capturing with sign from raw
        m2 = re.search(r"Total Delivery Services\s+(-?\$?\s*-?[\d,]+\.\d{2})", text, re.I)
        if m2:
            raw = m2.group(1).replace("$", "").replace(" ", "").replace(",", "")
            row["total_delivery_services"] = raw
        else:
            row["total_delivery_services"] = val

    m = re.search(r"Paperless Billing Credit\s+(" + MONEY + r")", text, re.I)
    if m:
        row["paperless_billing_credit"] = _money(m.group(1))

    m = re.search(r"Transferred AOB Credit\s+(" + MONEY + r")", text, re.I)
    if m:
        row["transferred_aob_credit"] = _money(m.group(1))

    m = re.search(
        r"Total Other Charges/Adjustments\s+-?\$?\s*(" + MONEY + r")",
        text,
        re.I,
    )
    if m:
        m2 = re.search(
            r"Total Other Charges/Adjustments\s+(-?\$?\s*-?[\d,]+\.\d{2})",
            text,
            re.I,
        )
        if m2:
            row["total_other_charges_adjustments"] = (
                m2.group(1).replace("$", "").replace(" ", "").replace(",", "")
            )
        else:
            row["total_other_charges_adjustments"] = _money(m.group(1))

    # Daily averages: "kWh 16.5 29.7" / "Cost $ 5.16 $ 11.38"
    m = re.search(r"Daily Averages[^\n]*\n\s*kWh\s+([-\d.]+)(?:\s+([-\d.]+))?", text)
    if m:
        row["daily_avg_kwh_prior"] = m.group(1)
        if m.group(2):
            row["daily_avg_kwh_current"] = m.group(2)
    m = re.search(
        r"Cost\s+\$?\s*([-\d.]+)(?:\s+\$?\s*([-\d.]+))?",
        text,
    )
    if m and "daily_avg" in text.lower() or row["daily_avg_kwh_prior"]:
        # Prefer the Cost line that follows Daily Averages
        m = re.search(
            r"Daily Averages.*?\n\s*kWh[^\n]*\n\s*Cost\s+\$?\s*([-\d.]+)(?:\s+\$?\s*([-\d.]+))?",
            text,
            re.S,
        )
        if m:
            row["daily_avg_cost_prior"] = m.group(1)
            if m.group(2):
                row["daily_avg_cost_current"] = m.group(2)

    critical = [
        row["account_number"],
        row["billing_period_start"],
        row["total_usage_kwh"] or row["current_charges"] or row["amount_due_total"],
    ]
    row["parse_ok"] = "1" if all(critical) else "0"
    if not all(critical) and "incomplete" not in notes:
        notes.append("incomplete critical fields")
    row["parse_notes"] = "; ".join(notes)
    return row


def collect_pdfs(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(p for p in folder.glob(pattern) if p.is_file() and not p.stem.endswith("_ext"))


def run(folder: Path, output: Path, recursive: bool, verbose: bool) -> int:
    pdfs = collect_pdfs(folder, recursive)
    if not pdfs:
        print(f"No PDF files found in {folder}", file=sys.stderr)
        return 1

    rows: list[dict[str, str]] = []
    errors = 0
    for i, pdf in enumerate(pdfs, 1):
        if verbose:
            print(f"[{i}/{len(pdfs)}] {pdf.name}")
        try:
            text = extract_pdf_text(pdf)
            if not text.strip():
                row = _empty_row(pdf.name)
                row["parse_notes"] = "no text layer"
                rows.append(row)
                errors += 1
                print(f"  no text: {pdf.name}", file=sys.stderr)
                continue
            row = parse_ng_bill(text, pdf.name)
            rows.append(row)
            if row["parse_ok"] != "1":
                errors += 1
                if verbose:
                    print(f"  partial: {row['parse_notes']}")
            elif verbose:
                print(
                    f"  ok: acct={row['account_number']} "
                    f"usage={row['total_usage_kwh']} kWh "
                    f"due={row['amount_due_total']}"
                )
        except Exception as e:
            errors += 1
            row = _empty_row(pdf.name)
            row["parse_notes"] = f"error: {e}"
            rows.append(row)
            print(f"  error: {pdf.name}: {e}", file=sys.stderr)

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    ok = sum(1 for r in rows if r["parse_ok"] == "1")
    print(f"Wrote {len(rows)} row(s) to {output} (ok={ok}, issues={errors})")
    return 0 if errors == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract National Grid bill statement fields from PDFs to CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ngbill2csv.py -f testdocs/NGBills
  python ngbill2csv.py -f testdocs/NGBills -o testdocs/ng_bills.csv -v
  python ngbill2csv.py -f ./bills -r -o ng_bills.csv
        """,
    )
    parser.add_argument(
        "-f",
        "--folder",
        required=True,
        metavar="DIR",
        help="Folder of National Grid bill PDFs",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="FILE",
        help="Output CSV path (default: <folder>/ng_bills.csv)",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recurse into subfolders",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"Error: not a directory: {folder}", file=sys.stderr)
        raise SystemExit(1)
    output = Path(args.output).resolve() if args.output else folder / "ng_bills.csv"
    raise SystemExit(run(folder, output, args.recursive, args.verbose))


if __name__ == "__main__":
    main()
