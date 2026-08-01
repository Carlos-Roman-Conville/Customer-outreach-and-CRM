from fastapi import APIRouter

from api.services.stats import get_stats

router = APIRouter()


@router.get("/stats")
def stats():
    return get_stats()
