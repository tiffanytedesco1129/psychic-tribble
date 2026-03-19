"""
Donation Report Generator
=========================
Takes the structured data returned by check_processor.extract_check_data()
and produces:

  1. A plain-text summary (for quick review / logging).
  2. An HTML email body matching the Midnight Mission gift-processing format
     used by Tiffany's team.

Category rules
--------------
  $1,000+        → Section 1  (High-Touch – Tiffany)
  Corporate      → Section 2  (Flag for Brent / Robert)
  Foundation     → Section 3  (Flag for Val / Abby)
  $500–$999      → Section 4  (Research + Assignment)
  DAF            → Section 5  (Acknowledgement Required)
  All gifts      → Section 6  (Opportunity Scan – Tiffany + Val)

A single gift can appear in multiple sections (e.g. a $2,000 corporate gift
appears in both Section 1 and Section 2).
"""

from __future__ import annotations

import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fmt_currency(amount: float | None) -> str:
    if amount is None:
        return "$—"
    return f"${amount:,.2f}"


def _display_name(check: dict) -> str:
    """Return the most useful display name for a check."""
    if check.get("is_foundation") and check.get("foundation_name"):
        return check["foundation_name"]
    if check.get("is_daf") and check.get("daf_sponsor"):
        donor = check.get("donor_name", "")
        sponsor = check["daf_sponsor"]
        return f"{donor} ({sponsor})" if donor else sponsor
    if check.get("is_corporate") and check.get("company_name"):
        return check["company_name"]
    return check.get("donor_name") or "Unknown Donor"


def _letter_summary(check: dict, letters: list[dict]) -> str:
    idx = check.get("associated_letter_index")
    if idx is None or idx >= len(letters):
        return ""
    letter = letters[idx]
    parts = []
    if letter.get("sender_organization"):
        parts.append(letter["sender_organization"])
    elif letter.get("sender_name"):
        parts.append(letter["sender_name"])
    ltype = letter.get("letter_type", "letter")
    parts.append(f"({ltype})")
    if letter.get("notes"):
        parts.append(f"— {letter['notes']}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Categorisation
# ---------------------------------------------------------------------------

def _categorise(checks: list[dict]) -> dict[str, list[dict]]:
    cats: dict[str, list[dict]] = {
        "major": [],        # ≥ $1,000
        "corporate": [],
        "foundation": [],
        "mid": [],          # $500–$999
        "daf": [],
        "all": list(checks),
    }
    for c in checks:
        amt = c.get("amount") or 0
        if amt >= 1000:
            cats["major"].append(c)
        if c.get("is_corporate"):
            cats["corporate"].append(c)
        if c.get("is_foundation"):
            cats["foundation"].append(c)
        if 500 <= amt < 1000:
            cats["mid"].append(c)
        if c.get("is_daf"):
            cats["daf"].append(c)
    return cats


# ---------------------------------------------------------------------------
# HTML builder helpers
# ---------------------------------------------------------------------------

_CSS = """
body { font-family: Arial, sans-serif; font-size: 14px; color: #222; margin: 0; padding: 20px; }
h1 { color: #1a3a5c; font-size: 20px; margin-bottom: 4px; }
h2 { color: #1a3a5c; font-size: 16px; border-bottom: 2px solid #1a3a5c; padding-bottom: 4px; margin-top: 30px; }
h3 { color: #555; font-size: 14px; margin-top: 16px; margin-bottom: 4px; }
table { border-collapse: collapse; width: 100%; margin-top: 8px; }
th { background: #1a3a5c; color: #fff; text-align: left; padding: 8px 10px; font-size: 13px; }
td { border: 1px solid #ddd; padding: 7px 10px; vertical-align: top; font-size: 13px; }
tr:nth-child(even) td { background: #f5f8fc; }
.summary-box { background: #f0f4f9; border: 1px solid #c5d4e8; border-radius: 6px;
               padding: 14px 20px; margin: 16px 0; display: inline-block; }
.summary-box ul { margin: 6px 0; padding-left: 20px; }
.note { color: #555; font-style: italic; font-size: 12px; margin-top: 6px; }
.footer { margin-top: 30px; border-top: 1px solid #ddd; padding-top: 12px;
          font-size: 13px; color: #444; }
.highlight { font-weight: bold; color: #1a3a5c; }
""".strip()


def _table(headers: list[str], rows: list[list[str]], empty_msg: str = "No items.") -> str:
    if not rows:
        return f'<p class="note">{empty_msg}</p>'
    th = "".join(f"<th>{h}</th>" for h in headers)
    body_rows = ""
    for row in rows:
        tds = "".join(f"<td>{cell}</td>" for cell in row)
        body_rows += f"<tr>{tds}</tr>"
    return f"<table><thead><tr>{th}</tr></thead><tbody>{body_rows}</tbody></table>"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_report(
    data: dict,
    period_start: str | None = None,
    period_end: str | None = None,
) -> tuple[str, str]:
    """
    Build plain-text and HTML versions of the donation report.

    Parameters
    ----------
    data:
        Output from check_processor.extract_check_data().
    period_start / period_end:
        Human-readable date strings for the reporting period header.
        Defaults to today's date if not supplied.

    Returns
    -------
    (plain_text, html) tuple
    """
    checks: list[dict] = data.get("checks", [])
    letters: list[dict] = data.get("letters", [])

    today = datetime.date.today().strftime("%B %d, %Y")
    period = f"{period_start or today} – {period_end or today}"

    cats = _categorise(checks)

    total_gifts = len(checks)
    total_revenue = sum(c.get("amount") or 0 for c in checks)
    num_major = len(cats["major"])
    num_daf = len(cats["daf"])

    # Notable new donors: anyone giving ≥ $500 who is not a foundation/daf/corporate
    notable = [
        c for c in checks
        if (c.get("amount") or 0) >= 500
        and not c.get("is_foundation")
        and not c.get("is_daf")
    ]

    # -----------------------------------------------------------------------
    # HTML body
    # -----------------------------------------------------------------------
    html_parts: list[str] = [
        f"<html><head><style>{_CSS}</style></head><body>",
        f"<h1>Midnight Mission — Gift Processing Report</h1>",
        f"<p><strong>Reporting Period:</strong> {period}</p>",

        # Summary snapshot
        '<h2>Summary Snapshot</h2>',
        '<div class="summary-box"><ul>',
        f"<li><strong>Total Gifts:</strong> {total_gifts}</li>",
        f"<li><strong>Total Revenue:</strong> {_fmt_currency(total_revenue)}</li>",
        f"<li><strong># of Gifts $1,000+:</strong> {num_major}</li>",
        f"<li><strong># of DAF Gifts:</strong> {num_daf}</li>",
        f"<li><strong>Notable New Donors:</strong> {len(notable)}</li>",
        "</ul></div>",
    ]

    # -----------------------------------------------------------------------
    # Section 1 — $1,000+ Gifts
    # -----------------------------------------------------------------------
    html_parts += [
        '<h2>1. $1,000+ Gifts <span style="font-weight:normal;font-size:13px;">'
        '(High-Touch – Tiffany)</span></h2>',
    ]
    s1_rows = []
    for c in cats["major"]:
        name = _display_name(c)
        amt = _fmt_currency(c.get("amount"))
        gtype = (
            "DAF" if c.get("is_daf")
            else "Foundation" if c.get("is_foundation")
            else "Corporate" if c.get("is_corporate")
            else "Individual"
        )
        letter = _letter_summary(c, letters)
        s1_rows.append([
            name, amt, gtype,
            "Call + Letter + Email",
            "Pending",
            letter or "—",
        ])
    html_parts.append(
        _table(
            ["Donor Name", "Amount", "Type", "Action", "Status", "Letter / Notes"],
            s1_rows,
            "No gifts at $1,000+ this period.",
        )
    )
    html_parts.append(
        '<p class="note">Calls completed within 48 hours where possible. '
        "Personalized acknowledgements sent separately from receipts.</p>"
    )

    # -----------------------------------------------------------------------
    # Section 2 — Corporate Gifts
    # -----------------------------------------------------------------------
    html_parts += [
        '<h2>2. Corporate Gifts <span style="font-weight:normal;font-size:13px;">'
        '(Flag for Brent / Robert)</span></h2>',
    ]
    s2_rows = []
    for c in cats["corporate"]:
        name = _display_name(c)
        company = c.get("company_name") or name
        amt = _fmt_currency(c.get("amount"))
        s2_rows.append([name, company, amt, "Thank + Awareness", "Brent / Robert"])
    html_parts.append(
        _table(
            ["Donor", "Company", "Amount", "Action Needed", "Owner"],
            s2_rows,
            "No corporate gifts this period.",
        )
    )
    html_parts.append(
        '<p class="note">Identify partnership, sponsorship, or in-kind opportunities where applicable.</p>'
    )

    # -----------------------------------------------------------------------
    # Section 3 — Foundation Gifts
    # -----------------------------------------------------------------------
    html_parts += [
        '<h2>3. Foundation Gifts <span style="font-weight:normal;font-size:13px;">'
        '(Flag for Val / Abby)</span></h2>',
    ]
    s3_rows = []
    for c in cats["foundation"]:
        fname = c.get("foundation_name") or _display_name(c)
        amt = _fmt_currency(c.get("amount"))
        letter = _letter_summary(c, letters) or "—"
        s3_rows.append([fname, amt, letter, "Review grant requirements", "Val / Abby"])
    html_parts.append(
        _table(
            ["Foundation", "Amount", "Context / Letter", "Next Step", "Owner"],
            s3_rows,
            "No foundation gifts this period.",
        )
    )

    # -----------------------------------------------------------------------
    # Section 4 — $500–$999 Gifts
    # -----------------------------------------------------------------------
    html_parts += [
        '<h2>4. $500–$999 Gifts <span style="font-weight:normal;font-size:13px;">'
        '(Research + Assignment)</span></h2>',
    ]
    s4_rows = []
    for c in cats["mid"]:
        name = _display_name(c)
        amt = _fmt_currency(c.get("amount"))
        memo = c.get("memo") or "—"
        s4_rows.append([name, amt, memo, "TBD", "Acknowledge + Research"])
    html_parts.append(
        _table(
            ["Donor", "Amount", "Notes", "Assigned To", "Action"],
            s4_rows,
            "No gifts in the $500–$999 range this period.",
        )
    )

    # -----------------------------------------------------------------------
    # Section 5 — DAF Gifts
    # -----------------------------------------------------------------------
    html_parts += [
        '<h2>5. DAF Gifts <span style="font-weight:normal;font-size:13px;">'
        '(Acknowledgement Required – No Tax Receipt)</span></h2>',
    ]
    s5_rows = []
    for c in cats["daf"]:
        name = c.get("donor_name") or "Unknown"
        sponsor = c.get("daf_sponsor") or "Unknown Sponsor"
        amt = _fmt_currency(c.get("amount"))
        s5_rows.append([name, sponsor, amt, "No", "Send acknowledgement only"])
    html_parts.append(
        _table(
            ["Donor Name", "DAF Sponsor", "Amount", "Acknowledged (Y/N)", "Notes"],
            s5_rows,
            "No DAF gifts this period.",
        )
    )
    html_parts.append(
        '<p class="note"><strong>Reminder:</strong> DAF gifts should always receive an '
        "acknowledgement, but <em>no</em> tax receipt.</p>"
    )

    # -----------------------------------------------------------------------
    # Section 6 — Opportunity Scan
    # -----------------------------------------------------------------------
    html_parts += [
        '<h2>6. Opportunity Scan <span style="font-weight:normal;font-size:13px;">'
        '(Tiffany + Val)</span></h2>',
    ]
    # Surface gifts ≥ $250 as potential opportunities
    opp_checks = [c for c in checks if (c.get("amount") or 0) >= 250]
    s6_rows = []
    for c in opp_checks:
        name = _display_name(c)
        amt = _fmt_currency(c.get("amount"))
        amount_val = c.get("amount") or 0
        if amount_val >= 1000 and not c.get("is_daf") and not c.get("is_foundation"):
            opp = "Major donor cultivation"
            step = "Personal outreach from Tiffany within 48 hrs"
        elif c.get("is_daf"):
            opp = "DAF relationship — find the advisor"
            step = "Research DAF sponsor; invite to events"
        elif c.get("is_foundation"):
            opp = "Grant renewal / expansion"
            step = "Schedule stewardship call with Val"
        elif c.get("is_corporate"):
            opp = "Corporate partnership or sponsorship"
            step = "Introduce to Brent / Robert for follow-up"
        elif amount_val >= 500:
            opp = "Upgrade potential"
            step = "Include in major gift pipeline review"
        else:
            opp = "Mid-level cultivation"
            step = "Add to newsletter / event list"
        s6_rows.append([name, amt, opp, step])
    html_parts.append(
        _table(
            ["Donor", "Amount", "Opportunity Identified", "Suggested Next Step"],
            s6_rows,
            "No opportunities flagged this period.",
        )
    )
    html_parts.append("""
<p class="note">Examples: Upgrade potential · Major donor cultivation ·
Event or sponsorship alignment · Corporate or foundation linkage</p>
""")

    # -----------------------------------------------------------------------
    # Letters section (if any)
    # -----------------------------------------------------------------------
    if letters:
        html_parts.append(
            '<h2>Attached Letters / Supporting Documents</h2>'
        )
        letter_rows = []
        for i, letter in enumerate(letters):
            org = letter.get("sender_organization") or letter.get("sender_name") or "Unknown"
            ltype = letter.get("letter_type", "other").title()
            amt = _fmt_currency(letter.get("associated_amount"))
            notes = letter.get("notes") or "—"
            page = letter.get("page_number", "—")
            letter_rows.append([str(i + 1), org, ltype, amt, f"Page {page}", notes])
        html_parts.append(
            _table(
                ["#", "Sent By", "Type", "Amount Mentioned", "Page", "Notes"],
                letter_rows,
            )
        )

    # -----------------------------------------------------------------------
    # Attachments + Next Steps
    # -----------------------------------------------------------------------
    html_parts.append("""
<h2>Attachments</h2>
<ul>
  <li>Check copies for all gifts listed above</li>
  <li>Supporting notes (if applicable)</li>
</ul>

<h2>Next Steps</h2>
<ul>
  <li>Complete assigned outreach within 3–5 days</li>
  <li>Flag any meaningful conversations, signals, or opportunities back to me</li>
</ul>

<div class="footer">
  <p>This is about making sure we're not missing moments to connect, thank, and build deeper
  relationships.</p>
  <p>Appreciate you all 🤍 <strong>Tiffany</strong></p>
</div>
</body></html>
""")

    html = "\n".join(html_parts)

    # -----------------------------------------------------------------------
    # Plain-text summary (for logging / fallback)
    # -----------------------------------------------------------------------
    lines = [
        "=" * 60,
        "MIDNIGHT MISSION — GIFT PROCESSING REPORT",
        f"Reporting Period: {period}",
        "=" * 60,
        "",
        "SUMMARY SNAPSHOT",
        f"  Total Gifts:       {total_gifts}",
        f"  Total Revenue:     {_fmt_currency(total_revenue)}",
        f"  # of Gifts $1,000+: {num_major}",
        f"  # of DAF Gifts:    {num_daf}",
        f"  Notable New Donors: {len(notable)}",
        "",
    ]
    for section, label, items in [
        ("1. $1,000+ Gifts (High-Touch – Tiffany)", "major", cats["major"]),
        ("2. Corporate Gifts (Brent / Robert)", "corporate", cats["corporate"]),
        ("3. Foundation Gifts (Val / Abby)", "foundation", cats["foundation"]),
        ("4. $500–$999 Gifts", "mid", cats["mid"]),
        ("5. DAF Gifts", "daf", cats["daf"]),
    ]:
        lines.append(section)
        if not items:
            lines.append("  (none)")
        for c in items:
            lines.append(f"  • {_display_name(c):<40s}  {_fmt_currency(c.get('amount'))}")
        lines.append("")

    if letters:
        lines.append("LETTERS / DOCUMENTS")
        for letter in letters:
            org = letter.get("sender_organization") or letter.get("sender_name") or "Unknown"
            lines.append(f"  • [{letter.get('letter_type','other').upper()}] {org}"
                         f" — p.{letter.get('page_number','?')}")
        lines.append("")

    plain = "\n".join(lines)
    return plain, html


def report_subject(
    data: dict,
    period_start: str | None = None,
    period_end: str | None = None,
) -> str:
    """Return a concise email subject line for the report."""
    checks = data.get("checks", [])
    total = sum(c.get("amount") or 0 for c in checks)
    today = datetime.date.today().strftime("%m/%d/%Y")
    period = period_start or today
    return (
        f"Gift Processing Report — {period} | "
        f"{len(checks)} Gifts | {_fmt_currency(total)} Total"
    )
