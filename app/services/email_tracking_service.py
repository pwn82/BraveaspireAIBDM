"""
Email open / click tracking.
- Injects a 1×1 transparent GIF pixel into outgoing emails.
- The pixel URL hits FastAPI /track/open/{tracking_id}.
- FastAPI marks the outreach as Opened and increments open_count.
"""
import uuid
import base64
from datetime import datetime

# 1×1 transparent GIF (43 bytes)
TRANSPARENT_GIF = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


def generate_tracking_id() -> str:
    return str(uuid.uuid4())


def build_tracking_pixel_url(tracking_id: str, base_url: str) -> str:
    base_url = base_url.rstrip("/")
    return f"{base_url}/track/open/{tracking_id}"


def inject_tracking_pixel(body: str, tracking_id: str, base_url: str) -> str:
    """
    Append a hidden 1×1 pixel image to plain-text or HTML email body.
    For plain text we append as a tiny HTML footer; for HTML we inject before </body>.
    """
    pixel_url = build_tracking_pixel_url(tracking_id, base_url)
    pixel_tag = f'<img src="{pixel_url}" width="1" height="1" alt="" style="display:none" />'

    if "</body>" in body.lower():
        return body.replace("</body>", f"{pixel_tag}</body>")
    return body + f"\n\n{pixel_tag}"


def record_open(tracking_id: str):
    """Called by FastAPI tracking endpoint — marks outreach Opened."""
    from ..database.db import get_db
    from ..database.models import Outreach
    with get_db() as db:
        o = db.query(Outreach).filter(Outreach.tracking_id == tracking_id).first()
        if o:
            o.open_count = (o.open_count or 0) + 1
            if o.status == "Sent":
                o.status    = "Opened"
                o.opened_at = datetime.utcnow()


def record_click(tracking_id: str):
    """Record a link click event."""
    from ..database.db import get_db
    from ..database.models import Outreach
    with get_db() as db:
        o = db.query(Outreach).filter(Outreach.tracking_id == tracking_id).first()
        if o:
            o.click_count = (o.click_count or 0) + 1


def get_tracking_stats() -> dict:
    """Return aggregate open/click stats."""
    from ..database.db import get_db
    from ..database.models import Outreach
    from sqlalchemy import func
    with get_db() as db:
        total_opens  = db.query(func.sum(Outreach.open_count)).scalar()  or 0
        total_clicks = db.query(func.sum(Outreach.click_count)).scalar() or 0
        unique_opens = db.query(Outreach).filter(Outreach.open_count > 0).count()
        return {
            "total_opens":  total_opens,
            "total_clicks": total_clicks,
            "unique_opens": unique_opens,
        }
