"""
IMAP inbox monitoring service.
Connects to Gmail/Outlook, detects replies to sent outreach, updates CRM status.
"""
import imaplib
import email
import logging
import re
from datetime import datetime, timedelta
from email.header import decode_header
from typing import Optional

logger = logging.getLogger("imap")


class IMAPService:
    def __init__(self, host: str, port: int, username: str, password: str):
        self.host     = host
        self.port     = port
        self.username = username
        self.password = password

    def _connect(self) -> imaplib.IMAP4_SSL:
        mail = imaplib.IMAP4_SSL(self.host, self.port)
        mail.login(self.username, self.password)
        return mail

    def test_connection(self) -> tuple[bool, str]:
        try:
            mail = self._connect()
            mail.logout()
            return True, f"Connected to {self.host} as {self.username}"
        except Exception as e:
            return False, str(e)

    def check_replies(self, days_back: int = 7) -> int:
        """
        Scan inbox for replies to tracked outreach emails.
        Returns count of newly detected replies.
        """
        from ..database.db import get_db
        from ..database.models import Outreach, Contact

        try:
            mail    = self._connect()
            count   = 0
            mail.select("INBOX")

            # Search since N days ago
            since_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%d-%b-%Y")
            _, msg_ids = mail.search(None, f'(SINCE "{since_date}")')

            if not msg_ids or not msg_ids[0]:
                mail.logout()
                return 0

            with get_db() as db:
                sent_outreach = db.query(Outreach).filter(
                    Outreach.status.in_(["Sent", "Opened"])
                ).all()
                # Build subject → outreach map
                subj_map: dict[str, Outreach] = {}
                for o in sent_outreach:
                    if o.subject:
                        clean = re.sub(r"^(Re:|Fwd?:|FW:)\s*", "", o.subject, flags=re.I).strip().lower()
                        subj_map[clean] = o

                for mid in msg_ids[0].split():
                    try:
                        _, data = mail.fetch(mid, "(RFC822)")
                        raw     = data[0][1]
                        msg     = email.message_from_bytes(raw)
                        subject = _decode_header_str(msg.get("Subject", ""))
                        sender  = msg.get("From", "")

                        clean_subj = re.sub(r"^(Re:|Fwd?:|FW:)\s*", "", subject,
                                             flags=re.I).strip().lower()

                        if clean_subj in subj_map:
                            outreach = subj_map[clean_subj]
                            if outreach.status in ("Sent", "Opened"):
                                outreach.status     = "Replied"
                                outreach.replied_at = datetime.utcnow()
                                count += 1
                                logger.info(f"Reply detected for outreach #{outreach.id}: {subject}")

                    except Exception as e:
                        logger.debug(f"Email parse error: {e}")
                        continue

            mail.logout()
            return count

        except Exception as e:
            logger.error(f"IMAP check_replies error: {e}")
            return 0

    def get_recent_messages(self, limit: int = 20) -> list[dict]:
        """Fetch recent inbox messages for display."""
        messages = []
        try:
            mail = self._connect()
            mail.select("INBOX")
            _, msg_ids = mail.search(None, "ALL")
            if not msg_ids or not msg_ids[0]:
                mail.logout()
                return []

            recent_ids = msg_ids[0].split()[-limit:]
            for mid in reversed(recent_ids):
                try:
                    _, data = mail.fetch(mid, "(RFC822.HEADER)")
                    raw     = data[0][1]
                    msg     = email.message_from_bytes(raw)
                    messages.append({
                        "subject": _decode_header_str(msg.get("Subject", "(no subject)")),
                        "from":    msg.get("From", ""),
                        "date":    msg.get("Date", ""),
                    })
                except Exception:
                    continue
            mail.logout()
        except Exception as e:
            logger.warning(f"get_recent_messages error: {e}")
        return messages


def _decode_header_str(value: str) -> str:
    try:
        parts = decode_header(value)
        decoded = []
        for part, enc in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(enc or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return " ".join(decoded)
    except Exception:
        return value or ""
