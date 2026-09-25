from fastapi import APIRouter

from category_tiers import QUEUE_ELIGIBLE_WHERE
from config import CALL_QUEUE_MIN_SCORE
from db import connect

router = APIRouter()


@router.get("/analytics/icp-deciles")
def icp_deciles():
    with connect() as conn:
        rows = conn.execute(
            f"""
            WITH scored AS (
                SELECT t.icp_score,
                       CASE WHEN t.status = 'won' THEN 1 ELSE 0 END AS won
                FROM targets t
                WHERE {QUEUE_ELIGIBLE_WHERE} AND t.icp_score >= ?
            ),
            bucketed AS (
                SELECT
                    CAST((icp_score - ?) / 10 AS INTEGER) AS decile_bucket,
                    COUNT(*) AS total,
                    SUM(won) AS wins
                FROM scored
                GROUP BY decile_bucket
            )
            SELECT decile_bucket, total, wins,
                   ROUND(100.0 * wins / NULLIF(total, 0), 2) AS win_rate
            FROM bucketed
            ORDER BY decile_bucket DESC
            LIMIT 12
            """,
            (CALL_QUEUE_MIN_SCORE, CALL_QUEUE_MIN_SCORE),
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/analytics/connect-by-hour")
def connect_by_hour():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT CAST(strftime('%H', completed_at) AS INTEGER) AS hour,
                   COUNT(*) AS total,
                   SUM(CASE WHEN disposition = 'connected' THEN 1 ELSE 0 END) AS connected
            FROM touches
            WHERE channel = 'call' AND completed_at IS NOT NULL
            GROUP BY hour
            ORDER BY hour
            """
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/analytics/segment-funnel")
def segment_funnel():
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT segment,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status = 'working' THEN 1 ELSE 0 END) AS working,
                   SUM(CASE WHEN status = 'meeting' THEN 1 ELSE 0 END) AS meeting,
                   SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) AS won
            FROM targets t
            WHERE {QUEUE_ELIGIBLE_WHERE}
            GROUP BY segment
            ORDER BY total DESC
            """
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/analytics/discovery")
def discovery_analytics():
    with connect() as conn:
        after_hours = conn.execute(
            """
            SELECT after_hours AS key, COUNT(*) AS count
            FROM discovery
            WHERE after_hours IS NOT NULL
            GROUP BY after_hours
            ORDER BY count DESC
            """
        ).fetchall()
        missed_calls = conn.execute(
            """
            SELECT missed_calls AS key, COUNT(*) AS count
            FROM discovery
            WHERE missed_calls IS NOT NULL
            GROUP BY missed_calls
            ORDER BY count DESC
            """
        ).fetchall()
        hiring = conn.execute(
            """
            SELECT hiring_front_desk AS key, COUNT(*) AS count
            FROM discovery
            WHERE hiring_front_desk IS NOT NULL
            GROUP BY hiring_front_desk
            ORDER BY count DESC
            """
        ).fetchall()
        avg_spend = conn.execute(
            "SELECT AVG(answering_spend) AS avg FROM discovery WHERE answering_spend IS NOT NULL"
        ).fetchone()["avg"]
        booking_platforms = conn.execute(
            """
            SELECT booking_platform AS key, COUNT(*) AS count
            FROM businesses
            WHERE booking_platform IS NOT NULL
            GROUP BY booking_platform
            ORDER BY count DESC
            LIMIT 15
            """
        ).fetchall()
        discovery_total = conn.execute("SELECT COUNT(*) FROM discovery").fetchone()[0]

    return {
        "discovery_total": int(discovery_total),
        "after_hours": [dict(r) for r in after_hours],
        "missed_calls": [dict(r) for r in missed_calls],
        "hiring_front_desk": [dict(r) for r in hiring],
        "avg_answering_spend": round(float(avg_spend), 2) if avg_spend is not None else None,
        "booking_platforms": [dict(r) for r in booking_platforms],
    }
