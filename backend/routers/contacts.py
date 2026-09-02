import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from app.services.crm_service import CRMService
from backend.auth import get_scoped_crm_for

api = APIRouter(prefix="/api/contacts", tags=["contacts"])


class ContactCreate(BaseModel):
    company_id: int
    name: str
    designation: Optional[str] = ""
    email: Optional[str] = ""
    linkedin: Optional[str] = ""
    phone: Optional[str] = ""
    verified: Optional[bool] = False
    notes: Optional[str] = ""


@api.get("/")
def list_contacts(
    company_id: Optional[int] = Query(None),
    search: str = Query(""),
    crm: CRMService = Depends(get_scoped_crm_for("contact.read")),
):
    return crm.get_contacts(company_id=company_id, search=search)


@api.post("/", status_code=201)
def create_contact(body: ContactCreate,
                   crm: CRMService = Depends(get_scoped_crm_for("contact.create"))):
    result = crm.add_contact(body.model_dump())
    if not result:
        raise HTTPException(404, "Company not found in your organization")
    return result


@api.put("/{contact_id}")
def update_contact(contact_id: int, body: dict,
                   crm: CRMService = Depends(get_scoped_crm_for("contact.update"))):
    result = crm.update_contact(contact_id, body)
    if not result:
        raise HTTPException(404, "Contact not found")
    return result
