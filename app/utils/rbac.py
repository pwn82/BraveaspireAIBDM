"""
Role-Based Access Control (RBAC)
=================================
Roles (highest → lowest):
  super_admin     — full access to everything, including user management
  admin           — manage users, full CRM access, all pages
  sales_manager   — view all leads/outreach, run workflows, view analytics
  bdm             — manage own leads, send outreach, run AI workflow
  sales_executive — view/add companies and contacts, send emails
  viewer          — read-only access to companies and analytics
"""

from __future__ import annotations
from typing import Optional
import streamlit as st

# ── Role list (ordered highest → lowest privilege) ───────────────────────────
ROLES = ["super_admin", "admin", "sales_manager", "bdm", "sales_executive", "viewer"]

# ── Permission catalogue ──────────────────────────────────────────────────────
# Each permission maps to a set of roles that hold it.
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
}

# ── Role hierarchy (higher index = more permissions via explicit PERMISSIONS) ──
ROLE_HIERARCHY = ["viewer", "sales_executive", "bdm", "sales_manager", "admin", "super_admin"]

ROLE_DISPLAY = {
    "super_admin":     "🔴 Super Admin",
    "admin":           "🟠 Admin",
    "sales_manager":   "🟡 Sales Manager",
    "bdm":             "🔵 BDM",
    "sales_executive": "🟢 Sales Executive",
    "viewer":          "⚪ Viewer",
}

ROLE_DESCRIPTIONS = {
    "super_admin":     "Full system access including user deletion and system settings",
    "admin":           "User management, full CRM access, all features",
    "sales_manager":   "Manage team, full analytics, run workflows, approve outreach",
    "bdm":             "Manage leads, run AI workflow, send outreach, AI chat",
    "sales_executive": "Add/view companies & contacts, send emails, follow-ups",
    "viewer":          "Read-only access to companies and analytics",
}


# ── Core helpers ──────────────────────────────────────────────────────────────

def has_permission(user: Optional[dict], permission: str) -> bool:
    """Check if a user dict has a specific permission."""
    if not user:
        return False
    role = user.get("role", "viewer")
    return role in PERMISSIONS.get(permission, [])


def has_role(user: Optional[dict], *roles: str) -> bool:
    """Check if a user has any of the given roles."""
    if not user:
        return False
    return user.get("role") in roles


def is_admin(user: Optional[dict]) -> bool:
    return has_role(user, "super_admin", "admin")


def require_permission(permission: str, user: Optional[dict] = None) -> bool:
    """
    In a Streamlit page, call this to gate access.
    If user is None, reads from st.session_state.
    Returns True if allowed, False + shows error message if not.
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
    """Just ensure the user is authenticated."""
    if user is None:
        user = st.session_state.get("user")
    if not st.session_state.get("authenticated") or not user:
        st.error("🔒 Please log in to continue.")
        st.page_link("pages/0_Login.py", label="Go to Login", icon="🔐")
        st.stop()
    return user


def get_accessible_pages(user: Optional[dict]) -> list[str]:
    """Return list of page names accessible to this user."""
    if not user:
        return []
    role = user.get("role", "viewer")
    pages = []

    if has_permission(user, "company.read"):
        pages.append("Companies")
    if has_permission(user, "contact.read"):
        pages.append("Contacts")
    if has_permission(user, "outreach.read"):
        pages.append("Outreach")
    if has_permission(user, "followup.read"):
        pages.append("Follow-ups")
    if has_permission(user, "analytics.read"):
        pages.append("Analytics")
    if has_permission(user, "ai_chat.use"):
        pages.append("AI Chat")
    if has_permission(user, "settings.read"):
        pages.append("Settings")
    if has_permission(user, "workflow.run"):
        pages.append("Workflow")
    if has_permission(user, "scraping.run"):
        pages.append("Lead Scraper")
    if is_admin(user):
        pages.append("User Management")

    return pages
