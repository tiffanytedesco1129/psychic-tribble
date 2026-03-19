"""
Midnight Mission — Automated Check Processing
=============================================
Processes a scanned PDF (or image) of donation checks, extracts structured
data using Claude's vision API, generates a formatted gift-processing report,
and emails it to the team.

Usage
-----
    python check_main.py path/to/checks.pdf

Optional flags
--------------
  --start DATE      Reporting period start date (e.g. "March 1, 2026")
  --end DATE        Reporting period end date   (e.g. "March 15, 2026")
  --no-email        Print the plain-text report to stdout and skip sending
  --out PATH        Save the HTML report to a file instead of (or in addition
                    to) emailing it

Setup
-----
1. Copy .env.example to .env and set:
       AZURE_CLIENT_ID=...
       AZURE_TENANT_ID=...
       ANTHROPIC_API_KEY=...
       CHECK_REPORT_RECIPIENTS=tiffany@midnightmission.com,...
       CHECK_REPORT_CC=                      (optional)

2. Install dependencies:
       pip install -r requirements.txt

3. Run on a scanned check PDF:
       python check_main.py checks_batch_2026_03.pdf
"""

import argparse
import sys

from check_processor import extract_check_data
from donation_report import generate_report, report_subject
from check_email_sender import send_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process scanned donation checks and email a gift report."
    )
    parser.add_argument(
        "file",
        metavar="FILE",
        help="Path to the scanned PDF or image file containing the checks.",
    )
    parser.add_argument(
        "--start",
        default=None,
        metavar="DATE",
        help='Reporting period start (e.g. "March 1, 2026"). Defaults to today.',
    )
    parser.add_argument(
        "--end",
        default=None,
        metavar="DATE",
        help='Reporting period end (e.g. "March 15, 2026"). Defaults to today.',
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip sending the email; print the plain-text report to stdout.",
    )
    parser.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Optional path to save the HTML report (e.g. report.html).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ------------------------------------------------------------------
    # Step 1: Extract check + letter data from the scan
    # ------------------------------------------------------------------
    print("\nStep 1/3  Extracting check data from scan…")
    data = extract_check_data(args.file)

    checks = data.get("checks", [])
    letters = data.get("letters", [])
    if not checks:
        print("\nNo checks were found in the provided file. Nothing to report.")
        sys.exit(0)

    print(
        f"          Found {len(checks)} check(s) and {len(letters)} letter(s) "
        f"across {data.get('total_pages_analyzed', '?')} page(s)."
    )

    # ------------------------------------------------------------------
    # Step 2: Generate the report
    # ------------------------------------------------------------------
    print("\nStep 2/3  Generating gift-processing report…")
    plain_text, html = generate_report(data, args.start, args.end)
    subject = report_subject(data, args.start, args.end)
    print(f"          Subject: {subject}")

    # Optionally save HTML to disk
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"          HTML report saved to: {args.out}")

    # ------------------------------------------------------------------
    # Step 3: Send or print
    # ------------------------------------------------------------------
    if args.no_email:
        print("\nStep 3/3  --no-email flag set; printing report to stdout.\n")
        print("=" * 60)
        print(plain_text)
        print("=" * 60)
    else:
        print("\nStep 3/3  Sending email report…")
        send_report(subject, html, plain_text)

    print("\nDone!\n")


if __name__ == "__main__":
    main()
