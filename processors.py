"""
CSV processors for Raiser's Edge and Get Connected exports.

Both processors return a list of dicts ready to upsert into the Company/Contact tables.
Column names are flexible — callers pass a mapping from logical field names to actual CSV headers.
"""

import io
import re
import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GIK_KEYWORDS = {"gift in kind", "in-kind", "in kind", "gik", "inkind"}


def _is_gik(gift_type: str) -> bool:
    t = gift_type.strip().lower()
    return any(k in t for k in GIK_KEYWORDS)


def _clean_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits[0] == "1":
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return str(raw or "").strip()


def _val(row, col, default=""):
    if not col or col not in row.index:
        return default
    v = row[col]
    if pd.isna(v):
        return default
    return str(v).strip()


# ---------------------------------------------------------------------------
# Column auto-detection
# ---------------------------------------------------------------------------

RE_FIELD_ALIASES = {
    "company_name": [
        "organization name", "org name", "company", "company name",
        "constituent name", "business name", "employer",
        "organization", "corp name",
    ],
    "gift_type": [
        "gift type", "type", "gift kind", "gift category",
        "payment type", "gift sub type",
    ],
    "gift_amount": [
        "gift amount", "amount", "total amount", "gift total",
        "gift value",
    ],
    "contact_name": [
        "contact name", "contact", "full name", "name",
        "primary contact", "key contact",
    ],
    "contact_title": [
        "title", "job title", "position", "role",
    ],
    "contact_email": [
        "email", "email address", "e-mail", "contact email",
    ],
    "contact_phone": [
        "phone", "phone number", "work phone", "business phone",
        "mobile", "cell phone",
    ],
    "address": [
        "address", "address line 1", "street address", "mailing address",
        "address 1", "street",
    ],
    "city": ["city"],
    "state": ["state", "state/province", "province"],
    "zip_code": ["zip", "zip code", "postal code", "zip/postal code"],
    "company_phone": [
        "company phone", "org phone", "main phone", "business phone",
        "organization phone",
    ],
    "website": ["website", "url", "web", "web address", "company website"],
    "industry": ["industry", "sector", "business type", "type of business"],
}

GC_FIELD_ALIASES = {
    "company_name": [
        "organization", "company", "employer", "business", "org",
        "organization name", "company name", "employer name",
    ],
    "contact_name": [
        "full name", "name", "volunteer name", "first last",
    ],
    "first_name": ["first name", "firstname", "first"],
    "last_name": ["last name", "lastname", "last", "surname"],
    "contact_email": [
        "email", "email address", "e-mail",
    ],
    "contact_phone": [
        "phone", "phone number", "mobile", "cell",
    ],
    "contact_title": [
        "title", "job title", "position",
    ],
    "address": ["address", "street address", "mailing address"],
    "city": ["city"],
    "state": ["state"],
    "zip_code": ["zip", "zip code", "postal code"],
}


def auto_detect_columns(headers: list[str], field_aliases: dict) -> dict:
    """
    Try to match CSV column headers to logical field names using alias lists.
    Returns a dict {logical_field: detected_csv_column | ''}.
    """
    lower_headers = {h.strip().lower(): h for h in headers}
    mapping = {}
    for field, aliases in field_aliases.items():
        found = ""
        for alias in aliases:
            if alias in lower_headers:
                found = lower_headers[alias]
                break
        mapping[field] = found
    return mapping


# ---------------------------------------------------------------------------
# Raiser's Edge processor
# ---------------------------------------------------------------------------

def process_raiser_edge(file_bytes: bytes, column_map: dict) -> dict:
    """
    Parse a Raiser's Edge CSV/Excel export.

    Returns:
        {
          'companies': {name: {...company_fields..., has_cash_gift, has_gik}},
          'contacts':  {company_name: [contact_dict, ...]},
          'row_count': int,
          'skipped':   int,
        }
    """
    df = _read_file(file_bytes)

    companies: dict[str, dict] = {}
    contacts: dict[str, list] = {}
    skipped = 0

    for _, row in df.iterrows():
        name = _val(row, column_map.get("company_name", ""))
        if not name:
            skipped += 1
            continue

        gift_type = _val(row, column_map.get("gift_type", ""))
        is_cash = bool(gift_type) and not _is_gik(gift_type)
        is_gik = _is_gik(gift_type)

        if name not in companies:
            companies[name] = {
                "name": name,
                "address": _val(row, column_map.get("address", "")),
                "city": _val(row, column_map.get("city", "")),
                "state": _val(row, column_map.get("state", "")),
                "zip_code": _val(row, column_map.get("zip_code", "")),
                "phone": _clean_phone(_val(row, column_map.get("company_phone", ""))),
                "website": _val(row, column_map.get("website", "")),
                "industry": _val(row, column_map.get("industry", "")),
                "has_cash_gift": is_cash,
                "has_gik": is_gik,
            }
        else:
            if is_cash:
                companies[name]["has_cash_gift"] = True
            if is_gik:
                companies[name]["has_gik"] = True

        # Extract contact if available
        contact_name = _val(row, column_map.get("contact_name", ""))
        contact_email = _val(row, column_map.get("contact_email", ""))
        if contact_name or contact_email:
            if name not in contacts:
                contacts[name] = []
            entry = {
                "name": contact_name,
                "title": _val(row, column_map.get("contact_title", "")),
                "email": contact_email,
                "phone": _clean_phone(_val(row, column_map.get("contact_phone", ""))),
                "source": "raiser_edge",
            }
            # Deduplicate within this import
            if not any(c["email"] == entry["email"] and c["name"] == entry["name"]
                       for c in contacts[name]):
                contacts[name].append(entry)

    return {
        "companies": companies,
        "contacts": contacts,
        "row_count": len(df),
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# Get Connected processor
# ---------------------------------------------------------------------------

def process_get_connected(file_bytes: bytes, column_map: dict) -> dict:
    """
    Parse a Get Connected CSV export.

    Returns same structure as process_raiser_edge but without gift fields.
    """
    df = _read_file(file_bytes)

    companies: dict[str, dict] = {}
    contacts: dict[str, list] = {}
    skipped = 0

    for _, row in df.iterrows():
        name = _val(row, column_map.get("company_name", ""))
        if not name or name.lower() in ("n/a", "none", "individual", "-"):
            skipped += 1
            continue

        if name not in companies:
            companies[name] = {
                "name": name,
                "address": _val(row, column_map.get("address", "")),
                "city": _val(row, column_map.get("city", "")),
                "state": _val(row, column_map.get("state", "")),
                "zip_code": _val(row, column_map.get("zip_code", "")),
                "phone": "",
                "website": "",
                "industry": "",
            }

        # Build contact name from first/last if full name not available
        contact_name = _val(row, column_map.get("contact_name", ""))
        if not contact_name:
            first = _val(row, column_map.get("first_name", ""))
            last = _val(row, column_map.get("last_name", ""))
            contact_name = f"{first} {last}".strip()

        contact_email = _val(row, column_map.get("contact_email", ""))
        if contact_name or contact_email:
            if name not in contacts:
                contacts[name] = []
            entry = {
                "name": contact_name,
                "title": _val(row, column_map.get("contact_title", "")),
                "email": contact_email,
                "phone": _clean_phone(_val(row, column_map.get("contact_phone", ""))),
                "source": "get_connected",
            }
            if not any(c["email"] == entry["email"] and c["name"] == entry["name"]
                       for c in contacts[name]):
                contacts[name].append(entry)

    return {
        "companies": companies,
        "contacts": contacts,
        "row_count": len(df),
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# Priority assignment
# ---------------------------------------------------------------------------

def compute_priority(re_status: str, gc_status: str) -> str:
    """
    Assign a sponsorship target priority based on relationship history.

    Priority logic:
      High   — volunteers but never gave cash (warm relationship, untapped)
      High   — GIK + volunteers (deeply engaged, step-up opportunity)
      Medium — GIK only (engaged, but in a limited way)
      Low    — no prior relationship (cold outreach)
      None   — already a cash donor or sponsor (not a new target)
    """
    if re_status in ("cash_donor", "sponsor"):
        return "not_targeted"
    if gc_status == "volunteer" and re_status == "none":
        return "high"
    if gc_status == "volunteer" and re_status == "gik_only":
        return "high"
    if re_status == "gik_only":
        return "medium"
    # No prior relationship
    return "low"


def compute_re_status(has_cash_gift: bool, has_gik: bool) -> str:
    if has_cash_gift:
        return "cash_donor"
    if has_gik:
        return "gik_only"
    return "none"


# ---------------------------------------------------------------------------
# File reading utility
# ---------------------------------------------------------------------------

def _read_file(file_bytes: bytes) -> pd.DataFrame:
    """Read CSV or Excel bytes into a DataFrame."""
    try:
        return pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8-sig", dtype=str)
    except Exception:
        try:
            return pd.read_csv(io.BytesIO(file_bytes), encoding="latin-1", dtype=str)
        except Exception:
            return pd.read_excel(io.BytesIO(file_bytes), dtype=str)


def get_csv_headers(file_bytes: bytes) -> list[str]:
    """Return the column headers from a CSV/Excel file."""
    df = _read_file(file_bytes)
    return list(df.columns)
