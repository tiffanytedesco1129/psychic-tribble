"""
Check Processor
===============
Uses Claude's vision API to extract structured donation data from a scanned
PDF containing checks and any accompanying letters (grant letters, DAF cover
letters, etc.).

Each PDF page is rendered at 2x resolution and sent to Claude in a single
multi-image API call so it can understand context across pages (e.g. a letter
on page 3 that belongs to the check on page 4).

Returned structure
------------------
{
  "checks": [
    {
      "donor_name": str,
      "address": str | None,
      "amount": float,
      "date": str,          # YYYY-MM-DD when parseable
      "memo": str | None,
      "check_number": str | None,
      "bank_name": str | None,
      "is_daf": bool,
      "daf_sponsor": str | None,
      "is_corporate": bool,
      "company_name": str | None,
      "is_foundation": bool,
      "foundation_name": str | None,
      "associated_letter_index": int | None   # index into "letters" list
    },
    ...
  ],
  "letters": [
    {
      "sender_name": str | None,
      "sender_organization": str | None,
      "letter_type": "grant" | "daf" | "cover_letter" | "other",
      "associated_amount": float | None,
      "notes": str,
      "page_number": int
    },
    ...
  ],
  "total_pages_analyzed": int
}
"""

import base64
import json
import os
import sys
from pathlib import Path

import anthropic


# ---------------------------------------------------------------------------
# PDF → images
# ---------------------------------------------------------------------------

def _pdf_to_images(pdf_path: str) -> list[bytes]:
    """Render every PDF page to a PNG at 2× scale for better OCR quality."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        sys.exit(
            "PyMuPDF is required for PDF processing.\n"
            "Install it with:  pip install pymupdf"
        )

    doc = fitz.open(pdf_path)
    images: list[bytes] = []
    scale = fitz.Matrix(2.0, 2.0)

    for page in doc:
        pix = page.get_pixmap(matrix=scale)
        images.append(pix.tobytes("png"))

    doc.close()
    return images


def _image_file_to_bytes(image_path: str) -> list[bytes]:
    """Return a single-element list with raw image bytes for a non-PDF image."""
    with open(image_path, "rb") as f:
        return [f.read()]


# ---------------------------------------------------------------------------
# Media type helper
# ---------------------------------------------------------------------------

def _media_type(path: str, is_pdf: bool) -> str:
    if is_pdf:
        return "image/png"          # pages were converted to PNG
    ext = Path(path).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/png")


# ---------------------------------------------------------------------------
# Claude extraction prompt
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """You are processing a scanned batch of donation checks for a nonprofit organization. \
The pages may include personal checks, corporate checks, Donor Advised Fund (DAF) checks, \
foundation checks, and accompanying letters (grant award letters, DAF transmittal letters, \
cover letters, etc.).

For EVERY CHECK found across all pages, extract:
  - donor_name: Full name exactly as printed on the check
  - address: Full address if visible (null if not)
  - amount: Dollar amount as a plain float (e.g. 1500.00)
  - date: Date on the check in YYYY-MM-DD format; use best guess if partial
  - memo: Text in the memo/for field (null if blank)
  - check_number: Check number (null if not visible)
  - bank_name: Issuing bank name (null if not visible)
  - is_daf: true if the check is from a Donor Advised Fund sponsor (Fidelity Charitable, \
Schwab Charitable, Vanguard Charitable, National Philanthropic Trust, etc.)
  - daf_sponsor: Name of the DAF sponsor if is_daf is true (null otherwise)
  - is_corporate: true if this is clearly a business/corporate check
  - company_name: Company name if is_corporate is true (null otherwise)
  - is_foundation: true if the check is from a foundation or grant-making entity
  - foundation_name: Foundation name if is_foundation is true (null otherwise)
  - associated_letter_index: Zero-based index into the "letters" array of any letter \
that appears to belong to this check; null if none

For EVERY LETTER / COVER PAGE found, extract:
  - sender_name: Individual name if signed (null if not)
  - sender_organization: Organization or institution name (null if not clear)
  - letter_type: one of "grant", "daf", "cover_letter", or "other"
  - associated_amount: Dollar amount stated in the letter as a float (null if none)
  - notes: One or two sentence summary of the letter's purpose
  - page_number: 1-based page number where the letter appears

Return ONLY valid JSON — no markdown fences, no extra text — in exactly this structure:
{
  "checks": [ ... ],
  "letters": [ ... ],
  "total_pages_analyzed": <integer>
}"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_check_data(file_path: str) -> dict:
    """
    Process a PDF or image file containing scanned checks (and optional letters).

    Parameters
    ----------
    file_path:
        Path to a PDF, JPEG, PNG, or other image file.

    Returns
    -------
    dict with keys: checks, letters, total_pages_analyzed
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    is_pdf = path.suffix.lower() == ".pdf"
    if is_pdf:
        print(f"  Converting PDF pages to images…")
        raw_images = _pdf_to_images(file_path)
    else:
        raw_images = _image_file_to_bytes(file_path)

    print(f"  Sending {len(raw_images)} page(s) to Claude for analysis…")
    media = _media_type(file_path, is_pdf)

    # Build the multi-image message content
    content: list[dict] = []
    for i, img_bytes in enumerate(raw_images):
        content.append({"type": "text", "text": f"--- Page {i + 1} of {len(raw_images)} ---"})
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media,
                "data": base64.standard_b64encode(img_bytes).decode("utf-8"),
            },
        })
    content.append({"type": "text", "text": _EXTRACTION_PROMPT})

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": content}],
    )

    raw_text: str = response.content[0].text.strip()

    # Strip accidental markdown fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```", 2)[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.rsplit("```", 1)[0]

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Claude returned non-JSON output:\n{raw_text}"
        ) from exc

    # Ensure required top-level keys exist
    data.setdefault("checks", [])
    data.setdefault("letters", [])
    data.setdefault("total_pages_analyzed", len(raw_images))

    print(f"  Extracted {len(data['checks'])} check(s) and {len(data['letters'])} letter(s).")
    return data
