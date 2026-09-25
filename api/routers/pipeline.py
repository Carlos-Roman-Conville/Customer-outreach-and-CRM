from datetime import date, timedelta

from fastapi import APIRouter, Query

from category_tiers import QUEUE_ELIGIBLE_WHERE, QUEUE_TIER_ORDER
from config import CALL_QUEUE_MIN_SCORE
from db import connect
from api.demo import scrub_name

router = APIRouter()

STAGES = ["new", "working", "meeting", "won", "dead"]
STALE_DAYS = 14


@router.get("/pipeline")
def pipeline_board(new_limit: int = Query(25, ge=1, le=200)):
    stale_cutoff = (date.today() - timedelta(days=STALE_DAYS)).isoformat()
    columns = {stage: {"total": 0, "deal_value": 0.0, "items": []} for stage in STAGES}

    with connect() as conn:
        totals = conn.execute(
            f"""
            SELECT t.status,
                   COUNT(*) AS total,
                   COALESCE(SUM(d.value), 0) AS deal_value
            FROM targets t
            LEFT JOIN deals d ON d.business_id = t.business_id
            WHERE {QUEUE_ELIGIBLE_WHERE}
              AND t.icp_score >= ?
              AND t.status IN ('new', 'working', 'meeting', 'won', 'dead')
            GROUP BY t.status
            """,
            (CALL_QUEUE_MIN_SCORE,),
        ).fetchall()
        for row in totals:
            status = row["status"] if row["status"] in STAGES else "new"
            columns[status]["total"] = int(row["total"])
            columns[status]["deal_value"] = round(float(row["deal_value"] or 0), 2)

        rows = conn.execute(
            f"""
            SELECT
                t.business_id,
                t.status,
                t.icp_score,
                t.revenue_tier,
                t.segment,
                b.name,
                COALESCE(d.value, 0) AS deal_value,
                (
                    SELECT MAX(completed_at) FROM touches
                    WHERE business_id = t.business_id AND completed_at IS NOT NULL
                ) AS last_completed_at,
                (
                    SELECT MIN(scheduled_for) FROM touches
                    WHERE business_id = t.business_id
                      AND completed_at IS NULL
                      AND scheduled_for IS NOT NULL
                ) AS next_scheduled,
                EXISTS (
                    SELECT 1 FROM contacts c
                    WHERE c.business_id = t.business_id AND c.kind = 'phone'
                ) AS has_phone,
                EXISTS (
                    SELECT 1 FROM contacts c
                    WHERE c.business_id = t.business_id AND c.kind = 'email'
                ) AS has_email,
                CASE
                    WHEN t.status IN ('working', 'meeting') AND (
                        (
                            SELECT MAX(completed_at) FROM touches
                            WHERE business_id = t.business_id AND completed_at IS NOT NULL
                        ) IS NULL
                        OR date((
                            SELECT MAX(completed_at) FROM touches
                            WHERE business_id = t.business_id AND completed_at IS NOT NULL
                        )) < date(?)
                    ) THEN 1
                    ELSE 0
                END AS is_stale
            FROM targets t
            JOIN businesses b ON b.gers_id = t.business_id
            LEFT JOIN deals d ON d.business_id = t.business_id
            WHERE {QUEUE_ELIGIBLE_WHERE}
              AND t.icp_score >= ?
              AND t.status IN ('new', 'working', 'meeting', 'won', 'dead')
            ORDER BY is_stale DESC, {QUEUE_TIER_ORDER}, t.icp_score DESC, b.name ASC
            """,
            (stale_cutoff, CALL_QUEUE_MIN_SCORE),
        ).fetchall()

    per_stage: dict[str, list] = {stage: [] for stage in STAGES}
    for row in rows:
        status = row["status"] if row["status"] in STAGES else "new"
        bid = row["business_id"]
        per_stage[status].append({
            "business_id": bid,
            "name": scrub_name(row["name"], bid),
            "icp_score": row["icp_score"],
            "revenue_tier": row["revenue_tier"],
            "segment": row["segment"],
            "deal_value": float(row["deal_value"] or 0),
            "last_completed_at": row["last_completed_at"],
            "next_scheduled": row["next_scheduled"],
            "has_phone": bool(row["has_phone"]),
            "has_email": bool(row["has_email"]),
            "is_stale": bool(row["is_stale"]),
        })

    for stage in STAGES:
        limit = new_limit if stage == "new" else len(per_stage[stage])
        columns[stage]["items"] = per_stage[stage][:limit]

    return {"columns": columns}
