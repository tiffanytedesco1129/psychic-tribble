"""
run.py  —  Process a scanned check PDF and generate the donation report.

Usage
-----
    python run.py path/to/scan.pdf
    python run.py path/to/scan.pdf --out report.html
    python run.py path/to/scan.pdf --dpi 300

Outputs (all written to the same directory as the PDF by default)
-----------------------------------------------------------------
    donation_report.html   — formatted report for email / review
    sage_upload.csv        — Finance upload for Sage accounting
    nxt_upload.csv         — Development upload for Blackbaud NXT
"""

import argparse
import sys
from pathlib import Path

from check_processor import process_pdf
from donation_report import generate_report
from check_exporters import export_sage_csv, export_nxt_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a scanned check PDF into an HTML donation report."
    )
    parser.add_argument(
        "pdf",
        metavar="PDF",
        help="Path to the scanned check PDF file",
    )
    parser.add_argument(
        "--out",
        default="donation_report.html",
        metavar="PATH",
        help="Output path for the HTML report (default: donation_report.html)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        metavar="N",
        help="Resolution for rendering PDF pages (default: 200)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        sys.exit(f"Error: file not found — {pdf_path}")

    print(f"\nStep 1/2  Extracting checks from '{pdf_path.name}'...")
    checks = process_pdf(pdf_path, dpi=args.dpi)

    detected = sum(1 for c in checks if c.donor_name)
    if not detected:
        print("No checks detected. Nothing to report.")
        sys.exit(0)

    out_dir = Path(args.out).parent

    print(f"\nStep 2/3  Building donation report...")
    out = generate_report(checks, output_path=args.out)

    print(f"\nStep 3/3  Exporting upload spreadsheets...")
    sage_out = export_sage_csv(checks, out_dir / "sage_upload.csv")
    nxt_out  = export_nxt_csv(checks,  out_dir / "nxt_upload.csv")

    print(f"\nDone!  {detected} check(s) processed.")
    print(f"  Report        -> {out.resolve()}")
    print(f"  Sage (Finance)-> {sage_out.resolve()}")
    print(f"  NXT (Dev)     -> {nxt_out.resolve()}")


if __name__ == "__main__":
    main()
