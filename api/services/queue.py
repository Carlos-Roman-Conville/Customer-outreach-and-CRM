"""Call queue queries."""
from __future__ import annotations

from datetime import date

from config import CALL_QUEUE_MIN_SCORE
from db import connect
from api.demo import scrub_address, scrub_email, scrub_name, scrub_phone, scrub_website


def _today() -> str:
    return date.today().isoformat()


def fetch_queue(
    limit: int = 40,
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
) -> list[dict]:
    bbox_clause = ""
    params: list = [CALL_QUEUE_MIN_SCORE, _today()]
    if all(v is not None for v in (west, south, east, north)):
        bbox_clause = " AND b.lat BETWEEN ? AND ? AND b.lng BETWEEN ? AND ?"
        params.extend([south, north, west, east])
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                t.business_id,
                t.segment,
                t.icp_score,
                t.status,
                b.name,
                b.category,
                b.city,
                b.county,
                b.address,
                b.website,
                b.lat,
                b.lng,
                (
                    SELECT c.value FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'phone'
                    ORDER BY c.confidence DESC NULLS LAST, c.id LIMIT 1
                ) AS phone,
                (
                    SELECT c.value FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'email'
                    ORDER BY c.confidence DESC NULLS LAST, c.id LIMIT 1
                ) AS email,
                (
                    SELECT notes FROM touches
                    WHERE business_id = b.gers_id AND channel = 'call' AND notes IS NOT NULL
                    ORDER BY completed_at DESC NULLS LAST, id DESC LIMIT 1
                ) AS last_notes,
                (
                    SELECT disposition FROM touches
                    WHERE business_id = b.gers_id AND channel = 'call'
                    ORDER BY completed_at DESC NULLS LAST, id DESC LIMIT 1
                ) AS last_disposition,
                (
                    SELECT scheduled_for FROM touches
                    WHERE business_id = b.gers_id AND channel = 'call'
                      AND disposition = 'callback' AND completed_at IS NULL
                    ORDER BY scheduled_for ASC, id DESC LIMIT 1
                ) AS callback_due
            FROM targets t
            JOIN businesses b ON b.gers_id = t.business_id
            WHERE t.do_not_contact = 0
              AND t.status NOT IN ('won', 'dead')
              AND t.segment != 'excluded'
              AND t.icp_score >= ?
              AND EXISTS (
                  SELECT 1 FROM contacts c
                  WHERE c.business_id = b.gers_id AND c.kind = 'phone'
              )
              {bbox_clause}
            ORDER BY
                CASE WHEN callback_due IS NOT NULL AND callback_due <= ? THEN 0 ELSE 1 END,
                t.icp_score DESC,
                b.name ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    out = []
    for row in rows:
        bid = row["business_id"]
        out.append({
            "business_id": bid,
            "segment": row["segment"],
            "icp_score": row["icp_score"],
            "status": row["status"],
            "name": scrub_name(row["name"], bid),
            "category": row["category"],
            "city": row["city"],
            "county": row["county"],
            "address": scrub_address(row["address"], bid),
            "website": scrub_website(row["website"], bid),
            "lat": row["lat"],
            "lng": row["lng"],
            "phone": scrub_phone(row["phone"], bid),
            "email": scrub_email(row["email"], bid),
            "last_notes": row["last_notes"],
            "last_disposition": row["last_disposition"],
            "callback_due": row["callback_due"],
        })
    return out
