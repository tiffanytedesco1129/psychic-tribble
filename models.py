"""
Database models for the Midnight Mission Sponsorship Identifier.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    address = db.Column(db.String(500))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(20))
    phone = db.Column(db.String(50))
    website = db.Column(db.String(255))
    industry = db.Column(db.String(100))

    # Status from Raiser's Edge
    # 'none' | 'gik_only' | 'cash_donor' | 'sponsor'
    re_status = db.Column(db.String(30), default="none", nullable=False)

    # Status from Get Connected
    # 'none' | 'volunteer'
    gc_status = db.Column(db.String(20), default="none", nullable=False)

    # Derived sponsorship priority
    # 'high' | 'medium' | 'low' | 'not_targeted'
    target_priority = db.Column(db.String(20), default="medium", nullable=False)

    # Current outreach stage
    # 'new' | 'researching' | 'contacted' | 'in_conversation' | 'committed' | 'declined' | 'converted'
    outreach_status = db.Column(db.String(30), default="new", nullable=False)

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    contacts = db.relationship(
        "Contact", backref="company", lazy=True, cascade="all, delete-orphan"
    )
    outreach_logs = db.relationship(
        "OutreachLog", backref="company", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def relationship_summary(self):
        parts = []
        if self.re_status == "gik_only":
            parts.append("Gift in Kind")
        elif self.re_status == "cash_donor":
            parts.append("Cash Donor")
        elif self.re_status == "sponsor":
            parts.append("Sponsor")
        if self.gc_status == "volunteer":
            parts.append("Volunteers")
        if not parts:
            return "No prior relationship"
        return " + ".join(parts)

    @property
    def why_target(self):
        """Human-readable reason this company is a sponsorship target."""
        if self.re_status == "none" and self.gc_status == "volunteer":
            return "Employees already volunteer — never asked for cash sponsorship"
        if self.re_status == "gik_only" and self.gc_status == "volunteer":
            return "Deep engagement (volunteer + GIK) — ready to step up to cash"
        if self.re_status == "gik_only":
            return "Gift in kind only — opportunity to convert to cash sponsorship"
        if self.re_status == "none" and self.gc_status == "none":
            return "No prior relationship — new prospect"
        return "Potential new sponsor"


class Contact(db.Model):
    __tablename__ = "contacts"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)

    name = db.Column(db.String(255))
    title = db.Column(db.String(255))
    email = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    mailing_address = db.Column(db.String(500))

    # 'phone' | 'email' | 'mail' | 'any'
    preferred_method = db.Column(db.String(20), default="email")
    is_primary = db.Column(db.Boolean, default=False)
    is_decision_maker = db.Column(db.Boolean, default=False)

    # 'raiser_edge' | 'get_connected' | 'manual' | 'research'
    source = db.Column(db.String(30), default="manual")
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class OutreachLog(db.Model):
    __tablename__ = "outreach_logs"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    contact_id = db.Column(db.Integer, db.ForeignKey("contacts.id"), nullable=True)

    # 'phone' | 'email' | 'mail'
    method = db.Column(db.String(20), nullable=False)
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    outcome = db.Column(db.String(100))
    next_follow_up = db.Column(db.Date)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    contact = db.relationship("Contact", lazy=True)
