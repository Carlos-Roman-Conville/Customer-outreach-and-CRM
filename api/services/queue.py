"""Call queue queries."""
from __future__ import annotations

from datetime import date

from category_tiers import QUEUE_ELIGIBLE_WHERE, QUEUE_ORDER_BY
from config import CALL_QUEUE_MIN_SCORE
from db import connect
from api.demo import scrub_address, scrub_email, scrub_name, scrub_phone, scrub_website


def _today() -> str:
    return date.today().isoformat()


def _normalize_categories(categories: list[str] | None) -> list[str]:
    if not categories:
        return []
    return [c for c in categories if c and c.strip()]


def fetch_queue(
    limit: int = 40,
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
    categories: list[str] | None = None,
    county: str | None = None,
) -> list[dict]:
    bbox_clause = ""
    category_clause = ""
    county_clause = ""
    cats = _normalize_categories(categories)

    params: list = [CALL_QUEUE_MIN_SCORE]

    if cats:
        placeholders = ",".join("?" * len(cats))
        category_clause = f" AND b.category IN ({placeholders})"
        params.extend(cats)

    if county:
        county_clause = " AND b.county = ?"
        params.append(county)

    if all(v is not None for v in (west, south, east, north)):
        bbox_clause = " AND b.lat BETWEEN ? AND ? AND b.lng BETWEEN ? AND ?"
        params.extend([south, north, west, east])

    params.append(_today())
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                t.business_id,
                t.segment,
                t.icp_score,
                t.revenue_tier,
                t.category_path,
                t.status,
                b.name,
                b.category,
                b.city,
                b.county,
                b.address,
                b.website,
                b.booking_platform,
                b.site_scanned_at,
                b.rating,
                b.review_count,
                b.lat,
                b.lng,
                d.after_hours AS discovery_after_hours,
                d.current_tool AS discovery_current_tool,
                d.hiring_front_desk AS discovery_hiring_front_desk,
                d.missed_calls AS discovery_missed_calls,
                d.answering_spend AS discovery_answering_spend,
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
            LEFT JOIN discovery d ON d.business_id = b.gers_id
            WHERE t.do_not_contact = 0
              AND t.status NOT IN ('won', 'dead')
              AND {QUEUE_ELIGIBLE_WHERE}
              AND t.icp_score >= ?
              AND EXISTS (
                  SELECT 1 FROM contacts c
                  WHERE c.business_id = b.gers_id AND c.kind = 'phone'
              )
              {category_clause}
              {county_clause}
              {bbox_clause}
            ORDER BY
                CASE WHEN callback_due IS NOT NULL AND callback_due <= ? THEN 0 ELSE 1 END,
                {QUEUE_ORDER_BY}
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
            "revenue_tier": row["revenue_tier"],
            "category_path": row["category_path"],
            "status": row["status"],
            "name": scrub_name(row["name"], bid),
            "category": row["category"],
            "city": row["city"],
            "county": row["county"],
            "address": scrub_address(row["address"], bid),
            "website": scrub_website(row["website"], bid),
            "booking_platform": row["booking_platform"],
            "site_scanned_at": row["site_scanned_at"],
            "rating": row["rating"],
            "review_count": row["review_count"],
            "lat": row["lat"],
            "lng": row["lng"],
            "phone": scrub_phone(row["phone"], bid),
            "email": scrub_email(row["email"], bid),
            "last_notes": row["last_notes"],
            "last_disposition": row["last_disposition"],
            "callback_due": row["callback_due"],
            "discovery": {
                "after_hours": row["discovery_after_hours"],
                "current_tool": row["discovery_current_tool"],
                "hiring_front_desk": row["discovery_hiring_front_desk"],
                "missed_calls": row["discovery_missed_calls"],
                "answering_spend": row["discovery_answering_spend"],
            } if row["discovery_after_hours"] or row["discovery_current_tool"] is not None
               or row["discovery_hiring_front_desk"] is not None or row["discovery_missed_calls"]
               or row["discovery_answering_spend"] is not None else None,
        })
    return out
