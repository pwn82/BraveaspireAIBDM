import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends
from app.services.crm_service import CRMService
from app.services.email_tracking_service import get_tracking_stats
from app.services.auth_service import get_audit_logs
from backend.auth import require_permission, get_scoped_crm_for

api = APIRouter(prefix="/api/analytics", tags=["analytics"])


@api.get("/pipeline")
def get_pipeline(crm: CRMService = Depends(get_scoped_crm_for("analytics.read"))):
    return crm.get_pipeline_stats()


@api.get("/tracking")
def get_tracking(user=Depends(require_permission("analytics.read"))):
    return get_tracking_stats()


@api.get("/audit-logs")
def get_audit(limit: int = 50, user=Depends(require_permission("user.read"))):
    return get_audit_logs(limit=limit)
