from fastapi import APIRouter, Query

from api.services.leads import global_search

router = APIRouter()


@router.get("/search")
def search(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=50)):
    return {"items": global_search(q, limit=limit)}
