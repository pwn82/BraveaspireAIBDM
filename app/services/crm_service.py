from datetime import datetime
from typing import Optional
from sqlalchemy import func
from ..database.db import get_db
from ..database.models import Company, Contact, Outreach, FollowUp, AILog


class CRMService:

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
            q = db.query(Company)
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

    # Column length limits matching the Company model (defensive truncation
    # so SQL Server never throws "String or binary data would be truncated")
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
        """Trim string fields to column max-lengths to avoid SQL truncation errors."""
        out = dict(data)
        for col, max_len in cls._COMPANY_LIMITS.items():
            v = out.get(col)
            if isinstance(v, str) and len(v) > max_len:
                out[col] = v[: max_len - 1].rstrip() + "…"
        return out

    def add_company(self, data: dict) -> dict:
        data = self._truncate_company(data)
        with get_db() as db:
            company = Company(**data)
            db.add(company)
            db.flush()
            return self._company_dict(company)

    def update_company(self, company_id: int, data: dict) -> Optional[dict]:
        data = self._truncate_company(data)
        with get_db() as db:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                return None
            for k, v in data.items():
                setattr(company, k, v)
            company.updated_at = datetime.utcnow()
            return self._company_dict(company)

    def delete_company(self, company_id: int) -> bool:
        with get_db() as db:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                return False
            db.delete(company)
            return True

    def get_industries(self) -> list[str]:
        with get_db() as db:
            rows = db.query(Company.industry).distinct().filter(Company.industry.isnot(None)).all()
            return sorted([r[0] for r in rows if r[0]])

    def _company_dict(self, c: Company) -> dict:
        return {
            "id": c.id, "name": c.name, "website": c.website,
            "industry": c.industry, "location": c.location,
            "employee_size": c.employee_size, "revenue": c.revenue,
            "score": c.score, "status": c.status,
            "hiring_status": c.hiring_status, "tech_stack": c.tech_stack,
            "pain_points": c.pain_points, "notes": c.notes,
            "source": c.source,
            "created_at": c.created_at.strftime("%Y-%m-%d") if c.created_at else "",
        }

    # ── Contacts ───────────────────────────────────────────────────────────────

    def get_contacts(self, company_id: Optional[int] = None, search: str = "") -> list:
        with get_db() as db:
            q = db.query(Contact)
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

    def add_contact(self, data: dict) -> dict:
        with get_db() as db:
            contact = Contact(**data)
            db.add(contact)
            db.flush()
            return self._contact_dict(contact)

    def update_contact(self, contact_id: int, data: dict) -> Optional[dict]:
        with get_db() as db:
            contact = db.query(Contact).filter(Contact.id == contact_id).first()
            if not contact:
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
            "notes": c.notes,
            "created_at": c.created_at.strftime("%Y-%m-%d") if c.created_at else "",
            "company_name": "",
        }

    # ── Outreach ───────────────────────────────────────────────────────────────

    def get_outreach(self, status: str = "", contact_id: Optional[int] = None) -> list:
        with get_db() as db:
            q = db.query(Outreach)
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
                    if o.contact.company:
                        d["company_name"] = o.contact.company.name
                result.append(d)
            return result

    def create_outreach(self, data: dict) -> dict:
        with get_db() as db:
            outreach = Outreach(**data)
            db.add(outreach)
            db.flush()
            return self._outreach_dict(outreach)

    def update_outreach(self, outreach_id: int, data: dict) -> Optional[dict]:
        with get_db() as db:
            outreach = db.query(Outreach).filter(Outreach.id == outreach_id).first()
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
            "created_at": o.created_at.strftime("%Y-%m-%d") if o.created_at else "",
            "contact_name": "", "contact_email": "", "company_name": "",
        }

    # ── Follow-ups ─────────────────────────────────────────────────────────────

    def get_followups(self, status: str = "") -> list:
        with get_db() as db:
            q = db.query(FollowUp)
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

    def add_followup(self, data: dict) -> dict:
        with get_db() as db:
            fu = FollowUp(**data)
            db.add(fu)
            db.flush()
            return self._followup_dict(fu)

    def update_followup(self, followup_id: int, data: dict) -> Optional[dict]:
        with get_db() as db:
            fu = db.query(FollowUp).filter(FollowUp.id == followup_id).first()
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
            "created_at": f.created_at.strftime("%Y-%m-%d") if f.created_at else "",
            "contact_name": "", "contact_email": "", "company_name": "",
        }

    # ── Analytics / Stats ──────────────────────────────────────────────────────

    def get_pipeline_stats(self) -> dict:
        with get_db() as db:
            statuses = ["New", "Contacted", "Interested", "Proposal", "Won", "Lost"]
            counts = {}
            for s in statuses:
                counts[s] = db.query(Company).filter(Company.status == s).count()
            total = db.query(Company).count()
            total_contacts = db.query(Contact).count()
            total_outreach = db.query(Outreach).count()
            sent = db.query(Outreach).filter(Outreach.status.in_(["Sent", "Opened", "Replied"])).count()
            opened = db.query(Outreach).filter(Outreach.status.in_(["Opened", "Replied"])).count()
            replied = db.query(Outreach).filter(Outreach.status == "Replied").count()
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

    def log_ai(self, agent: str, task: str, result: str, provider: str, model: str, duration_ms: int):
        with get_db() as db:
            log = AILog(
                agent_name=agent, task=task, result=result,
                provider=provider, model=model, duration_ms=duration_ms,
            )
            db.add(log)
