"""Dashboard statistics."""
from __future__ import annotations

from datetime import date, timedelta

from api.demo import demo_stats_overlay
from config import CALL_QUEUE_MIN_SCORE, DEMO_STATS
from db import connect


def _week_start() -> str:
    today = date.today()
    start = today - timedelta(days=today.weekday())
    return start.isoformat()


def get_stats() -> dict:
    week_start = _week_start()
    with connect() as conn:
        contactable = conn.execute(
            """
            SELECT COUNT(*) FROM targets t
            WHERE t.segment != 'excluded'
              AND t.icp_score >= ?
              AND t.do_not_contact = 0
              AND EXISTS (
                  SELECT 1 FROM contacts c
                  WHERE c.business_id = t.business_id AND c.kind = 'phone'
              )
            """,
            (CALL_QUEUE_MIN_SCORE,),
        ).fetchone()[0]

        contacted_week = conn.execute(
            """
            SELECT COUNT(DISTINCT business_id) FROM touches
            WHERE channel = 'call' AND completed_at IS NOT NULL
              AND date(completed_at) >= date(?)
            """,
            (week_start,),
        ).fetchone()[0]

        meetings = conn.execute(
            "SELECT COUNT(*) FROM targets WHERE status = 'meeting'"
        ).fetchone()[0]

        won = conn.execute(
            "SELECT COUNT(*) FROM targets WHERE status = 'won'"
        ).fetchone()[0]

        working = conn.execute(
            "SELECT COUNT(*) FROM targets WHERE status = 'working'"
        ).fetchone()[0]

        pipeline_value = conn.execute(
            """
            SELECT COALESCE(SUM(value * probability), 0)
            FROM deals WHERE stage NOT IN ('won', 'dead')
            """
        ).fetchone()[0]

        total_deals = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        win_rate = (won / total_deals * 100) if total_deals else 0.0

        activity = conn.execute(
            """
            SELECT date(completed_at) AS day, COUNT(*) AS count
            FROM touches
            WHERE completed_at IS NOT NULL
              AND date(completed_at) >= date(?, '-30 days')
            GROUP BY date(completed_at)
            ORDER BY day
            """,
            (date.today().isoformat(),),
        ).fetchall()

        emails_total = conn.execute(
            "SELECT COUNT(*) FROM contacts WHERE kind = 'email'"
        ).fetchone()[0]
        emails_verified = conn.execute(
            """
            SELECT COUNT(*) FROM contacts
            WHERE kind = 'email' AND verify_status IS NOT NULL AND verify_status != 'pending'
            """
        ).fetchone()[0]
        emails_sendable = conn.execute(
            """
            SELECT COUNT(*) FROM contacts
            WHERE kind = 'email' AND verify_status IN ('valid', 'role_ok', 'deliverable')
            """
        ).fetchone()[0]

        total_leads = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]

    stats = {
        "total_leads": int(total_leads),
        "contactable_leads": int(contactable),
        "contacted_this_week": int(contacted_week),
        "meetings": int(meetings),
        "won": int(won),
        "working": int(working),
        "win_rate": round(win_rate, 1),
        "pipeline_value": round(float(pipeline_value or 0), 2),
        "emails_total": int(emails_total),
        "emails_verified": int(emails_verified),
        "emails_sendable": int(emails_sendable),
        "activity": [{"day": r["day"], "count": r["count"]} for r in activity],
    }
    if DEMO_STATS:
        stats = demo_stats_overlay(stats)
    return stats
