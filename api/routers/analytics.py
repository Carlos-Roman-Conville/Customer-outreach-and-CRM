from fastapi import APIRouter

from db import connect

router = APIRouter()


@router.get("/analytics/icp-deciles")
def icp_deciles():
    with connect() as conn:
        rows = conn.execute(
            """
            WITH scored AS (
                SELECT t.icp_score,
                       CASE WHEN t.status = 'won' THEN 1 ELSE 0 END AS won
                FROM targets t
                WHERE t.segment != 'excluded' AND t.icp_score >= 25
            ),
            bucketed AS (
                SELECT
                    CAST((icp_score - 25) / 10 AS INTEGER) AS decile_bucket,
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
            """
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
            """
            SELECT segment,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status = 'working' THEN 1 ELSE 0 END) AS working,
                   SUM(CASE WHEN status = 'meeting' THEN 1 ELSE 0 END) AS meeting,
                   SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) AS won
            FROM targets
            WHERE segment != 'excluded'
            GROUP BY segment
            ORDER BY total DESC
            """
        ).fetchall()
    return {"items": [dict(r) for r in rows]}
