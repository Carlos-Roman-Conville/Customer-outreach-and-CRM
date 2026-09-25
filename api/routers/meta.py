from fastapi import APIRouter, Query

from api.services.meta import counts_for_categories, get_app_config, list_categories

router = APIRouter()


@router.get("/meta/config")
def get_config():
    return get_app_config()


@router.get("/meta/categories")
def get_categories(
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    callable_only: bool = True,
):
    return {"items": list_categories(q=q, limit=limit, callable_only=callable_only)}


@router.get("/meta/categories/count")
def get_category_count(category: list[str] | None = Query(None)):
    return counts_for_categories(category or [])
