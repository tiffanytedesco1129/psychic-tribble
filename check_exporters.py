"""
check_exporters.py — Export CheckData to upload-ready CSV files.

Two formats
-----------
  Sage   : used by Finance (Sage accounting)
  NXT    : used by Development (Blackbaud NXT)

Both include: name, address, amount, date, memo, check number.

Usage
-----
    from check_exporters import export_sage_csv, export_nxt_csv
    export_sage_csv(checks, "sage_upload.csv")
    export_nxt_csv(checks, "nxt_upload.csv")
"""

import csv
from pathlib import Path
from typing import Sequence

from check_processor import CheckData


def _valid(checks: Sequence[CheckData]) -> list[CheckData]:
    return [c for c in checks if c.donor_name]


def _amount_fmt(c: CheckData) -> str:
    """Return a plain numeric string suitable for import (no $ or commas)."""
    return f"{c.amount:.2f}"


# ── Sage ──────────────────────────────────────────────────────────────────────

_SAGE_HEADERS = [
    "Name",
    "Address",
    "Amount",
    "Date",
    "Memo",
    "Check No",
]


def export_sage_csv(
    checks: Sequence[CheckData],
    output_path: str | Path = "sage_upload.csv",
) -> Path:
    """
    Write a Sage-compatible CSV for Finance.

    Columns: Name | Address | Amount | Date | Memo | Check No
    """
    output_path = Path(output_path)
    rows = _valid(checks)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_SAGE_HEADERS)
        for c in rows:
            writer.writerow([
                c.donor_name,
                c.donor_address,
                _amount_fmt(c),
                c.date,
                c.memo,
                c.check_number,
            ])

    print(f"Sage CSV written to: {output_path}  ({len(rows)} records)")
    return output_path


# ── Blackbaud NXT ─────────────────────────────────────────────────────────────

_NXT_HEADERS = [
    "Constituent Name",
    "Address",
    "Gift Amount",
    "Gift Date",
    "Gift Memo",
    "Check Number",
]


def export_nxt_csv(
    checks: Sequence[CheckData],
    output_path: str | Path = "nxt_upload.csv",
) -> Path:
    """
    Write a Blackbaud NXT-compatible CSV for Development.

    Columns: Constituent Name | Address | Gift Amount | Gift Date | Gift Memo | Check Number
    """
    output_path = Path(output_path)
    rows = _valid(checks)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_NXT_HEADERS)
        for c in rows:
            writer.writerow([
                c.donor_name,
                c.donor_address,
                _amount_fmt(c),
                c.date,
                c.memo,
                c.check_number,
            ])

    print(f"NXT CSV written to:  {output_path}  ({len(rows)} records)")
    return output_path
