"""
Check Processor
===============
Converts a scanned PDF of donation checks into structured data by:
  1. Rendering each PDF page to a PNG image (via PyMuPDF)
  2. Sending the image to Claude's vision AI
  3. Parsing the returned JSON into a CheckData dataclass

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

_EXTRACTION_PROMPT = """You are extracting data from a scanned page that contains one or more donation checks.
These are real paper checks that have been scanned — they may appear at an angle, have low contrast,
or be partially cut off. Do your best to read every field even if the scan quality is poor.

Look carefully for:
- The PAY TO THE ORDER OF line (donor name / payer)
- The dollar amount (numeric box and written-out amount)
- The date field (top-right area of the check)
- The memo/for line (bottom-left)
- The check number (top-right corner)
- The address printed on the check (upper-left area)
- Bank name and routing/account numbers at the bottom (MICR line)

Return a single JSON object with exactly these keys (no markdown fencing, no extra text):
{
  "donor_name":          "<full name or organization printed on the check — the account holder/payer>",
  "donor_address":       "<full mailing address printed on the check if visible, else empty string>",
  "amount":              0.00,
  "amount_str":          "<amount as written, e.g. '$1,250.00'>",
  "date":                "<date as written on the check>",
  "memo":                "<memo/for line text, or empty string>",
  "check_number":        "<check number if visible, else empty string>",
  "donor_type":          "<one of: individual | daf | corporate | foundation>",
  "has_attached_letter": false,
  "notes":               "<any other important observations, or difficulties reading the check>"
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
page is clearly visible alongside or attached to the check.

IMPORTANT: Even if the scan is blurry or partial, extract whatever you can.
Only return all empty/zero fields if you are certain the page contains NO check at all
(e.g. it is a blank page or contains only a cover letter with no check).

Return only valid JSON — no prose, no markdown, no code fences."""


def _page_to_base64(page: fitz.Page, dpi: int = 200) -> str:
    """Render a PDF page to a base64-encoded PNG string."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return base64.standard_b64encode(pix.tobytes("png")).decode("utf-8")


def _parse_json_response(raw: str) -> dict:
    """Extract a JSON object from Claude's response, tolerating minor formatting."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


def _extract_from_image(
    client: anthropic.Anthropic,
    image_b64: str,
    page_num: int,
) -> CheckData:
    """Send one page image to Claude Vision and return a populated CheckData."""
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
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

    raw = next((b.text for b in response.content if b.type == "text"), "{}")
    data = _parse_json_response(raw)

    if not data.get("donor_name"):
        # Show a snippet of what Claude returned to help with debugging
        snippet = raw[:300].replace("\n", " ") if raw else "(empty response)"
        print(f"\n    [debug] Claude raw response: {snippet}")

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


# ── Public API ────────────────────────────────────────────────────────────────

def process_pdf(pdf_path: str | Path, dpi: int = 300) -> list[CheckData]:
    """
    Convert every page of a scanned check PDF to an image and extract
    check data from each page using Claude's vision AI.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the input PDF file.
    dpi : int
        Resolution used when rendering pages (default 200 dpi).

    Returns
    -------
    list[CheckData]
        One entry per PDF page. Pages with no detected check will have
        empty string fields and amount == 0.0.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    client = anthropic.Anthropic()
    results: list[CheckData] = []

    with fitz.open(str(pdf_path)) as doc:
        print(f"Processing {len(doc)} page(s) from '{pdf_path.name}'...")

        debug_dir = pdf_path.parent / "debug_pages"
        debug_dir.mkdir(exist_ok=True)
        print(f"  (debug images → {debug_dir})")

        page_count = len(doc)
        for i in range(page_count):
            page_num = i + 1
            print(f"  Page {page_num}/{page_count}: rendering and analyzing...", end=" ")
            page = doc[i]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            debug_img = debug_dir / f"page_{page_num:03d}.png"
            pix.save(str(debug_img))
            image_b64 = base64.standard_b64encode(pix.tobytes("png")).decode("utf-8")
            del page  # release page reference before moving on
            check = _extract_from_image(client, image_b64, page_num)
            results.append(check)

            if check.donor_name:
                print(f"{check.donor_name} | {check.amount_str} | {check.donor_type}")
            else:
                print("(no check detected)")

    detected = sum(1 for c in results if c.donor_name)
    print(f"\nDone. Detected {detected} check(s) across {len(results)} page(s).")
    return results
