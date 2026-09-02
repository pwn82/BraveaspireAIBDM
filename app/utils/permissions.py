"""
Permission catalog — Streamlit-free, safe to import from FastAPI, workers,
tests, or anywhere else.

`rbac.py` is the Streamlit-facing wrapper (session_state, st.stop, page_link).
Everything pure — the roles table, the permissions map, `has_permission()` —
lives here so `backend/*` can import it without dragging in `streamlit`.
"""
from __future__ import annotations
from typing import Optional


# ── Role list (ordered highest → lowest privilege) ───────────────────────────
ROLES = ["super_admin", "admin", "sales_manager", "bdm", "sales_executive", "viewer"]

ROLE_HIERARCHY = ["viewer", "sales_executive", "bdm", "sales_manager", "admin", "super_admin"]


# ── Permission catalog ────────────────────────────────────────────────────────
PERMISSIONS: dict[str, list[str]] = {
    # User management
    "user.create":          ["super_admin", "admin"],
    "user.read":            ["super_admin", "admin"],
    "user.update":          ["super_admin", "admin"],
    "user.delete":          ["super_admin"],
    "user.assign_role":     ["super_admin", "admin"],

    # Companies
    "company.create":       ["super_admin", "admin", "sales_manager", "bdm", "sales_executive"],
    "company.read":         ["super_admin", "admin", "sales_manager", "bdm", "sales_executive", "viewer"],
    "company.update":       ["super_admin", "admin", "sales_manager", "bdm", "sales_executive"],
    "company.delete":       ["super_admin", "admin", "sales_manager"],

    # Contacts
    "contact.create":       ["super_admin", "admin", "sales_manager", "bdm", "sales_executive"],
    "contact.read":         ["super_admin", "admin", "sales_manager", "bdm", "sales_executive", "viewer"],
    "contact.update":       ["super_admin", "admin", "sales_manager", "bdm", "sales_executive"],
    "contact.delete":       ["super_admin", "admin", "sales_manager"],

    # Outreach
    "outreach.create":      ["super_admin", "admin", "sales_manager", "bdm", "sales_executive"],
    "outreach.read":        ["super_admin", "admin", "sales_manager", "bdm", "sales_executive", "viewer"],
    "outreach.send":        ["super_admin", "admin", "sales_manager", "bdm", "sales_executive"],
    "outreach.delete":      ["super_admin", "admin", "sales_manager"],

    # Follow-ups
    "followup.create":      ["super_admin", "admin", "sales_manager", "bdm", "sales_executive"],
    "followup.send":        ["super_admin", "admin", "sales_manager", "bdm", "sales_executive"],
    "followup.read":        ["super_admin", "admin", "sales_manager", "bdm", "sales_executive", "viewer"],

    # Analytics
    "analytics.read":       ["super_admin", "admin", "sales_manager", "bdm", "viewer"],

    # AI Workflow
    "workflow.run":         ["super_admin", "admin", "sales_manager", "bdm"],
    "workflow.hitl":        ["super_admin", "admin", "sales_manager", "bdm"],

    # AI Chat
    "ai_chat.use":          ["super_admin", "admin", "sales_manager", "bdm", "sales_executive"],

    # Settings
    "settings.read":        ["super_admin", "admin"],
    "settings.update":      ["super_admin", "admin"],

    # Lead scraping
    "scraping.run":         ["super_admin", "admin", "sales_manager", "bdm"],

    # Billing
    "billing.read":         ["super_admin", "admin"],
    "billing.manage":       ["super_admin"],
}

# Convenience — display strings used by both Streamlit UI and API error messages.
ROLE_DISPLAY = {
    "super_admin":     "Super Admin",
    "admin":           "Admin",
    "sales_manager":   "Sales Manager",
    "bdm":             "BDM",
    "sales_executive": "Sales Executive",
    "viewer":          "Viewer",
}

ROLE_DESCRIPTIONS = {
    "super_admin":     "Full system access including user deletion and system settings",
    "admin":           "User management, full CRM access, all features",
    "sales_manager":   "Manage team, full analytics, run workflows, approve outreach",
    "bdm":             "Manage leads, run AI workflow, send outreach, AI chat",
    "sales_executive": "Add/view companies & contacts, send emails, follow-ups",
    "viewer":          "Read-only access to companies and analytics",
}


# ── Pure helpers (no streamlit, no fastapi) ──────────────────────────────────

def has_permission(user: Optional[dict], permission: str) -> bool:
    """Return True iff `user` holds `permission`."""
    if not user:
        return False
    role = user.get("role", "viewer")
    return role in PERMISSIONS.get(permission, [])


def has_role(user: Optional[dict], *roles: str) -> bool:
    if not user:
        return False
    return user.get("role") in roles


def is_admin(user: Optional[dict]) -> bool:
    return has_role(user, "super_admin", "admin")
