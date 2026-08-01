from fastapi import APIRouter

from config import CALL_QUEUE_MIN_SCORE
from db import connect
from api.demo import scrub_name

router = APIRouter()


@router.get("/pipeline")
def pipeline_board():
    columns = ["new", "working", "meeting", "won", "dead"]
    result = {col: [] for col in columns}
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.business_id, t.status, t.icp_score, t.segment, b.name,
                   (
                       SELECT MAX(COALESCE(completed_at, scheduled_for))
                       FROM touches WHERE business_id = t.business_id
                   ) AS last_touch
            FROM targets t
            JOIN businesses b ON b.gers_id = t.business_id
            WHERE t.segment != 'excluded'
              AND t.icp_score >= ?
            ORDER BY t.icp_score DESC
            LIMIT 500
            """,
            (CALL_QUEUE_MIN_SCORE,),
        ).fetchall()
    for row in rows:
        status = row["status"] if row["status"] in columns else "new"
        bid = row["business_id"]
        result[status].append({
            "business_id": bid,
            "name": scrub_name(row["name"], bid),
            "icp_score": row["icp_score"],
            "segment": row["segment"],
            "last_touch": row["last_touch"],
        })
    return result
