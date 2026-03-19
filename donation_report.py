"""
Donation Report Builder
=======================
Takes the list of CheckData objects produced by check_processor.py and:
  1. Categorizes every gift into one of six sections
  2. Builds a complete HTML email / report page

Six-section layout
------------------
  1. Individual Gifts
  2. Donor-Advised Fund (DAF) Gifts
  3. Corporate Gifts
  4. Foundation Gifts
  5. Gifts with Attached Letters   ← any type that arrived with a cover letter
  6. Summary                       ← counts + subtotals per category + grand total

Usage
-----
    from check_processor import process_pdf
    from donation_report import generate_report

    checks = process_pdf("batch_scan.pdf")
    generate_report(checks, "report.html")
"""

from datetime import date
from pathlib import Path
from typing import Sequence

from check_processor import CheckData


# ── Section registry ──────────────────────────────────────────────────────────

# (bucket_key, display_label)  — order determines report section order
_SECTIONS: list[tuple[str, str]] = [
    ("individual",  "Individual Gifts"),
    ("daf",         "Donor-Advised Fund Gifts"),
    ("corporate",   "Corporate Gifts"),
    ("foundation",  "Foundation Gifts"),
    ("letter",      "Gifts with Attached Letters"),
]


# ── Categorization ────────────────────────────────────────────────────────────

def categorize(checks: Sequence[CheckData]) -> dict[str, list[CheckData]]:
    """
    Distribute checks across section buckets.

    A check with has_attached_letter=True also appears in the "letter"
    bucket regardless of its donor_type, so staff know to follow up.
    """
    buckets: dict[str, list[CheckData]] = {key: [] for key, _ in _SECTIONS}

    for c in checks:
        if not c.donor_name:
            continue  # page contained no check
        dtype = c.donor_type if c.donor_type in buckets else "individual"
        buckets[dtype].append(c)
        if c.has_attached_letter:
            buckets["letter"].append(c)

    return buckets


# ── HTML fragments ────────────────────────────────────────────────────────────

_CSS = """
  * { box-sizing: border-box; }
  body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 14px;
    color: #222;
    max-width: 960px;
    margin: 0 auto;
    padding: 24px;
    background: #fff;
  }
  h1 {
    color: #1a3a5c;
    border-bottom: 3px solid #1a3a5c;
    padding-bottom: 10px;
    margin-bottom: 4px;
  }
  .report-meta { color: #555; margin-bottom: 32px; }
  h2 {
    color: #1a3a5c;
    margin-top: 36px;
    border-left: 5px solid #1a3a5c;
    padding-left: 12px;
    font-size: 16px;
  }
  table {
    border-collapse: collapse;
    width: 100%;
    margin-top: 10px;
    font-size: 13px;
  }
  th {
    background: #1a3a5c;
    color: #fff;
    padding: 8px 12px;
    text-align: left;
    white-space: nowrap;
  }
  td { padding: 7px 12px; border-bottom: 1px solid #ddd; vertical-align: top; }
  tr:nth-child(even) td { background: #f5f8fc; }
  .subtotal td {
    font-weight: bold;
    border-top: 2px solid #1a3a5c;
    background: #eaf0f8 !important;
  }
  .grand-total td {
    font-weight: bold;
    font-size: 14px;
    border-top: 3px solid #1a3a5c;
    background: #d0dff0 !important;
  }
  .num { text-align: right; }
  .center { text-align: center; }
  .empty { color: #999; font-style: italic; padding: 12px; }
  .footer {
    margin-top: 48px;
    font-size: 11px;
    color: #aaa;
    border-top: 1px solid #ddd;
    padding-top: 10px;
  }
"""


def _fmt(c: CheckData) -> str:
    """Return a display-ready amount string for a check."""
    if c.amount_str:
        return c.amount_str
    return f"${c.amount:,.2f}" if c.amount else "—"


def _section_table(checks: list[CheckData]) -> str:
    if not checks:
        return '<p class="empty">No gifts in this category.</p>'

    rows = []
    for c in checks:
        letter_mark = "&#10003;" if c.has_attached_letter else ""
        rows.append(
            f"<tr>"
            f"<td>{c.donor_name}</td>"
            f"<td>{c.donor_address or '—'}</td>"
            f'<td class="num">{_fmt(c)}</td>'
            f"<td>{c.date or '—'}</td>"
            f"<td>{c.memo or '—'}</td>"
            f'<td class="center">{letter_mark}</td>'
            f"</tr>"
        )

    subtotal = sum(c.amount for c in checks)
    rows.append(
        f'<tr class="subtotal">'
        f"<td colspan='2'>Subtotal ({len(checks)} gift{'s' if len(checks) != 1 else ''})</td>"
        f'<td class="num">${subtotal:,.2f}</td>'
        f"<td colspan='3'></td>"
        f"</tr>"
    )

    return (
        "<table>"
        "<thead><tr>"
        "<th>Donor</th><th>Address</th><th>Amount</th>"
        "<th>Date</th><th>Memo</th><th>Letter</th>"
        "</tr></thead>"
        "<tbody>" + "\n".join(rows) + "</tbody>"
        "</table>"
    )


def _summary_table(
    buckets: dict[str, list[CheckData]],
    all_valid: list[CheckData],
) -> str:
    rows = []
    for key, label in _SECTIONS:
        items = buckets[key]
        subtotal = sum(c.amount for c in items)
        rows.append(
            f"<tr>"
            f"<td>{label}</td>"
            f'<td class="center">{len(items)}</td>'
            f'<td class="num">${subtotal:,.2f}</td>'
            f"</tr>"
        )

    grand_count = len(all_valid)
    grand_total = sum(c.amount for c in all_valid)
    rows.append(
        f'<tr class="grand-total">'
        f"<td>GRAND TOTAL</td>"
        f'<td class="center">{grand_count}</td>'
        f'<td class="num">${grand_total:,.2f}</td>'
        f"</tr>"
    )

    return (
        "<table>"
        "<thead><tr><th>Category</th><th>Count</th><th>Total</th></tr></thead>"
        "<tbody>" + "\n".join(rows) + "</tbody>"
        "</table>"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def build_html_email(
    checks: Sequence[CheckData],
    report_date: date | None = None,
) -> str:
    """
    Build and return a complete HTML donation-report email.

    Parameters
    ----------
    checks : Sequence[CheckData]
        Output from check_processor.process_pdf().
    report_date : date | None
        Date shown in the report header (defaults to today).

    Returns
    -------
    str
        A self-contained HTML document ready to send or save.
    """
    report_date = report_date or date.today()
    all_valid = [c for c in checks if c.donor_name]
    buckets = categorize(all_valid)

    sections_html = ""
    for key, label in _SECTIONS:
        sections_html += f"<h2>{label}</h2>\n"
        sections_html += _section_table(buckets[key]) + "\n"

    sections_html += "<h2>Summary</h2>\n"
    sections_html += _summary_table(buckets, all_valid) + "\n"

    formatted_date = report_date.strftime("%B %d, %Y")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Donation Report — {formatted_date}</title>
  <style>{_CSS}</style>
</head>
<body>
  <h1>Donation Report</h1>
  <p class="report-meta">
    <strong>Report Date:</strong> {formatted_date} &nbsp;|&nbsp;
    <strong>Total Gifts:</strong> {len(all_valid)} &nbsp;|&nbsp;
    <strong>Grand Total:</strong> ${sum(c.amount for c in all_valid):,.2f}
  </p>

  {sections_html}

  <div class="footer">
    Generated automatically from scanned check PDF using Claude Vision AI.
  </div>
</body>
</html>"""


def generate_report(
    checks: Sequence[CheckData],
    output_path: str | Path = "donation_report.html",
    report_date: date | None = None,
) -> Path:
    """
    Write the HTML donation report to disk.

    Parameters
    ----------
    checks : Sequence[CheckData]
        Output from check_processor.process_pdf().
    output_path : str | Path
        Destination file path (default: donation_report.html).
    report_date : date | None
        Date shown in the report header (defaults to today).

    Returns
    -------
    Path
        Resolved path to the written file.
    """
    output_path = Path(output_path)
    html = build_html_email(checks, report_date)
    output_path.write_text(html, encoding="utf-8")
    print(f"Donation report written to: {output_path}")
    return output_path
