"""
FastAPI auth + authorization dependencies.

Chain enforced by every endpoint:
  1. Authenticate   — valid JWT     → 401 otherwise
  2. Organization   — user has org  → 403 otherwise
  3. Role/Permission— has perm      → 403 otherwise
  4. Ownership      — scoped CRMService returns None for cross-tenant IDs

`require_permission(perm)` is a factory: `Depends(require_permission("company.read"))`
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.auth_service import decode_token, get_user_by_id
from app.utils.permissions import has_permission, ROLE_DISPLAY

bearer = HTTPBearer(auto_error=False)


# ── Authentication ───────────────────────────────────────────────────────────

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = get_user_by_id(int(payload["sub"]))
    if not user or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def optional_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds:
        return None
    payload = decode_token(creds.credentials)
    if not payload:
        return None
    return get_user_by_id(int(payload["sub"]))


# ── Authorization ────────────────────────────────────────────────────────────

def require_admin(user: dict = Depends(get_current_user)):
    """Legacy helper — prefer require_permission for new endpoints."""
    if user.get("role") not in ("super_admin", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def require_permission(permission: str):
    """
    Return a FastAPI dependency that enforces `permission`.

    Usage:
        @api.get("/", dependencies=[Depends(require_permission("company.read"))])
        def list_companies(...): ...

    or bound to a variable so it also injects the user:
        @api.get("/")
        def list_companies(user=Depends(require_permission("company.read"))): ...

    Failure modes:
      • no/invalid token           → 401 Unauthorized (from get_current_user)
      • user has no org membership → 403 Forbidden
      • role lacks the permission  → 403 Forbidden
    """
    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if not user.get("organization_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no organization membership",
            )
        if not has_permission(user, permission):
            role = user.get("role", "viewer")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied. Role '{ROLE_DISPLAY.get(role, role)}' "
                    f"does not have permission '{permission}'."
                ),
            )
        return user
    return _dep


# ── Multi-tenancy dependency (Phase 1, Chunk 3) ──────────────────────────────

def get_scoped_crm(user: dict = Depends(get_current_user)):
    """
    Returns a CRMService bound to the caller's org.

    Use this for endpoints that don't need a specific permission beyond
    authentication + org membership. For permissioned endpoints, prefer
    `get_scoped_crm_for(<perm>)` below so the permission check runs first.
    """
    from app.services.crm_service import CRMService
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no organization membership",
        )
    return CRMService(organization_id=org_id)


def get_scoped_crm_for(permission: str):
    """
    Composed dependency: enforce `permission` AND return a scoped CRMService.

    Usage:
        @api.get("/")
        def list(crm: CRMService = Depends(get_scoped_crm_for("company.read"))): ...
    """
    perm_dep = require_permission(permission)
    def _dep(user: dict = Depends(perm_dep)):
        from app.services.crm_service import CRMService
        return CRMService(organization_id=user["organization_id"])
    return _dep
