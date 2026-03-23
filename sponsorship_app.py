"""
Midnight Mission — Charity Sponsorship Identifier
==================================================
Flask web app that:
  1. Accepts CSV uploads from Raiser's Edge and Get Connected
  2. Categorizes companies by their relationship history
  3. Surfaces new sponsorship targets with priority ranking
  4. Tracks contacts and outreach (phone, mail, email)

Run:
    python sponsorship_app.py

Then open http://localhost:5000
"""

import csv
import io
import json
import os
import tempfile
from datetime import date, datetime

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    Response,
)
from werkzeug.utils import secure_filename

from models import Company, Contact, OutreachLog, db
from processors import (
    RE_FIELD_ALIASES,
    GC_FIELD_ALIASES,
    auto_detect_columns,
    compute_priority,
    compute_re_status,
    get_csv_headers,
    process_get_connected,
    process_raiser_edge,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-midnight-mission")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///sponsorship.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

UPLOAD_FOLDER = tempfile.mkdtemp(prefix="mm_sponsorship_")

db.init_app(app)


@app.before_request
def create_tables():
    db.create_all()


# ---------------------------------------------------------------------------
# Context processors
# ---------------------------------------------------------------------------


@app.context_processor
def inject_stats():
    try:
        total = Company.query.count()
        high = Company.query.filter_by(target_priority="high").count()
        medium = Company.query.filter_by(target_priority="medium").count()
        low = Company.query.filter_by(target_priority="low").count()
        return dict(
            nav_stats=dict(total=total, high=high, medium=medium, low=low)
        )
    except Exception:
        return dict(nav_stats=dict(total=0, high=0, medium=0, low=0))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    total = Company.query.count()
    high = Company.query.filter_by(target_priority="high").count()
    medium = Company.query.filter_by(target_priority="medium").count()
    low = Company.query.filter_by(target_priority="low").count()
    not_targeted = Company.query.filter_by(target_priority="not_targeted").count()

    # Outreach stats
    contacted = Company.query.filter(
        Company.outreach_status.in_(["contacted", "in_conversation", "committed", "converted"])
    ).count()
    converted = Company.query.filter_by(outreach_status="converted").count()

    # Recent outreach
    recent_outreach = (
        OutreachLog.query.order_by(OutreachLog.date.desc()).limit(5).all()
    )

    # Companies needing follow-up today or earlier
    today = date.today()
    follow_ups = (
        OutreachLog.query.filter(OutreachLog.next_follow_up <= today)
        .order_by(OutreachLog.next_follow_up)
        .limit(10)
        .all()
    )

    return render_template(
        "index.html",
        total=total,
        high=high,
        medium=medium,
        low=low,
        not_targeted=not_targeted,
        contacted=contacted,
        converted=converted,
        recent_outreach=recent_outreach,
        follow_ups=follow_ups,
        today=today,
    )


# ---------------------------------------------------------------------------
# Upload — Step 1: Choose file
# ---------------------------------------------------------------------------


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file_type = request.form.get("file_type")  # 're' or 'gc'
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Please select a file.", "danger")
            return redirect(url_for("upload"))
        if file_type not in ("re", "gc"):
            flash("Please choose a data source.", "danger")
            return redirect(url_for("upload"))

        filename = secure_filename(f.filename)
        file_bytes = f.read()

        try:
            headers = get_csv_headers(file_bytes)
        except Exception as e:
            flash(f"Could not read file: {e}", "danger")
            return redirect(url_for("upload"))

        # Store in temp file and remember path in session
        tmp_path = os.path.join(UPLOAD_FOLDER, f"upload_{file_type}_{filename}")
        with open(tmp_path, "wb") as tmp:
            tmp.write(file_bytes)

        session["upload_tmp"] = tmp_path
        session["upload_type"] = file_type
        session["upload_headers"] = headers

        aliases = RE_FIELD_ALIASES if file_type == "re" else GC_FIELD_ALIASES
        detected = auto_detect_columns(headers, aliases)
        session["detected_map"] = detected

        return redirect(url_for("column_map"))

    return render_template("upload.html")


# ---------------------------------------------------------------------------
# Upload — Step 2: Map columns
# ---------------------------------------------------------------------------


@app.route("/upload/map", methods=["GET", "POST"])
def column_map():
    tmp_path = session.get("upload_tmp")
    file_type = session.get("upload_type")
    headers = session.get("upload_headers", [])
    detected = session.get("detected_map", {})

    if not tmp_path or not file_type:
        flash("Upload session expired. Please start again.", "warning")
        return redirect(url_for("upload"))

    aliases = RE_FIELD_ALIASES if file_type == "re" else GC_FIELD_ALIASES
    fields_meta = _fields_meta(file_type)

    if request.method == "POST":
        column_map_in = {field: request.form.get(field, "") for field in aliases}

        if not column_map_in.get("company_name"):
            flash("Company/Organization Name column is required.", "danger")
            return render_template(
                "column_map.html",
                file_type=file_type,
                headers=headers,
                detected=column_map_in,
                fields_meta=fields_meta,
            )

        try:
            with open(tmp_path, "rb") as f:
                file_bytes = f.read()

            if file_type == "re":
                result = process_raiser_edge(file_bytes, column_map_in)
                _upsert_re_data(result)
            else:
                result = process_get_connected(file_bytes, column_map_in)
                _upsert_gc_data(result)

            os.remove(tmp_path)
            session.pop("upload_tmp", None)

            flash(
                f"Imported {len(result['companies'])} companies from "
                f"{result['row_count']} rows "
                f"({result['skipped']} rows skipped).",
                "success",
            )
            return redirect(url_for("companies"))

        except Exception as e:
            flash(f"Error processing file: {e}", "danger")
            return render_template(
                "column_map.html",
                file_type=file_type,
                headers=headers,
                detected=detected,
                fields_meta=fields_meta,
            )

    return render_template(
        "column_map.html",
        file_type=file_type,
        headers=headers,
        detected=detected,
        fields_meta=fields_meta,
    )


def _fields_meta(file_type: str) -> list[dict]:
    """Return display metadata for fields to map, by file type."""
    if file_type == "re":
        return [
            {"key": "company_name", "label": "Company / Organization Name", "required": True,
             "hint": "e.g. 'Organization Name', 'Company'"},
            {"key": "gift_type", "label": "Gift Type", "required": True,
             "hint": "e.g. 'Gift Type' — used to detect Gift in Kind vs. cash"},
            {"key": "gift_amount", "label": "Gift Amount", "required": False,
             "hint": "e.g. 'Amount', 'Gift Amount'"},
            {"key": "contact_name", "label": "Contact Name", "required": False,
             "hint": "e.g. 'Contact', 'Primary Contact'"},
            {"key": "contact_title", "label": "Contact Title / Position", "required": False,
             "hint": "e.g. 'Title', 'Job Title'"},
            {"key": "contact_email", "label": "Contact Email", "required": False,
             "hint": "e.g. 'Email', 'Email Address'"},
            {"key": "contact_phone", "label": "Contact Phone", "required": False,
             "hint": "e.g. 'Phone', 'Work Phone'"},
            {"key": "address", "label": "Street Address", "required": False,
             "hint": "e.g. 'Address Line 1'"},
            {"key": "city", "label": "City", "required": False, "hint": ""},
            {"key": "state", "label": "State", "required": False, "hint": ""},
            {"key": "zip_code", "label": "ZIP Code", "required": False, "hint": ""},
            {"key": "company_phone", "label": "Company Phone", "required": False,
             "hint": "Main phone number for the company"},
            {"key": "website", "label": "Website", "required": False, "hint": ""},
            {"key": "industry", "label": "Industry / Sector", "required": False, "hint": ""},
        ]
    else:
        return [
            {"key": "company_name", "label": "Company / Organization Name", "required": True,
             "hint": "e.g. 'Organization', 'Company', 'Employer'"},
            {"key": "first_name", "label": "Volunteer First Name", "required": False,
             "hint": "e.g. 'First Name'"},
            {"key": "last_name", "label": "Volunteer Last Name", "required": False,
             "hint": "e.g. 'Last Name'"},
            {"key": "contact_name", "label": "Volunteer Full Name", "required": False,
             "hint": "e.g. 'Full Name', 'Name' — use if first/last not separate"},
            {"key": "contact_email", "label": "Volunteer Email", "required": False,
             "hint": "e.g. 'Email'"},
            {"key": "contact_phone", "label": "Volunteer Phone", "required": False,
             "hint": "e.g. 'Phone'"},
            {"key": "contact_title", "label": "Volunteer Title / Position", "required": False,
             "hint": "e.g. 'Title', 'Job Title'"},
            {"key": "address", "label": "Street Address", "required": False, "hint": ""},
            {"key": "city", "label": "City", "required": False, "hint": ""},
            {"key": "state", "label": "State", "required": False, "hint": ""},
            {"key": "zip_code", "label": "ZIP Code", "required": False, "hint": ""},
        ]


# ---------------------------------------------------------------------------
# Data upsert helpers
# ---------------------------------------------------------------------------


def _upsert_re_data(result: dict):
    """Write Raiser's Edge results into the database."""
    companies_data = result["companies"]
    contacts_data = result["contacts"]

    for name, cdata in companies_data.items():
        company = Company.query.filter_by(name=name).first()
        re_status = compute_re_status(cdata["has_cash_gift"], cdata["has_gik"])

        if company is None:
            company = Company(name=name)
            db.session.add(company)

        # Update RE fields (address, phone etc. only if blank)
        if cdata.get("address") and not company.address:
            company.address = cdata["address"]
        if cdata.get("city") and not company.city:
            company.city = cdata["city"]
        if cdata.get("state") and not company.state:
            company.state = cdata["state"]
        if cdata.get("zip_code") and not company.zip_code:
            company.zip_code = cdata["zip_code"]
        if cdata.get("phone") and not company.phone:
            company.phone = cdata["phone"]
        if cdata.get("website") and not company.website:
            company.website = cdata["website"]
        if cdata.get("industry") and not company.industry:
            company.industry = cdata["industry"]

        company.re_status = re_status
        company.target_priority = compute_priority(re_status, company.gc_status)

    db.session.flush()

    for company_name, contact_list in contacts_data.items():
        company = Company.query.filter_by(name=company_name).first()
        if not company:
            continue
        for cdata in contact_list:
            existing = Contact.query.filter_by(
                company_id=company.id, email=cdata["email"], name=cdata["name"]
            ).first()
            if not existing and (cdata["name"] or cdata["email"]):
                db.session.add(Contact(
                    company_id=company.id,
                    name=cdata["name"],
                    title=cdata["title"],
                    email=cdata["email"],
                    phone=cdata["phone"],
                    source="raiser_edge",
                ))

    db.session.commit()


def _upsert_gc_data(result: dict):
    """Write Get Connected results into the database."""
    companies_data = result["companies"]
    contacts_data = result["contacts"]

    for name, cdata in companies_data.items():
        company = Company.query.filter_by(name=name).first()
        if company is None:
            company = Company(name=name)
            db.session.add(company)

        if cdata.get("address") and not company.address:
            company.address = cdata["address"]
        if cdata.get("city") and not company.city:
            company.city = cdata["city"]
        if cdata.get("state") and not company.state:
            company.state = cdata["state"]
        if cdata.get("zip_code") and not company.zip_code:
            company.zip_code = cdata["zip_code"]

        company.gc_status = "volunteer"
        company.target_priority = compute_priority(company.re_status, "volunteer")

    db.session.flush()

    for company_name, contact_list in contacts_data.items():
        company = Company.query.filter_by(name=company_name).first()
        if not company:
            continue
        for cdata in contact_list:
            existing = Contact.query.filter_by(
                company_id=company.id, email=cdata["email"], name=cdata["name"]
            ).first()
            if not existing and (cdata["name"] or cdata["email"]):
                db.session.add(Contact(
                    company_id=company.id,
                    name=cdata["name"],
                    title=cdata["title"],
                    email=cdata["email"],
                    phone=cdata["phone"],
                    source="get_connected",
                ))

    db.session.commit()


# ---------------------------------------------------------------------------
# Company list
# ---------------------------------------------------------------------------


@app.route("/companies")
def companies():
    q = Company.query

    priority_filter = request.args.get("priority", "")
    re_filter = request.args.get("re_status", "")
    gc_filter = request.args.get("gc_status", "")
    status_filter = request.args.get("outreach_status", "")
    search = request.args.get("search", "").strip()

    if priority_filter:
        q = q.filter_by(target_priority=priority_filter)
    if re_filter:
        q = q.filter_by(re_status=re_filter)
    if gc_filter:
        q = q.filter_by(gc_status=gc_filter)
    if status_filter:
        q = q.filter_by(outreach_status=status_filter)
    if search:
        q = q.filter(Company.name.ilike(f"%{search}%"))

    # Default sort: priority (high first), then name
    priority_order = db.case(
        {"high": 1, "medium": 2, "low": 3, "not_targeted": 4},
        value=Company.target_priority,
        else_=5,
    )
    companies_list = q.order_by(priority_order, Company.name).all()

    return render_template(
        "companies.html",
        companies=companies_list,
        priority_filter=priority_filter,
        re_filter=re_filter,
        gc_filter=gc_filter,
        status_filter=status_filter,
        search=search,
    )


# ---------------------------------------------------------------------------
# Company detail
# ---------------------------------------------------------------------------


@app.route("/companies/<int:company_id>")
def company_detail(company_id):
    company = Company.query.get_or_404(company_id)
    logs = (
        OutreachLog.query.filter_by(company_id=company_id)
        .order_by(OutreachLog.date.desc())
        .all()
    )
    today = date.today()
    return render_template(
        "company.html", company=company, logs=logs, today=today
    )


@app.route("/companies/<int:company_id>/edit", methods=["GET", "POST"])
def edit_company(company_id):
    company = Company.query.get_or_404(company_id)
    if request.method == "POST":
        company.name = request.form.get("name", company.name).strip()
        company.address = request.form.get("address", "").strip()
        company.city = request.form.get("city", "").strip()
        company.state = request.form.get("state", "").strip()
        company.zip_code = request.form.get("zip_code", "").strip()
        company.phone = request.form.get("phone", "").strip()
        company.website = request.form.get("website", "").strip()
        company.industry = request.form.get("industry", "").strip()
        company.re_status = request.form.get("re_status", company.re_status)
        company.gc_status = request.form.get("gc_status", company.gc_status)
        company.outreach_status = request.form.get("outreach_status", company.outreach_status)
        company.target_priority = compute_priority(company.re_status, company.gc_status)
        # Allow manual override of priority
        manual_priority = request.form.get("target_priority_override", "")
        if manual_priority:
            company.target_priority = manual_priority
        company.notes = request.form.get("notes", "").strip()
        db.session.commit()
        flash("Company updated.", "success")
        return redirect(url_for("company_detail", company_id=company.id))
    return render_template("edit_company.html", company=company)


@app.route("/companies/add", methods=["GET", "POST"])
def add_company():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Company name is required.", "danger")
            return redirect(url_for("add_company"))
        existing = Company.query.filter_by(name=name).first()
        if existing:
            flash(f'"{name}" already exists.', "warning")
            return redirect(url_for("company_detail", company_id=existing.id))
        re_status = request.form.get("re_status", "none")
        gc_status = request.form.get("gc_status", "none")
        company = Company(
            name=name,
            address=request.form.get("address", "").strip(),
            city=request.form.get("city", "").strip(),
            state=request.form.get("state", "").strip(),
            zip_code=request.form.get("zip_code", "").strip(),
            phone=request.form.get("phone", "").strip(),
            website=request.form.get("website", "").strip(),
            industry=request.form.get("industry", "").strip(),
            re_status=re_status,
            gc_status=gc_status,
            target_priority=compute_priority(re_status, gc_status),
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(company)
        db.session.commit()
        flash(f'"{name}" added.', "success")
        return redirect(url_for("company_detail", company_id=company.id))
    return render_template("add_company.html")


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------


@app.route("/companies/<int:company_id>/contacts/add", methods=["POST"])
def add_contact(company_id):
    company = Company.query.get_or_404(company_id)
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    if not name and not email:
        flash("Name or email required.", "danger")
        return redirect(url_for("company_detail", company_id=company_id))

    contact = Contact(
        company_id=company.id,
        name=name,
        title=request.form.get("title", "").strip(),
        email=email,
        phone=request.form.get("phone", "").strip(),
        mailing_address=request.form.get("mailing_address", "").strip(),
        preferred_method=request.form.get("preferred_method", "email"),
        is_primary=bool(request.form.get("is_primary")),
        is_decision_maker=bool(request.form.get("is_decision_maker")),
        source="manual",
        notes=request.form.get("notes", "").strip(),
    )
    db.session.add(contact)
    db.session.commit()
    flash(f"Contact {name or email} added.", "success")
    return redirect(url_for("company_detail", company_id=company_id))


@app.route("/contacts/<int:contact_id>/delete", methods=["POST"])
def delete_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    company_id = contact.company_id
    db.session.delete(contact)
    db.session.commit()
    flash("Contact removed.", "success")
    return redirect(url_for("company_detail", company_id=company_id))


# ---------------------------------------------------------------------------
# Outreach log
# ---------------------------------------------------------------------------


@app.route("/companies/<int:company_id>/outreach/add", methods=["POST"])
def add_outreach(company_id):
    company = Company.query.get_or_404(company_id)

    method = request.form.get("method", "")
    date_str = request.form.get("date", "")
    if not method or not date_str:
        flash("Method and date are required.", "danger")
        return redirect(url_for("company_detail", company_id=company_id))

    try:
        log_date = date.fromisoformat(date_str)
    except ValueError:
        flash("Invalid date format.", "danger")
        return redirect(url_for("company_detail", company_id=company_id))

    follow_up_str = request.form.get("next_follow_up", "").strip()
    follow_up_date = None
    if follow_up_str:
        try:
            follow_up_date = date.fromisoformat(follow_up_str)
        except ValueError:
            pass

    contact_id_str = request.form.get("contact_id", "")
    contact_id = int(contact_id_str) if contact_id_str else None

    log = OutreachLog(
        company_id=company.id,
        contact_id=contact_id,
        method=method,
        date=log_date,
        notes=request.form.get("notes", "").strip(),
        outcome=request.form.get("outcome", "").strip(),
        next_follow_up=follow_up_date,
    )
    db.session.add(log)

    # Auto-advance outreach status
    new_status = request.form.get("outreach_status", "")
    if new_status:
        company.outreach_status = new_status

    db.session.commit()
    flash("Outreach logged.", "success")
    return redirect(url_for("company_detail", company_id=company_id))


@app.route("/outreach/<int:log_id>/delete", methods=["POST"])
def delete_outreach(log_id):
    log = OutreachLog.query.get_or_404(log_id)
    company_id = log.company_id
    db.session.delete(log)
    db.session.commit()
    flash("Log entry removed.", "success")
    return redirect(url_for("company_detail", company_id=company_id))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@app.route("/export")
def export_companies():
    """Download the current filtered company list as CSV."""
    priority_filter = request.args.get("priority", "")
    status_filter = request.args.get("outreach_status", "")

    q = Company.query
    if priority_filter:
        q = q.filter_by(target_priority=priority_filter)
    if status_filter:
        q = q.filter_by(outreach_status=status_filter)

    priority_order = db.case(
        {"high": 1, "medium": 2, "low": 3, "not_targeted": 4},
        value=Company.target_priority,
        else_=5,
    )
    rows = q.order_by(priority_order, Company.name).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Company Name", "Priority", "RE Status", "GC Status",
        "Outreach Status", "Why Target", "Address", "City", "State", "ZIP",
        "Phone", "Website", "Industry",
        "Primary Contact", "Title", "Email", "Phone (Contact)", "Preferred Method",
        "Notes",
    ])

    for c in rows:
        primary = next((ct for ct in c.contacts if ct.is_primary), None)
        if not primary and c.contacts:
            primary = c.contacts[0]

        writer.writerow([
            c.name,
            c.target_priority,
            c.re_status,
            c.gc_status,
            c.outreach_status,
            c.why_target,
            c.address or "",
            c.city or "",
            c.state or "",
            c.zip_code or "",
            c.phone or "",
            c.website or "",
            c.industry or "",
            primary.name if primary else "",
            primary.title if primary else "",
            primary.email if primary else "",
            primary.phone if primary else "",
            primary.preferred_method if primary else "",
            c.notes or "",
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=sponsorship_targets.csv"
        },
    )


# ---------------------------------------------------------------------------
# Clear all data
# ---------------------------------------------------------------------------


@app.route("/clear-data", methods=["POST"])
def clear_data():
    OutreachLog.query.delete()
    Contact.query.delete()
    Company.query.delete()
    db.session.commit()
    flash("All data has been cleared.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
