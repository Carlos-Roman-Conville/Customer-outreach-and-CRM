"""Metadata for filters (categories, counts)."""
from __future__ import annotations

from category_tiers import QUEUE_ELIGIBLE_WHERE, QUEUE_TIER_ORDER
from config import CALL_QUEUE_MIN_SCORE, ICP_SCORE_VERSION
from db import connect


def get_app_config() -> dict:
    return {
        "call_queue_min_score": CALL_QUEUE_MIN_SCORE,
        "score_version": ICP_SCORE_VERSION,
        "max_score": 58,
    }


def _normalize_categories(categories: list[str] | str | None) -> list[str]:
    if not categories:
        return []
    if isinstance(categories, str):
        return [categories] if categories.strip() else []
    return [c for c in categories if c and c.strip()]


def _callable_where() -> str:
    return f"""
        {QUEUE_ELIGIBLE_WHERE}
        AND t.icp_score >= ?
        AND EXISTS (
            SELECT 1 FROM contacts c
            WHERE c.business_id = b.gers_id AND c.kind = 'phone'
        )
    """


def list_categories(
    q: str | None = None,
    limit: int = 50,
    callable_only: bool = True,
) -> list[dict]:
    limit = max(1, min(limit, 200))
    params: list = []
    where = ["b.category IS NOT NULL", "b.category != ''"]

    if callable_only:
        where.append(_callable_where())
        params.append(CALL_QUEUE_MIN_SCORE)

    if q:
        normalized = q.replace(" ", "_").lower()
        where.append("LOWER(b.category) LIKE ?")
        params.append(f"%{normalized}%")

    where_sql = " AND ".join(where)
    join = "JOIN targets t ON t.business_id = b.gers_id" if callable_only else "LEFT JOIN targets t ON t.business_id = b.gers_id"

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                b.category AS category,
                COUNT(DISTINCT b.gers_id) AS total,
                COUNT(DISTINCT CASE
                    WHEN EXISTS (
                        SELECT 1 FROM contacts c2
                        WHERE c2.business_id = b.gers_id AND c2.kind = 'email'
                    ) THEN b.gers_id
                END) AS with_email
            FROM businesses b
            {join}
            WHERE {where_sql}
            GROUP BY b.category
            ORDER BY total DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()

    return [
        {
            "category": r["category"],
            "total": int(r["total"]),
            "with_email": int(r["with_email"]),
        }
        for r in rows
    ]


def counts_for_categories(categories: list[str]) -> dict:
    cats = _normalize_categories(categories)
    if not cats:
        return {"total": 0, "with_email": 0}

    placeholders = ",".join("?" * len(cats))
    params = [*cats, CALL_QUEUE_MIN_SCORE]

    with connect() as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(DISTINCT b.gers_id) AS total,
                COUNT(DISTINCT CASE
                    WHEN EXISTS (
                        SELECT 1 FROM contacts c2
                        WHERE c2.business_id = b.gers_id AND c2.kind = 'email'
                    ) THEN b.gers_id
                END) AS with_email
            FROM businesses b
            JOIN targets t ON t.business_id = b.gers_id
            WHERE b.category IN ({placeholders})
              AND {QUEUE_ELIGIBLE_WHERE}
              AND t.icp_score >= ?
              AND EXISTS (
                  SELECT 1 FROM contacts c
                  WHERE c.business_id = b.gers_id AND c.kind = 'phone'
              )
            """,
            params,
        ).fetchone()

    return {
        "total": int(row["total"] or 0),
        "with_email": int(row["with_email"] or 0),
    }
