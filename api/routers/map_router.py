from fastapi import APIRouter, Query

from api.services.leads import county_stats, map_points

router = APIRouter()


@router.get("/map/counties")
def get_map_counties(
    min_score: float = Query(25.0),
    status: str | None = None,
    category: list[str] | None = Query(None),
):
    return county_stats(min_score=min_score, category=category, status=status)


@router.get("/map/points")
def get_map_points(
    west: float = Query(...),
    south: float = Query(...),
    east: float = Query(...),
    north: float = Query(...),
    limit: int = Query(5000, ge=1, le=10000),
    min_score: float = Query(25.0),
    county: str | None = None,
    status: str | None = None,
    category: list[str] | None = Query(None),
    batch_id: str | None = None,
    mode: str = Query("hunt"),
    overdue_only: bool = Query(False),
):
    return map_points(
        west,
        south,
        east,
        north,
        limit=limit,
        min_score=min_score,
        county=county,
        status=status,
        category=category,
        batch_id=batch_id,
        mode=mode,
        overdue_only=overdue_only,
    )
