from fastapi import APIRouter, HTTPException, Query

from api.deps import current_user_id
from api.schemas import DispositionIn
from api.services.queue import fetch_queue
from services.dispositions import record_disposition, undo_last_disposition

router = APIRouter()


@router.get("/queue")
def get_queue(
    limit: int = Query(40, ge=1, le=200),
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
):
    return {"items": fetch_queue(limit, west, south, east, north)}


@router.post("/queue/{business_id}/log")
def log_disposition(business_id: str, body: DispositionIn):
    try:
        result = record_disposition(
            business_id,
            body.disposition,
            notes=body.notes,
            callback_days=body.callback_days,
            callback_date=body.callback_date,
            changed_by=current_user_id(),
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/queue/{business_id}/undo")
def undo_disposition(business_id: str):
    ok = undo_last_disposition(business_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Nothing to undo")
    return {"ok": True}
