"""
AI-powered features for the Midnight Mission Sponsorship Identifier.

Requires ANTHROPIC_API_KEY in environment (or .env file).
"""

import json
import os

import requests

# ---------------------------------------------------------------------------
# Program catalogue — used for matching and pitch generation
# ---------------------------------------------------------------------------

PROGRAMS = [
    {
        "id": "annual_gala",
        "name": "Annual Gala",
        "description": (
            "Black-tie fundraising dinner. Table and presenting sponsorships "
            "from $5K to $50K+. High visibility, great for corporate branding, "
            "client entertainment, and executive-level engagement."
        ),
        "typical_range": "$5,000 – $50,000+",
        "best_for": "Finance, law, real estate, consulting, entertainment, tech",
    },
    {
        "id": "womens_program",
        "name": "Women's Center Programs",
        "description": (
            "Supporting women and children in recovery, housing, and "
            "workforce re-entry. Naming rights and program funding available. "
            "Strong fit for companies with women-focused CSR or female-skewing brands."
        ),
        "typical_range": "$2,500 – $25,000",
        "best_for": "Healthcare, retail, beauty, fashion, education",
    },
    {
        "id": "family_services",
        "name": "Family Housing & Services",
        "description": (
            "Helping families—including children—transition out of homelessness "
            "into stable housing. Room sponsorships and program funding. "
            "Resonates deeply with family-oriented brands and real estate."
        ),
        "typical_range": "$1,000 – $15,000",
        "best_for": "Real estate, construction, insurance, grocery, family services",
    },
    {
        "id": "volunteer_day",
        "name": "Corporate Volunteer Day",
        "description": (
            "Team volunteer experience at the Mission. Can be paired with an "
            "in-kind or cash donation. Low barrier, great relationship builder "
            "and natural entry point for companies new to us."
        ),
        "typical_range": "$500 – $5,000 (cash or in-kind)",
        "best_for": "Any industry — especially companies already sending volunteers",
    },
    {
        "id": "employment_training",
        "name": "Employment & Skills Training",
        "description": (
            "Workforce readiness: résumé workshops, mock interviews, job fairs, "
            "and hiring partnerships. Great for companies with active hiring needs "
            "or a workforce development pillar in their CSR strategy."
        ),
        "typical_range": "$2,500 – $20,000",
        "best_for": "Staffing, tech, retail, hospitality, logistics, manufacturing",
    },
    {
        "id": "holiday",
        "name": "Holiday Programs",
        "description": (
            "Thanksgiving and Christmas meal service for thousands of guests "
            "on Skid Row. Meal sponsorships and gift drives. High community "
            "visibility and an easy, feel-good entry point for new partners."
        ),
        "typical_range": "$500 – $10,000",
        "best_for": "Any industry — universal appeal",
    },
]

PROGRAM_BY_ID = {p["id"]: p for p in PROGRAMS}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client():
    """Return an Anthropic client, or raise a friendly error if key is missing."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to a .env file in your project folder:\n"
            "  ANTHROPIC_API_KEY=sk-ant-..."
        )
    try:
        from anthropic import Anthropic
        return Anthropic(api_key=api_key)
    except ImportError:
        raise RuntimeError(
            "The 'anthropic' package is not installed. "
            "Run: pip install anthropic"
        )


def _parse_json_response(text: str):
    """Extract and parse a JSON object or array from a Claude response."""
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# Feature 1: Generate pitch email + program & amount suggestions
# ---------------------------------------------------------------------------

def generate_pitch_and_suggestions(company, contacts, logs) -> dict:
    """
    Use Claude to write a personalised sponsorship pitch email and recommend
    the best Midnight Mission program + a suggested ask amount.

    Returns a dict with keys:
        subject, salutation, body, signature,
        suggested_program (id), suggested_amount, reasoning, tips,
        program_info (full program dict)
    On error: {"error": "..."}
    """
    try:
        client = _get_client()
    except RuntimeError as e:
        return {"error": str(e)}

    contact_lines = [
        f"{c.name} ({c.title})" for c in contacts if c.name
    ] or ["No contacts on file yet"]

    history_lines = [
        f"{l.date}: {l.method} — {l.outcome or 'no outcome recorded'}"
        for l in logs[:5]
    ] if logs else ["No prior outreach"]

    programs_text = "\n".join(
        f"- id={p['id']} | {p['name']}: {p['description']} "
        f"Typical ask: {p['typical_range']}. Best for: {p['best_for']}."
        for p in PROGRAMS
    )

    prompt = f"""You are a professional fundraiser at the Midnight Mission in Los Angeles — \
a nonprofit providing comprehensive services (shelter, meals, healthcare, employment) \
to people experiencing homelessness since 1914.

Write a sponsorship outreach email for the company below and recommend the best program fit.

─── COMPANY PROFILE ───────────────────────────────────────────────
Name:               {company.name}
Industry:           {company.industry or "Unknown"}
Location:           {(company.city or "Los Angeles")}, {(company.state or "CA")}
Our relationship:   {company.relationship_summary}
Why we're targeting:{company.why_target}
Contacts we know:   {"; ".join(contact_lines)}
Recent outreach:    {"; ".join(history_lines)}

─── AVAILABLE PROGRAMS ─────────────────────────────────────────────
{programs_text}

─── INSTRUCTIONS ───────────────────────────────────────────────────
Reply with a JSON object (no markdown prose outside the JSON block) with these keys:

  subject          — compelling, personalised email subject line
  salutation       — opening line, e.g. "Dear [Contact Name],"
  body             — 3–4 paragraphs; warm and professional; reference their \
history with us if relevant; end with a clear call to action
  signature        — suggested closing (name, title, phone placeholder)
  suggested_program— single program id from the list above
  suggested_amount — specific dollar amount or tight range to ask for
  reasoning        — 1–2 sentences: why this program and amount fits this company
  tips             — list of 2–3 specific actionable tips for this outreach \
(e.g. how to get a warm intro, best timing, key talking points)

Be specific to this company. Do not produce a generic template."""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _parse_json_response(response.content[0].text)
        prog_id = result.get("suggested_program")
        if prog_id in PROGRAM_BY_ID:
            result["program_info"] = PROGRAM_BY_ID[prog_id]
        return result
    except json.JSONDecodeError as e:
        return {"error": f"Could not parse AI response as JSON: {e}"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Feature 2: External contact research guidance
# ---------------------------------------------------------------------------

def research_company_contacts(company_name: str, website: str = None, industry: str = None) -> dict:
    """
    Return structured guidance on how/where to find the right contact at a company.
    Optionally fetches the company website for additional context.

    Returns a dict with keys:
        target_titles, linkedin_searches, website_pages, research_tips, contact_guess
    On error: {"error": "..."}
    """
    try:
        client = _get_client()
    except RuntimeError as e:
        return {"error": str(e)}

    # Try fetching the company website's /about page for context
    website_snippet = ""
    if website:
        url = website if website.startswith("http") else f"https://{website}"
        for path in ["/about", "/about-us", "/team", "/leadership", "/foundation", ""]:
            try:
                r = requests.get(
                    url.rstrip("/") + path,
                    timeout=5,
                    headers={"User-Agent": "Mozilla/5.0 (research)"},
                )
                if r.status_code == 200 and len(r.text) > 200:
                    # Strip HTML tags crudely for token efficiency
                    import re
                    text = re.sub(r"<[^>]+>", " ", r.text)
                    text = re.sub(r"\s+", " ", text).strip()
                    website_snippet = text[:2000]
                    break
            except Exception:
                continue

    prompt = f"""You are helping a nonprofit fundraiser find the right contact person at a company \
to discuss corporate sponsorship.

Company:  {company_name}
Industry: {industry or "Unknown"}
Website:  {website or "Not on file"}
{f"Website content (excerpt):{chr(10)}{website_snippet}" if website_snippet else ""}

Provide structured guidance for finding the best contact. Reply with JSON only:

{{
  "target_titles": [
      "list of ideal job titles to look for, ranked best-first for nonprofit sponsorship decisions"
  ],
  "linkedin_searches": [
      "exact search strings to type into LinkedIn People search (include company name)"
  ],
  "website_pages": [
      "specific URL paths likely to list leadership or CSR team, e.g. /foundation, /about/team"
  ],
  "research_tips": [
      "2–4 specific, actionable tips for finding this company's philanthropic decision-maker"
  ],
  "contact_guess": "Based on their industry, describe the most likely contact archetype \
(e.g. 'Mid-sized law firm — look for the firm's Managing Partner or pro bono coordinator')"
}}"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json_response(response.content[0].text)
    except json.JSONDecodeError as e:
        return {"error": f"Could not parse AI response as JSON: {e}"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Feature 3: Discover new prospect companies
# ---------------------------------------------------------------------------

def discover_new_companies(industry: str = "", location: str = "Los Angeles", description: str = "") -> dict:
    """
    Ask Claude to suggest new potential corporate sponsors the organisation
    has not yet worked with.

    Returns {"companies": [...]} where each company has:
        name, industry, headquarters, why_target, program_fit,
        suggested_ask, research_tip
    On error: {"error": "..."}
    """
    try:
        client = _get_client()
    except RuntimeError as e:
        return {"error": str(e)}

    industry_clause = f"in the **{industry}** sector" if industry else "across a variety of sectors"
    extra = f"\nAdditional context from the user: {description}" if description.strip() else ""

    prompt = f"""You are a fundraising strategist for the Midnight Mission in Los Angeles — \
a nonprofit providing shelter, meals, healthcare, and employment services to people \
experiencing homelessness since 1914.

Suggest **12–15 real, named companies** {industry_clause} that have a presence in \
{location} and would be strong new sponsorship prospects for us.{extra}

Prioritise companies with:
- Known CSR, philanthropic, or foundation programs
- Ties to the Los Angeles community or Skid Row area
- Alignment with poverty, homelessness, housing, health, or workforce development
- Revenue / size suggesting capacity to give $2,500 or more per year

For each company return a JSON object with:
  name           — company's full legal or trade name
  industry       — their primary industry
  headquarters   — city (note if LA-based or LA office)
  why_target     — 1–2 sentences: specific reason they fit Midnight Mission
  program_fit    — best matching program from: Annual Gala, Women's Center Programs, \
Family Housing & Services, Corporate Volunteer Day, Employment & Skills Training, Holiday Programs
  suggested_ask  — dollar range appropriate to this company
  research_tip   — one specific tip for making first contact

Reply with a JSON array of company objects only — no prose outside the JSON."""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=3500,
            messages=[{"role": "user", "content": prompt}],
        )
        companies = _parse_json_response(response.content[0].text)
        if not isinstance(companies, list):
            companies = companies.get("companies", companies)
        return {"companies": companies}
    except json.JSONDecodeError as e:
        return {"error": f"Could not parse AI response as JSON: {e}"}
    except Exception as e:
        return {"error": str(e)}
