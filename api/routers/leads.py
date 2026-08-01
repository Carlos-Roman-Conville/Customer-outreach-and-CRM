from fastapi import APIRouter, HTTPException, Query

from api.deps import current_user_id
from api.schemas import DealPatch, NoteIn, StatusPatch
from api.services.leads import add_note, get_lead_detail, search_leads, update_deal
from services.dispositions import patch_lead_status

router = APIRouter()


@router.get("/leads")
def list_leads(
    q: str | None = None,
    county: str | None = None,
    category: str | None = None,
    segment: str | None = None,
    status: str | None = None,
    min_score: float | None = None,
    has_email: bool | None = None,
    has_phone: bool | None = None,
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    return search_leads(
        q=q, county=county, category=category, segment=segment, status=status,
        min_score=min_score, has_email=has_email, has_phone=has_phone,
        west=west, south=south, east=east, north=north,
        page=page, page_size=page_size,
    )


@router.get("/leads/{business_id}")
def lead_detail(business_id: str):
    try:
        return get_lead_detail(business_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/leads/{business_id}/status")
def update_status(business_id: str, body: StatusPatch):
    try:
        patch_lead_status(business_id, body.status, changed_by=current_user_id())
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/leads/{business_id}/notes")
def create_note(business_id: str, body: NoteIn):
    return add_note(business_id, body.body, current_user_id())


@router.patch("/leads/{business_id}/deal")
def patch_deal(business_id: str, body: DealPatch):
    return update_deal(
        business_id,
        current_user_id(),
        value=body.value,
        probability=body.probability,
        stage=body.stage,
        expected_close=body.expected_close,
    )
