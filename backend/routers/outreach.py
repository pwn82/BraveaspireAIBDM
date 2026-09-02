import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from app.services.crm_service import CRMService
from backend.auth import get_scoped_crm_for

api = APIRouter(prefix="/api/outreach", tags=["outreach"])


class OutreachCreate(BaseModel):
    contact_id: int
    subject: str
    body: str
    status: Optional[str] = "Draft"


class OutreachUpdate(BaseModel):
    status: Optional[str]   = None
    subject: Optional[str]  = None
    body: Optional[str]     = None


@api.get("/")
def list_outreach(
    status: str = Query(""),
    contact_id: Optional[int] = Query(None),
    crm: CRMService = Depends(get_scoped_crm_for("outreach.read")),
):
    return crm.get_outreach(status=status, contact_id=contact_id)


@api.post("/", status_code=201)
def create_outreach(body: OutreachCreate,
                    crm: CRMService = Depends(get_scoped_crm_for("outreach.create"))):
    import uuid
    data = body.model_dump()
    data["tracking_id"] = str(uuid.uuid4())
    result = crm.create_outreach(data)
    if not result:
        raise HTTPException(404, "Contact not found in your organization")
    return result


@api.put("/{outreach_id}")
def update_outreach(outreach_id: int, body: OutreachUpdate,
                    crm: CRMService = Depends(get_scoped_crm_for("outreach.create"))):
    data   = {k: v for k, v in body.model_dump().items() if v is not None}
    result = crm.update_outreach(outreach_id, data)
    if not result:
        raise HTTPException(404, "Outreach not found")
    return result


@api.get("/followups")
def list_followups(status: str = Query(""),
                   crm: CRMService = Depends(get_scoped_crm_for("followup.read"))):
    return crm.get_followups(status=status)
