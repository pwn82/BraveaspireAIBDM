from datetime import datetime
from typing import Optional
from sqlalchemy import func
from ..database.db import get_db
from ..database.models import Company, Contact, Outreach, FollowUp, AILog


class CRMService:
    """
    Tenant-scoped CRM data access.

    Phase 1 (Chunk 2): `organization_id` is a REQUIRED constructor argument.
    Every read is filtered by it, every write is stamped with it, and every
    cross-model foreign-key on write is verified to belong to the same org.
    Passing a foreign key from another org returns None on write and empty
    lists on read — no silent leaks.

    `system=True` is the ONLY escape hatch and is reserved for legitimate
    system contexts (initial seed, scheduler sweeps across all tenants).
    UI and API paths must never use it.
    """

    def __init__(self, organization_id: Optional[int] = None, *, system: bool = False):
        if organization_id is None and not system:
            raise ValueError(
                "CRMService requires organization_id. "
                "Use system=True only for cross-tenant scheduler/seed contexts."
            )
        self.organization_id = organization_id
        self.system = system

    # ── Internal helpers ───────────────────────────────────────────────────────
    def _scope(self, query, model):
        """Filter a query by organization_id unless in system mode."""
        if self.system:
            return query
        return query.filter(model.organization_id == self.organization_id)

    def _stamp(self, data: dict) -> dict:
        """Stamp organization_id onto a write payload (unless system)."""
        if self.system:
            return data
        data = dict(data)
        data["organization_id"] = self.organization_id
        return data

    def _own_company(self, db, company_id) -> Optional[Company]:
        """Return company if it belongs to this org; None otherwise."""
        if not company_id:
            return None
        q = db.query(Company).filter(Company.id == company_id)
        if not self.system:
            q = q.filter(Company.organization_id == self.organization_id)
        return q.first()

    def _own_contact(self, db, contact_id) -> Optional[Contact]:
        if not contact_id:
            return None
        q = db.query(Contact).filter(Contact.id == contact_id)
        if not self.system:
            q = q.filter(Contact.organization_id == self.organization_id)
        return q.first()

    def _own_outreach(self, db, outreach_id) -> Optional[Outreach]:
        if not outreach_id:
            return None
        q = db.query(Outreach).filter(Outreach.id == outreach_id)
        if not self.system:
            q = q.filter(Outreach.organization_id == self.organization_id)
        return q.first()

    # ── Companies ──────────────────────────────────────────────────────────────

    def get_companies(
        self,
        search: str = "",
        industry: str = "",
        status: str = "",
        location: str = "",
        limit: Optional[int] = None,
    ) -> list:
        with get_db() as db:
            q = self._scope(db.query(Company), Company)
            if search:
                q = q.filter(
                    Company.name.ilike(f"%{search}%")
                    | Company.industry.ilike(f"%{search}%")
                    | Company.pain_points.ilike(f"%{search}%")
                )
            if industry:
                q = q.filter(Company.industry.ilike(f"%{industry}%"))
            if location:
                q = q.filter(Company.location.ilike(f"%{location}%"))
            if status:
                q = q.filter(Company.status == status)
            q = q.order_by(Company.score.desc())
            if limit:
                q = q.limit(limit)
            return [self._company_dict(c) for c in q.all()]

    _COMPANY_LIMITS = {
        "name":           300,
        "website":        500,
        "industry":       200,
        "location":       500,
        "revenue":        100,
        "status":          50,
        "source":         150,
        "linkedin_url":   500,
        "funding_stage":   50,
        "funding_amount":  50,
        "crunchbase_url": 500,
        "apollo_id":      100,
    }

    @classmethod
    def _truncate_company(cls, data: dict) -> dict:
        out = dict(data)
        for col, max_len in cls._COMPANY_LIMITS.items():
            v = out.get(col)
            if isinstance(v, str) and len(v) > max_len:
                out[col] = v[: max_len - 1].rstrip() + "…"
        return out

    def add_company(self, data: dict) -> Optional[dict]:
        """
        Create a Company for this org. Phase 7: enforces the `companies` quota
        from the org's plan. Returns None (and does not write) when over cap.
        Callers must check for None and show a friendly upgrade prompt.
        System-mode CRMService skips the quota check (for seed / migration).
        """
        if not self.system:
            from .entitlements import check_quota
            gate = check_quota(self.organization_id, "companies", amount=1)
            if not gate.allowed:
                return None
        data = self._truncate_company(self._stamp(data))
        with get_db() as db:
            company = Company(**data)
            db.add(company)
            db.flush()
            return self._company_dict(company)

    def update_company(self, company_id: int, data: dict) -> Optional[dict]:
        data = self._truncate_company(data)
        # Never let a caller move a row across orgs.
        data.pop("organization_id", None)
        with get_db() as db:
            company = self._own_company(db, company_id)
            if not company:
                return None
            for k, v in data.items():
                setattr(company, k, v)
            company.updated_at = datetime.utcnow()
            return self._company_dict(company)

    def delete_company(self, company_id: int) -> bool:
        with get_db() as db:
            company = self._own_company(db, company_id)
            if not company:
                return False
            db.delete(company)
            return True

    def get_industries(self) -> list[str]:
        with get_db() as db:
            q = self._scope(db.query(Company.industry).distinct(), Company).filter(
                Company.industry.isnot(None)
            )
            return sorted([r[0] for r in q.all() if r[0]])

    def _company_dict(self, c: Company) -> dict:
        return {
            "id": c.id, "name": c.name, "website": c.website,
            "industry": c.industry, "location": c.location,
            "employee_size": c.employee_size, "revenue": c.revenue,
            "score": c.score, "status": c.status,
            "hiring_status": c.hiring_status, "tech_stack": c.tech_stack,
            "pain_points": c.pain_points, "notes": c.notes,
            "source": c.source,
            "organization_id": c.organization_id,
            "created_at": c.created_at.strftime("%Y-%m-%d") if c.created_at else "",
        }

    # ── Contacts ───────────────────────────────────────────────────────────────

    def get_contacts(self, company_id: Optional[int] = None, search: str = "") -> list:
        with get_db() as db:
            q = self._scope(db.query(Contact), Contact)
            if company_id:
                q = q.filter(Contact.company_id == company_id)
            if search:
                q = q.filter(Contact.name.ilike(f"%{search}%") | Contact.email.ilike(f"%{search}%"))
            contacts = q.all()
            result = []
            for c in contacts:
                d = self._contact_dict(c)
                if c.company:
                    d["company_name"] = c.company.name
                result.append(d)
            return result

    def add_contact(self, data: dict) -> Optional[dict]:
        """company_id in the payload MUST belong to this org, else returns None.
        Also enforces the `contacts` plan quota."""
        if not self.system:
            from .entitlements import check_quota
            gate = check_quota(self.organization_id, "contacts", amount=1)
            if not gate.allowed:
                return None
        with get_db() as db:
            co_id = data.get("company_id")
            if co_id and not self._own_company(db, co_id):
                return None  # cross-tenant foreign key attempt
            payload = self._stamp(data)
            contact = Contact(**payload)
            db.add(contact)
            db.flush()
            return self._contact_dict(contact)

    def update_contact(self, contact_id: int, data: dict) -> Optional[dict]:
        data = dict(data)
        data.pop("organization_id", None)
        with get_db() as db:
            contact = self._own_contact(db, contact_id)
            if not contact:
                return None
            # If caller changes company_id, verify the new company is in-org.
            new_co = data.get("company_id")
            if new_co and not self._own_company(db, new_co):
                return None
            for k, v in data.items():
                setattr(contact, k, v)
            return self._contact_dict(contact)

    def _contact_dict(self, c: Contact) -> dict:
        return {
            "id": c.id, "company_id": c.company_id,
            "name": c.name, "designation": c.designation,
            "email": c.email, "linkedin": c.linkedin,
            "phone": c.phone, "verified": c.verified,
            "email_status": c.email_status or "unknown",
            "email_source": c.email_source,
            "email_confidence": c.email_confidence,
            "notes": c.notes,
            "organization_id": c.organization_id,
            "created_at": c.created_at.strftime("%Y-%m-%d") if c.created_at else "",
            "company_name": "",
        }

    # ── Outreach ───────────────────────────────────────────────────────────────

    def get_outreach(self, status: str = "", contact_id: Optional[int] = None) -> list:
        with get_db() as db:
            q = self._scope(db.query(Outreach), Outreach)
            if status:
                q = q.filter(Outreach.status == status)
            if contact_id:
                q = q.filter(Outreach.contact_id == contact_id)
            rows = q.order_by(Outreach.created_at.desc()).all()
            result = []
            for o in rows:
                d = self._outreach_dict(o)
                if o.contact:
                    d["contact_name"] = o.contact.name
                    d["contact_email"] = o.contact.email
                    d["contact_email_status"] = o.contact.email_status or "unknown"
                    if o.contact.company:
                        d["company_name"] = o.contact.company.name
                result.append(d)
            return result

    def create_outreach(self, data: dict) -> Optional[dict]:
        """contact_id in the payload MUST belong to this org."""
        with get_db() as db:
            ct_id = data.get("contact_id")
            if ct_id and not self._own_contact(db, ct_id):
                return None
            payload = self._stamp(data)
            outreach = Outreach(**payload)
            db.add(outreach)
            db.flush()
            return self._outreach_dict(outreach)

    def update_outreach(self, outreach_id: int, data: dict) -> Optional[dict]:
        data = dict(data)
        data.pop("organization_id", None)
        with get_db() as db:
            outreach = self._own_outreach(db, outreach_id)
            if not outreach:
                return None
            for k, v in data.items():
                setattr(outreach, k, v)
            return self._outreach_dict(outreach)

    def _outreach_dict(self, o: Outreach) -> dict:
        return {
            "id": o.id, "contact_id": o.contact_id,
            "subject": o.subject, "body": o.body, "status": o.status,
            "sent_at": o.sent_at.strftime("%Y-%m-%d %H:%M") if o.sent_at else "",
            "opened_at": o.opened_at.strftime("%Y-%m-%d %H:%M") if o.opened_at else "",
            "replied_at": o.replied_at.strftime("%Y-%m-%d %H:%M") if o.replied_at else "",
            "follow_up_count": o.follow_up_count,
            "approved_by": o.approved_by,
            "approved_at": o.approved_at.strftime("%Y-%m-%d %H:%M") if o.approved_at else "",
            "organization_id": o.organization_id,
            "created_at": o.created_at.strftime("%Y-%m-%d") if o.created_at else "",
            "contact_name": "", "contact_email": "", "contact_email_status": "unknown", "company_name": "",
        }

    # ── Follow-ups ─────────────────────────────────────────────────────────────

    def get_followups(self, status: str = "") -> list:
        with get_db() as db:
            q = self._scope(db.query(FollowUp), FollowUp)
            if status:
                q = q.filter(FollowUp.status == status)
            rows = q.order_by(FollowUp.scheduled_at.asc()).all()
            result = []
            for f in rows:
                d = self._followup_dict(f)
                if f.outreach and f.outreach.contact:
                    d["contact_name"] = f.outreach.contact.name
                    d["contact_email"] = f.outreach.contact.email
                    if f.outreach.contact.company:
                        d["company_name"] = f.outreach.contact.company.name
                result.append(d)
            return result

    def add_followup(self, data: dict) -> Optional[dict]:
        with get_db() as db:
            out_id = data.get("outreach_id")
            if out_id and not self._own_outreach(db, out_id):
                return None
            payload = self._stamp(data)
            fu = FollowUp(**payload)
            db.add(fu)
            db.flush()
            return self._followup_dict(fu)

    def update_followup(self, followup_id: int, data: dict) -> Optional[dict]:
        data = dict(data)
        data.pop("organization_id", None)
        with get_db() as db:
            q = db.query(FollowUp).filter(FollowUp.id == followup_id)
            if not self.system:
                q = q.filter(FollowUp.organization_id == self.organization_id)
            fu = q.first()
            if not fu:
                return None
            for k, v in data.items():
                setattr(fu, k, v)
            return self._followup_dict(fu)

    def _followup_dict(self, f: FollowUp) -> dict:
        return {
            "id": f.id, "outreach_id": f.outreach_id,
            "subject": f.subject, "body": f.body,
            "sequence_number": f.sequence_number,
            "scheduled_at": f.scheduled_at.strftime("%Y-%m-%d") if f.scheduled_at else "",
            "sent_at": f.sent_at.strftime("%Y-%m-%d %H:%M") if f.sent_at else "",
            "status": f.status,
            "organization_id": f.organization_id,
            "created_at": f.created_at.strftime("%Y-%m-%d") if f.created_at else "",
            "contact_name": "", "contact_email": "", "company_name": "",
        }

    # ── Analytics / Stats ──────────────────────────────────────────────────────

    def get_pipeline_stats(self) -> dict:
        with get_db() as db:
            statuses = ["New", "Contacted", "Interested", "Proposal", "Won", "Lost"]
            counts = {}
            for s in statuses:
                counts[s] = self._scope(db.query(Company), Company).filter(
                    Company.status == s
                ).count()
            total = self._scope(db.query(Company), Company).count()
            total_contacts = self._scope(db.query(Contact), Contact).count()
            total_outreach = self._scope(db.query(Outreach), Outreach).count()
            sent = self._scope(db.query(Outreach), Outreach).filter(
                Outreach.status.in_(["Sent", "Opened", "Replied"])
            ).count()
            opened = self._scope(db.query(Outreach), Outreach).filter(
                Outreach.status.in_(["Opened", "Replied"])
            ).count()
            replied = self._scope(db.query(Outreach), Outreach).filter(
                Outreach.status == "Replied"
            ).count()
            return {
                "pipeline": counts,
                "total_companies": total,
                "total_contacts": total_contacts,
                "total_outreach": total_outreach,
                "emails_sent": sent,
                "emails_opened": opened,
                "emails_replied": replied,
                "open_rate": round(opened / sent * 100, 1) if sent else 0,
                "reply_rate": round(replied / sent * 100, 1) if sent else 0,
                "conversion_rate": round(counts.get("Won", 0) / total * 100, 1) if total else 0,
            }

    # ── AI Logs ────────────────────────────────────────────────────────────────

    def log_ai(self, agent: str, task: str, result: str, provider: str, model: str,
               duration_ms: int, user_id: Optional[int] = None):
        with get_db() as db:
            log = AILog(
                agent_name=agent, task=task, result=result,
                provider=provider, model=model, duration_ms=duration_ms,
                organization_id=None if self.system else self.organization_id,
                user_id=user_id,
            )
            db.add(log)
