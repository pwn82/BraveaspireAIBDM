"""
Streamlit-facing RBAC helpers.

Pure permission data + `has_permission()` live in `permissions.py` — safe to
import from FastAPI, workers, tests. This file wraps them with Streamlit
side-effects (st.stop, page_link, session_state) and adds tenant context.
"""
from __future__ import annotations
from typing import Optional
import streamlit as st

# Re-export the pure surface so existing callers importing from rbac.py keep working.
from .permissions import (  # noqa: F401
    ROLES,
    ROLE_HIERARCHY,
    PERMISSIONS,
    ROLE_DISPLAY,
    ROLE_DESCRIPTIONS,
    has_permission,
    has_role,
    is_admin,
)


def require_permission(permission: str, user: Optional[dict] = None) -> bool:
    """
    Streamlit page-level gate. Halts rendering if user lacks the permission.
    Returns True if allowed; never returns False (calls st.stop() instead).
    """
    if user is None:
        user = st.session_state.get("user")
    if not user:
        st.error("🔒 You must be logged in to access this page.")
        st.stop()
        return False
    if not has_permission(user, permission):
        role = user.get("role", "viewer")
        st.error(
            f"🚫 Access denied. Your role **{ROLE_DISPLAY.get(role, role)}** "
            f"does not have the `{permission}` permission."
        )
        st.stop()
        return False
    return True


def require_auth(user: Optional[dict] = None):
    """Ensure the user is authenticated (any role); halt rendering otherwise."""
    if user is None:
        user = st.session_state.get("user")
    if not st.session_state.get("authenticated") or not user:
        st.error("🔒 Please log in to continue.")
        st.page_link("pages/0_Login.py", label="Go to Login", icon="🔐")
        st.stop()
    return user


def get_accessible_pages(user: Optional[dict]) -> list[str]:
    """Return the list of page names this user's role can open."""
    if not user:
        return []
    pages = []
    if has_permission(user, "company.read"):     pages.append("Companies")
    if has_permission(user, "contact.read"):     pages.append("Contacts")
    if has_permission(user, "outreach.read"):    pages.append("Outreach")
    if has_permission(user, "followup.read"):    pages.append("Follow-ups")
    if has_permission(user, "analytics.read"):   pages.append("Analytics")
    if has_permission(user, "ai_chat.use"):      pages.append("AI Chat")
    if has_permission(user, "settings.read"):    pages.append("Settings")
    if has_permission(user, "workflow.run"):     pages.append("Workflow")
    if has_permission(user, "scraping.run"):     pages.append("Lead Scraper")
    if is_admin(user):                           pages.append("User Management")
    return pages


# ── Multi-tenancy (Phase 1) ───────────────────────────────────────────────────

def get_current_org_id(user: Optional[dict] = None) -> Optional[int]:
    """
    Return the current user's active organization id.

    Resolution order:
      1. user["organization_id"]              — set at login
      2. st.session_state["organization_id"]  — set at login
      3. DB lookup via OrganizationUser       — fallback

    Returns None if the user has no active org membership.
    """
    if user is None:
        user = st.session_state.get("user")
    if not user:
        return None

    org_id = user.get("organization_id")
    if org_id:
        return int(org_id)

    ss_org = st.session_state.get("organization_id")
    if ss_org:
        return int(ss_org)

    user_id = user.get("id")
    if not user_id:
        return None
    from ..database.db import get_db
    from ..database.models import OrganizationUser
    with get_db() as db:
        membership = (
            db.query(OrganizationUser)
            .filter(OrganizationUser.user_id == user_id)
            .filter(OrganizationUser.status == "active")
            .order_by(OrganizationUser.created_at.asc())
            .first()
        )
        return membership.organization_id if membership else None
