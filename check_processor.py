"""
Check Processor
===============
Converts a scanned PDF of donation checks into structured data by:
  1. Rendering each PDF page to a PNG image (via PyMuPDF)
  2. Sending the image to Claude's vision AI
  3. Parsing the returned JSON array into CheckData dataclasses

Multiple checks per page are fully supported.

Extracted fields per check
--------------------------
  donor_name        Full name or organization on the check
  donor_address     Mailing address (if visible)
  amount / amount_str  Numeric value and as-written string (e.g. "$1,250.00")
  date              Date written on the check
  memo              Memo line text
  check_number      Check number (if visible)
  donor_type        "individual" | "daf" | "corporate" | "foundation"
  has_attached_letter  True when a cover letter / sticky note is detected
  notes             Any other notable observations

Usage
-----
    from check_processor import process_pdf
    checks = process_pdf("batch_scan.pdf")
"""

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import anthropic


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class CheckData:
    page_number: int
    donor_name: str = ""
    donor_address: str = ""
    amount: float = 0.0
    amount_str: str = ""
    date: str = ""
    memo: str = ""
    check_number: str = ""
    donor_type: str = "individual"   # individual | daf | corporate | foundation
    has_attached_letter: bool = False
    notes: str = ""


# ── Internal helpers ─────────────────────────────────────────────────────────

_EXTRACTION_PROMPT = """You are extracting data from a scanned page that may contain ONE OR MORE donation checks.
These are real paper checks that have been scanned — they may appear stacked vertically, at an angle,
have low contrast, or be partially cut off. Do your best to read every check even if scan quality is poor.

IMPORTANT: A single page often contains 2, 3, or more checks stacked on top of each other.
Extract ALL checks visible on the page — do not stop after the first one.

For each check, look carefully for:
- The name/address printed in the upper-left (the account holder — this is the DONOR)
- The PAY TO THE ORDER OF line (the recipient, e.g. "Midnight Mission" — NOT the donor)
- The dollar amount (numeric box on the right and written-out amount below)
- The date field (top-right area)
- The memo/for line (bottom-left)
- The check number (top-right corner, also in MICR line at bottom)
- Bank name

Return a JSON array — one object per check found. If NO checks at all are on the page, return [].

Each object must have exactly these keys:
{
  "donor_name":          "<full name or organization printed in upper-left — the account holder/payer>",
  "donor_address":       "<full mailing address printed on the check if visible, else empty string>",
  "amount":              0.00,
  "amount_str":          "<amount as written, e.g. '$30.00'>",
  "date":                "<date as written on the check>",
  "memo":                "<memo/for line text, or empty string>",
  "check_number":        "<check number if visible, else empty string>",
  "donor_type":          "<one of: individual | daf | corporate | foundation>",
  "has_attached_letter": false,
  "notes":               "<any other important observations>"
}

donor_type rules
----------------
• "daf"         — check is from a donor-advised fund (Fidelity Charitable,
                  Schwab Charitable, Vanguard Charitable, NPT, BNY Mellon, etc.)
• "foundation"  — check is from a private or family foundation
• "corporate"   — check is from a company, LLC, Inc., Corp., business, etc.
• "individual"  — personal check (default when none of the above apply)

has_attached_letter
-------------------
Set to true only when a cover letter, sticky note, or separate explanatory
page is clearly visible alongside or attached to a check.

Return only a valid JSON array — no prose, no markdown, no code fences.
Example of correct output for a page with 2 checks:
[
  { "donor_name": "Jane Smith", "amount": 30.00, ... },
  { "donor_name": "Bob Jones", "amount": 50.00, ... }
]"""


def _parse_json_array(raw: str) -> list[dict]:
    """Extract a JSON array from Claude's response, tolerating minor formatting."""
    raw = raw.strip()
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]  # single object returned instead of array
    except json.JSONDecodeError:
        pass

    # Try to find an array in the response
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # Fall back: try a single object
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return [json.loads(match.group())]
        except json.JSONDecodeError:
            pass

    return []


def _dict_to_check(data: dict, page_num: int) -> CheckData:
    return CheckData(
        page_number=page_num,
        donor_name=data.get("donor_name", ""),
        donor_address=data.get("donor_address", ""),
        amount=float(data.get("amount") or 0.0),
        amount_str=data.get("amount_str", ""),
        date=data.get("date", ""),
        memo=data.get("memo", ""),
        check_number=data.get("check_number", ""),
        donor_type=data.get("donor_type", "individual"),
        has_attached_letter=bool(data.get("has_attached_letter", False)),
        notes=data.get("notes", ""),
    )


def _extract_from_image(
    client: anthropic.Anthropic,
    image_b64: str,
    page_num: int,
) -> list[CheckData]:
    """Send one page image to Claude Vision and return all checks found on it."""
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_b64,
                    },
                },
                {"type": "text", "text": _EXTRACTION_PROMPT},
            ],
        }],
    )

    raw = next((b.text for b in response.content if b.type == "text"), "[]")
    items = _parse_json_array(raw)

    if not items:
        snippet = raw[:300].replace("\n", " ") if raw else "(empty response)"
        print(f"\n    [debug] Claude raw response: {snippet}")
        return []

    checks = [_dict_to_check(d, page_num) for d in items if d.get("donor_name")]
    return checks


# ── Public API ────────────────────────────────────────────────────────────────

def process_pdf(pdf_path: str | Path, dpi: int = 300) -> list[CheckData]:
    """
    Convert every page of a scanned check PDF to an image and extract
    all check data using Claude's vision AI. Multiple checks per page
    are fully supported.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the input PDF file.
    dpi : int
        Resolution used when rendering pages (default 300 dpi).

    Returns
    -------
    list[CheckData]
        One entry per detected check across all pages.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    client = anthropic.Anthropic()
    doc = fitz.open(str(pdf_path))
    results: list[CheckData] = []

    print(f"Processing {len(doc)} page(s) from '{pdf_path.name}'...")

    for i, page in enumerate(doc):
        page_num = i + 1
        print(f"  Page {page_num}/{len(doc)}: rendering and analyzing...", end=" ")
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        image_b64 = base64.standard_b64encode(pix.tobytes("png")).decode("utf-8")

        checks = _extract_from_image(client, image_b64, page_num)
        results.extend(checks)

        if checks:
            for c in checks:
                print(f"\n    {c.donor_name} | {c.amount_str} | {c.donor_type}", end=" ")
            print()
        else:
            print("(no check detected)")

    doc.close()

    print(f"\nDone. Detected {len(results)} check(s) across {len(doc)} page(s).")
    return results
