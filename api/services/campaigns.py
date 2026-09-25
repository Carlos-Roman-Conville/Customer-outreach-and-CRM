"""Campaign batch endpoints."""
from __future__ import annotations

from category_tiers import QUEUE_ELIGIBLE_WHERE, QUEUE_TIER_ORDER
from config import CALL_QUEUE_MIN_SCORE, SENDABLE_VERIFY_STATUSES
from db import connect
from api.demo import scrub_email, scrub_name

SENDABLE = ", ".join("?" * len(SENDABLE_VERIFY_STATUSES))


def list_campaigns() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                t.batch_id,
                COUNT(*) AS total,
                SUM(CASE WHEN EXISTS (
                    SELECT 1 FROM contacts c
                    WHERE c.business_id = t.business_id AND c.kind = 'email'
                      AND c.verify_status IN ({SENDABLE})
                ) THEN 1 ELSE 0 END) AS sendable
            FROM targets t
            WHERE t.batch_id IS NOT NULL
              AND t.unsubscribed_at IS NULL
              AND {QUEUE_ELIGIBLE_WHERE}
              AND t.icp_score >= ?
            GROUP BY t.batch_id
            ORDER BY t.batch_id
            """,
            (*SENDABLE_VERIFY_STATUSES, CALL_QUEUE_MIN_SCORE),
        ).fetchall()
    return [dict(r) for r in rows]


def campaign_detail(batch_id: str) -> dict:
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                b.gers_id AS business_id,
                b.name,
                t.icp_score,
                t.status,
                (
                    SELECT c.value FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'email' LIMIT 1
                ) AS email,
                (
                    SELECT c.verify_status FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'email' LIMIT 1
                ) AS verify_status,
                (
                    SELECT MAX(step) FROM touches
                    WHERE business_id = b.gers_id AND channel = 'email' AND completed_at IS NOT NULL
                ) AS email_step_done,
                (
                    SELECT scheduled_for FROM touches
                    WHERE business_id = b.gers_id AND channel = 'email'
                      AND completed_at IS NULL
                    ORDER BY step LIMIT 1
                ) AS next_email,
                (
                    SELECT scheduled_for FROM touches
                    WHERE business_id = b.gers_id AND channel = 'call'
                      AND completed_at IS NULL
                    ORDER BY step LIMIT 1
                ) AS next_call
            FROM targets t
            JOIN businesses b ON b.gers_id = t.business_id
            WHERE t.batch_id = ?
              AND t.unsubscribed_at IS NULL
              AND {QUEUE_ELIGIBLE_WHERE}
            ORDER BY {QUEUE_TIER_ORDER}, t.icp_score DESC
            """,
            (batch_id,),
        ).fetchall()

    items = []
    for r in rows:
        d = dict(r)
        bid = d["business_id"]
        d["name"] = scrub_name(d["name"], bid)
        d["email"] = scrub_email(d.get("email"), bid)
        items.append(d)
    return {"batch_id": batch_id, "items": items, "total": len(items)}
