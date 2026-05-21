import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends
from app.services.crm_service import CRMService
from app.services.email_tracking_service import get_tracking_stats
from app.services.auth_service import get_audit_logs
from backend.auth import get_current_user, require_admin

api = APIRouter(prefix="/api/analytics", tags=["analytics"])
crm = CRMService()


@api.get("/pipeline")
def get_pipeline(user=Depends(get_current_user)):
    return crm.get_pipeline_stats()


@api.get("/tracking")
def get_tracking(user=Depends(get_current_user)):
    return get_tracking_stats()


@api.get("/audit-logs")
def get_audit(limit: int = 50, user=Depends(require_admin)):
    return get_audit_logs(limit=limit)
