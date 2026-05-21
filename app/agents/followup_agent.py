from datetime import datetime, timedelta
from ..services.ai_service import AIService
from ..services.crm_service import CRMService

FOLLOWUP_SCHEDULE = {1: 3, 2: 7, 3: 14}  # sequence -> days after initial send


class FollowUpAgent:
    name = "Follow-up Agent"

    def __init__(self, ai: AIService, crm: CRMService):
        self.ai = ai
        self.crm = crm

    def schedule_followups(self, outreach_id: int, outreach: dict, contact: dict, company: dict) -> list[dict]:
        """Create 3 follow-up records for an outreach (Day 3, 7, 14)."""
        followups = []
        base_date = datetime.utcnow()
        original_subject = outreach.get("subject", "")

        for seq, days in FOLLOWUP_SCHEDULE.items():
            scheduled = base_date + timedelta(days=days)
            body = self._quick_followup_body(seq, contact.get("name", "there"), company.get("name", "your company"))
            fu = self.crm.add_followup({
                "outreach_id": outreach_id,
                "subject": f"Re: {original_subject}",
                "body": body,
                "sequence_number": seq,
                "scheduled_at": scheduled,
                "status": "Scheduled",
            })
            followups.append(fu)
        return followups

    def detect_overdue(self) -> list[dict]:
        """Return follow-ups that are scheduled but past their date."""
        all_fus = self.crm.get_followups(status="Scheduled")
        now = datetime.utcnow()
        overdue = []
        for fu in all_fus:
            scheduled_str = fu.get("scheduled_at", "")
            if scheduled_str:
                try:
                    scheduled = datetime.strptime(scheduled_str, "%Y-%m-%d")
                    if scheduled <= now:
                        overdue.append(fu)
                except ValueError:
                    pass
        return overdue

    def generate_smart_followup(self, contact: dict, company: dict, seq: int, original_subject: str) -> str:
        """Use AI to generate a smarter follow-up body."""
        prompt = f"""Write a brief follow-up #{seq} email body (under 80 words).
Contact: {contact.get('name')}, {contact.get('designation')} at {company.get('name')}
Original subject: {original_subject}
Add a new angle or value prop. End with an easy yes/no question."""
        return self.ai.generate(prompt)

    def _quick_followup_body(self, seq: int, name: str, company: str) -> str:
        angles = {
            1: f"Hi {name},\n\nJust following up on my previous email about {company}. "
               f"I know inboxes get busy — wanted to make sure this didn't get lost.\n\n"
               f"Would a quick 15-minute call this week work for you?\n\nBest,\nBraveAspire Team",
            2: f"Hi {name},\n\nI wanted to share a quick win: we recently helped a company similar to {company} "
               f"reduce their development cycle by 35%.\n\n"
               f"Would this kind of result be interesting for your team?\n\nBest,\nBraveAspire Team",
            3: f"Hi {name},\n\nThis will be my last follow-up — I don't want to clutter your inbox.\n\n"
               f"If the timing isn't right now, no worries at all. Just reply 'not now' and I'll check back in a few months.\n\n"
               f"Either way, wishing {company} continued success!\n\nBest,\nBraveAspire Team",
        }
        return angles.get(seq, angles[1])
