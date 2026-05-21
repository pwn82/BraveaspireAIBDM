import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from app.services.crm_service import CRMService
from backend.auth import get_current_user

router = CRMService()
api    = APIRouter(prefix="/api/companies", tags=["companies"])
crm    = CRMService()


class CompanyCreate(BaseModel):
    name: str
    website: Optional[str] = ""
    industry: Optional[str] = ""
    location: Optional[str] = ""
    employee_size: Optional[int] = 0
    revenue: Optional[str] = ""
    score: Optional[int] = 70
    status: Optional[str] = "New"
    hiring_status: Optional[bool] = False
    tech_stack: Optional[str] = ""
    pain_points: Optional[str] = ""
    notes: Optional[str] = ""
    source: Optional[str] = "Manual"


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    score: Optional[int] = None
    notes: Optional[str] = None
    hiring_status: Optional[bool] = None


@api.get("/")
def list_companies(
    search: str = Query(""),
    industry: str = Query(""),
    status: str = Query(""),
    user=Depends(get_current_user),
):
    return crm.get_companies(search=search, industry=industry, status=status)


@api.post("/", status_code=201)
def create_company(body: CompanyCreate, user=Depends(get_current_user)):
    return crm.add_company(body.model_dump())


@api.put("/{company_id}")
def update_company(company_id: int, body: CompanyUpdate, user=Depends(get_current_user)):
    data   = {k: v for k, v in body.model_dump().items() if v is not None}
    result = crm.update_company(company_id, data)
    if not result:
        raise HTTPException(404, "Company not found")
    return result


@api.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, user=Depends(get_current_user)):
    if not crm.delete_company(company_id):
        raise HTTPException(404, "Company not found")


@api.get("/industries")
def get_industries(user=Depends(get_current_user)):
    return crm.get_industries()
