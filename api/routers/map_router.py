from fastapi import APIRouter, Query

from api.services.leads import map_points

router = APIRouter()


@router.get("/map/points")
def get_map_points(
    west: float = Query(...),
    south: float = Query(...),
    east: float = Query(...),
    north: float = Query(...),
    limit: int = Query(5000, ge=1, le=10000),
    min_score: float = Query(25.0),
):
    return map_points(west, south, east, north, limit=limit, min_score=min_score)
