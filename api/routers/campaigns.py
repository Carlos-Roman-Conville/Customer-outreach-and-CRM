from fastapi import APIRouter, HTTPException

from api.services.campaigns import campaign_detail, list_campaigns

router = APIRouter()


@router.get("/campaigns")
def campaigns():
    return {"items": list_campaigns()}


@router.get("/campaigns/{batch_id}")
def campaign(batch_id: str):
    detail = campaign_detail(batch_id)
    if not detail["items"] and not batch_id:
        raise HTTPException(status_code=404, detail="Batch not found")
    return detail
