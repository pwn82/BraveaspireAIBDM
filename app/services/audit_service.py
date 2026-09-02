"""
Shared audit-log writer.

`auth_service.py` has its own private `_audit()` helper for auth events;
this module is the public equivalent for everywhere else (outreach
approval/send, suppression changes, contact verification overrides,
billing/role changes) so those call sites don't have to reach into
auth_service's internals or hand-roll AuditLog inserts.

Call sites should log the *decision*, not the payload — `details` is
free text capped at 500 chars, not a place to dump an email body.
"""
from __future__ import annotations

from typing import Optional

from ..database.db import get_db
from ..database.models import AuditLog


def log_audit(
    action: str,
    *,
    organization_id: Optional[int] = None,
    user_id: Optional[int] = None,
    resource: Optional[str] = None,
    resource_id: Optional[int] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Insert one audit_logs row. Never raises — an audit failure must not
    block the business action it's describing."""
    try:
        with get_db() as db:
            db.add(AuditLog(
                organization_id=organization_id,
                user_id=user_id,
                action=action,
                resource=resource,
                resource_id=resource_id,
                details=(details or "")[:500],
                ip_address=ip_address,
            ))
    except Exception:                                                   # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("audit log write failed: action=%s", action)
