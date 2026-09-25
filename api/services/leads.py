"""Lead search and detail."""
from __future__ import annotations

from datetime import date, datetime

from category_tiers import QUEUE_ELIGIBLE_WHERE, QUEUE_TIER_ORDER
from config import CALL_QUEUE_MIN_SCORE
from db import connect, upsert_deal, upsert_discovery, utc_now
from api.demo import (
    scrub_address,
    scrub_email,
    scrub_name,
    scrub_phone,
    scrub_signal_detail,
    scrub_website,
)


def _normalize_categories(category: str | list[str] | None) -> list[str]:
    if not category:
        return []
    if isinstance(category, str):
        return [category] if category.strip() else []
    return [c for c in category if c and c.strip()]


def _apply_category_filter(where: list, params: list, category: str | list[str] | None) -> None:
    cats = _normalize_categories(category)
    if not cats:
        return
    if len(cats) == 1:
        where.append("b.category = ?")
        params.append(cats[0])
    else:
        placeholders = ",".join("?" * len(cats))
        where.append(f"b.category IN ({placeholders})")
        params.extend(cats)


def _scrub_lead_row(row, bid: str | None = None) -> dict:
    bid = bid or row["business_id"] if "business_id" in row.keys() else row["gers_id"]
    d = dict(row)
    d["name"] = scrub_name(d.get("name"), bid)
    d["address"] = scrub_address(d.get("address"), bid)
    d["website"] = scrub_website(d.get("website"), bid)
    if "phone" in d:
        d["phone"] = scrub_phone(d.get("phone"), bid)
    if "email" in d:
        d["email"] = scrub_email(d.get("email"), bid)
    return d


def _apply_booking_filter(where: list, params: list, booking: str | None) -> None:
    if not booking:
        return
    if booking == "yes":
        where.append("b.booking_platform IS NOT NULL")
    elif booking == "no":
        where.append("b.site_scanned_at IS NOT NULL AND b.booking_platform IS NULL")
    elif booking == "unknown":
        where.append("b.site_scanned_at IS NULL")


def search_leads(
    q: str | None = None,
    county: str | None = None,
    category: str | list[str] | None = None,
    segment: str | None = None,
    status: str | None = None,
    min_score: float | None = None,
    has_email: bool | None = None,
    has_phone: bool | None = None,
    booking: str | None = None,
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    where = ["1=1"]
    params: list = []

    if q:
        where.append("(b.name LIKE ? OR b.address LIKE ? OR b.city LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    if county:
        where.append("b.county = ?")
        params.append(county)
    _apply_category_filter(where, params, category)
    if segment:
        where.append("t.segment = ?")
        params.append(segment)
    if status:
        where.append("t.status = ?")
        params.append(status)
    if min_score is not None:
        where.append("t.icp_score >= ?")
        params.append(min_score)
    if has_email:
        where.append(
            "EXISTS (SELECT 1 FROM contacts c WHERE c.business_id = b.gers_id AND c.kind = 'email')"
        )
    if has_phone:
        where.append(
            "EXISTS (SELECT 1 FROM contacts c WHERE c.business_id = b.gers_id AND c.kind = 'phone')"
        )
    _apply_booking_filter(where, params, booking)
    if all(v is not None for v in (west, south, east, north)):
        where.append("b.lat BETWEEN ? AND ? AND b.lng BETWEEN ? AND ?")
        params.extend([south, north, west, east])

    where_sql = " AND ".join(where)
    offset = (max(page, 1) - 1) * page_size

    with connect() as conn:
        total = conn.execute(
            f"""
            SELECT COUNT(*) FROM businesses b
            LEFT JOIN targets t ON t.business_id = b.gers_id
            WHERE {where_sql}
            """,
            params,
        ).fetchone()[0]

        rows = conn.execute(
            f"""
            SELECT
                b.gers_id AS business_id,
                b.name,
                b.category,
                b.county,
                b.city,
                b.address,
                b.website,
                b.booking_platform,
                b.site_scanned_at,
                b.lat,
                b.lng,
                t.segment,
                t.icp_score,
                t.revenue_tier,
                t.category_path,
                t.status,
                t.batch_id,
                (
                    SELECT c.value FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'phone' LIMIT 1
                ) AS phone,
                (
                    SELECT c.value FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'email' LIMIT 1
                ) AS email
            FROM businesses b
            LEFT JOIN targets t ON t.business_id = b.gers_id
            WHERE {where_sql}
            ORDER BY
                {QUEUE_TIER_ORDER},
                COALESCE(t.icp_score, 0) DESC,
                b.name
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

    items = [_scrub_lead_row(r) for r in rows]
    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "pages": (int(total) + page_size - 1) // page_size,
    }


def get_lead_detail(business_id: str) -> dict:
    with connect() as conn:
        biz = conn.execute(
            """
            SELECT b.*, t.segment, t.icp_score, t.revenue_tier, t.category_path,
                   t.status, t.batch_id, t.do_not_contact
            FROM businesses b
            LEFT JOIN targets t ON t.business_id = b.gers_id
            WHERE b.gers_id = ?
            """,
            (business_id,),
        ).fetchone()
        if not biz:
            raise ValueError("Lead not found")

        contacts = conn.execute(
            "SELECT * FROM contacts WHERE business_id = ? ORDER BY kind, id",
            (business_id,),
        ).fetchall()

        touches = conn.execute(
            "SELECT * FROM touches WHERE business_id = ? ORDER BY COALESCE(completed_at, scheduled_for) DESC, id DESC",
            (business_id,),
        ).fetchall()

        notes = conn.execute(
            "SELECT n.*, u.name AS user_name FROM notes n LEFT JOIN users u ON u.id = n.user_id "
            "WHERE n.business_id = ? ORDER BY n.created_at DESC",
            (business_id,),
        ).fetchall()

        history = conn.execute(
            "SELECT * FROM status_history WHERE business_id = ? ORDER BY changed_at DESC",
            (business_id,),
        ).fetchall()

        deal = conn.execute(
            "SELECT * FROM deals WHERE business_id = ?",
            (business_id,),
        ).fetchone()

        signals = conn.execute(
            """
            SELECT kind, value, detail, source, detected_at
            FROM business_signals
            WHERE business_id = ?
            ORDER BY kind, value
            """,
            (business_id,),
        ).fetchall()

        discovery = conn.execute(
            "SELECT * FROM discovery WHERE business_id = ?",
            (business_id,),
        ).fetchone()

    scrubbed_contacts = []
    for c in contacts:
        cd = dict(c)
        if cd["kind"] == "email":
            cd["value"] = scrub_email(cd["value"], business_id)
        elif cd["kind"] == "phone":
            cd["value"] = scrub_phone(cd["value"], business_id)
        elif cd["kind"] == "website":
            cd["value"] = scrub_website(cd["value"], business_id)
        scrubbed_contacts.append(cd)

    return {
        "business": _scrub_lead_row(biz, business_id),
        "contacts": scrubbed_contacts,
        "touches": [dict(t) for t in touches],
        "notes": [dict(n) for n in notes],
        "status_history": [dict(h) for h in history],
        "deal": dict(deal) if deal else None,
        "signals": [
            {
                **dict(s),
                "value": scrub_signal_detail(s["value"], business_id),
                "detail": scrub_signal_detail(s["detail"], business_id),
            }
            for s in signals
        ],
        "discovery": dict(discovery) if discovery else None,
    }


def patch_discovery(business_id: str, fields: dict, user_id: int) -> dict:
    with connect() as conn:
        if not conn.execute(
            "SELECT 1 FROM businesses WHERE gers_id = ?",
            (business_id,),
        ).fetchone():
            raise ValueError("Lead not found")
        upsert_discovery(conn, business_id, fields, user_id=user_id)
        row = conn.execute(
            "SELECT * FROM discovery WHERE business_id = ?",
            (business_id,),
        ).fetchone()
    return dict(row) if row else {}


def add_note(business_id: str, body: str, user_id: int) -> dict:
    now = utc_now()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO notes (business_id, user_id, body, created_at) VALUES (?, ?, ?, ?)",
            (business_id, user_id, body, now),
        )
        note_id = int(cur.lastrowid)
    return {"id": note_id, "business_id": business_id, "body": body, "created_at": now}


def update_deal(business_id: str, owner_id: int, **fields) -> dict:
    with connect() as conn:
        deal = conn.execute("SELECT * FROM deals WHERE business_id = ?", (business_id,)).fetchone()
        stage = fields.get("stage") if fields.get("stage") is not None else (deal["stage"] if deal else "new")
        value = fields.get("value") if fields.get("value") is not None else (deal["value"] if deal else None)
        probability = fields.get("probability") if fields.get("probability") is not None else (deal["probability"] if deal else None)
        upsert_deal(conn, business_id, stage, owner_id=owner_id, value=value, probability=probability)
        if fields.get("expected_close"):
            conn.execute(
                "UPDATE deals SET expected_close = ?, updated_at = ? WHERE business_id = ?",
                (fields["expected_close"], utc_now(), business_id),
            )
        if stage:
            conn.execute(
                "UPDATE targets SET status = ?, updated_at = ? WHERE business_id = ?",
                (stage, utc_now(), business_id),
            )
        updated = conn.execute("SELECT * FROM deals WHERE business_id = ?", (business_id,)).fetchone()
    return dict(updated) if updated else {}


def global_search(q: str, limit: int = 20) -> list[dict]:
    like = f"%{q}%"
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT b.gers_id AS business_id, b.name, b.category, b.county,
                   t.icp_score, t.revenue_tier, t.status
            FROM businesses b
            LEFT JOIN targets t ON t.business_id = b.gers_id
            LEFT JOIN contacts c ON c.business_id = b.gers_id
            WHERE b.name LIKE ? OR c.value LIKE ? OR b.address LIKE ?
            ORDER BY COALESCE(t.icp_score, 0) DESC
            LIMIT ?
            """,
            (like, like, like, limit),
        ).fetchall()
    return [_scrub_lead_row(r) for r in rows]


METRO_COUNTIES = [
    "Philadelphia",
    "Montgomery",
    "Bucks",
    "Chester",
    "Delaware",
    "Camden",
    "Burlington",
    "Gloucester",
]

# Cadence: open scheduled touch past due, or working/meeting stale 7+ days with no future schedule.
_OVERDUE_EXPR = """(
    (
        SELECT MIN(scheduled_for) FROM touches
        WHERE business_id = b.gers_id
          AND completed_at IS NULL
          AND scheduled_for IS NOT NULL
    ) < date('now')
    OR (
        t.status IN ('working', 'meeting')
        AND (
            SELECT MAX(completed_at) FROM touches
            WHERE business_id = b.gers_id AND completed_at IS NOT NULL
        ) < date('now', '-7 days')
        AND NOT EXISTS (
            SELECT 1 FROM touches
            WHERE business_id = b.gers_id
              AND completed_at IS NULL
              AND scheduled_for IS NOT NULL
              AND scheduled_for >= date('now')
        )
    )
)"""


def _map_filter_clauses(
    *,
    county: str | None,
    status: str | None,
    category: str | list[str] | None,
    batch_id: str | None,
    overdue_only: bool,
) -> tuple[str, list]:
    where: list[str] = []
    params: list = []
    if county:
        where.append("b.county = ?")
        params.append(county)
    if status:
        where.append("t.status = ?")
        params.append(status)
    cats = _normalize_categories(category)
    if cats:
        if len(cats) == 1:
            where.append("b.category = ?")
            params.append(cats[0])
        else:
            placeholders = ",".join("?" * len(cats))
            where.append(f"b.category IN ({placeholders})")
            params.extend(cats)
    if batch_id:
        where.append("t.batch_id = ?")
        params.append(batch_id)
    if overdue_only:
        where.append(_OVERDUE_EXPR)
    clause = (" AND " + " AND ".join(where)) if where else ""
    return clause, params


def county_stats(
    min_score: float = CALL_QUEUE_MIN_SCORE,
    category: str | list[str] | None = None,
    status: str | None = None,
) -> dict:
    """Read-only per-county aggregates for Territory Overview cards/choropleth."""
    extra, extra_params = _map_filter_clauses(
        county=None,
        status=status,
        category=category,
        batch_id=None,
        overdue_only=False,
    )
    placeholders = ",".join("?" * len(METRO_COUNTIES))
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                b.county AS county,
                COUNT(*) AS lead_count,
                AVG(t.icp_score) AS avg_icp,
                SUM(CASE WHEN t.status = 'new' THEN 1 ELSE 0 END) AS untouched_count,
                SUM(CASE WHEN t.status = 'new' AND t.icp_score >= ? THEN 1 ELSE 0 END) AS untouched_high_icp,
                SUM(CASE WHEN {_OVERDUE_EXPR} THEN 1 ELSE 0 END) AS overdue_count,
                SUM(CASE WHEN t.batch_id IS NOT NULL THEN 1 ELSE 0 END) AS in_campaign_count
            FROM businesses b
            JOIN targets t ON t.business_id = b.gers_id
            WHERE b.county IN ({placeholders})
              AND {QUEUE_ELIGIBLE_WHERE}
              AND t.icp_score >= ?
              {extra}
            GROUP BY b.county
            """,
            [min_score, *METRO_COUNTIES, min_score, *extra_params],
        ).fetchall()

    by_name = {r["county"]: dict(r) for r in rows}
    items = []
    for name in METRO_COUNTIES:
        r = by_name.get(name)
        if not r:
            items.append({
                "county": name,
                "lead_count": 0,
                "avg_icp": 0.0,
                "untouched_count": 0,
                "untouched_pct": 0.0,
                "overdue_count": 0,
                "in_campaign_count": 0,
                "opportunity": 0.0,
            })
            continue
        lead_count = int(r["lead_count"] or 0)
        untouched = int(r["untouched_count"] or 0)
        avg_icp = float(r["avg_icp"] or 0)
        untouched_high = int(r["untouched_high_icp"] or 0)
        items.append({
            "county": name,
            "lead_count": lead_count,
            "avg_icp": round(avg_icp, 1),
            "untouched_count": untouched,
            "untouched_pct": round((untouched / lead_count * 100) if lead_count else 0.0, 1),
            "overdue_count": int(r["overdue_count"] or 0),
            "in_campaign_count": int(r["in_campaign_count"] or 0),
            "opportunity": round(untouched_high * avg_icp, 1),
        })
    items.sort(key=lambda x: x["opportunity"], reverse=True)
    return {"items": items}


def map_points(
    west: float,
    south: float,
    east: float,
    north: float,
    limit: int = 5000,
    min_score: float = CALL_QUEUE_MIN_SCORE,
    county: str | None = None,
    status: str | None = None,
    category: str | list[str] | None = None,
    batch_id: str | None = None,
    mode: str = "hunt",
    overdue_only: bool = False,
) -> dict:
    mode = (mode or "hunt").lower()
    if mode not in ("hunt", "cadence", "campaign", "overview"):
        mode = "hunt"

    extra, extra_params = _map_filter_clauses(
        county=county,
        status=status,
        category=category,
        batch_id=batch_id,
        overdue_only=overdue_only and mode == "cadence",
    )

    if mode == "cadence":
        select_extra = f"""
            ,
            (
                SELECT MAX(completed_at) FROM touches
                WHERE business_id = b.gers_id AND completed_at IS NOT NULL
            ) AS last_completed_at,
            (
                SELECT MIN(scheduled_for) FROM touches
                WHERE business_id = b.gers_id
                  AND completed_at IS NULL
                  AND scheduled_for IS NOT NULL
            ) AS next_scheduled_for,
            CASE WHEN {_OVERDUE_EXPR} THEN 1 ELSE 0 END AS overdue,
            t.batch_id AS batch_id
        """
    else:
        select_extra = ", t.batch_id AS batch_id"

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT b.gers_id AS business_id, b.name, b.lat, b.lng,
                   b.category, b.county, t.icp_score, t.revenue_tier, t.status, t.segment
                   {select_extra}
            FROM businesses b
            JOIN targets t ON t.business_id = b.gers_id
            WHERE b.lat BETWEEN ? AND ? AND b.lng BETWEEN ? AND ?
              AND {QUEUE_ELIGIBLE_WHERE}
              AND t.icp_score >= ?
              {extra}
            ORDER BY {QUEUE_TIER_ORDER}, t.icp_score DESC
            LIMIT ?
            """,
            (south, north, west, east, min_score, *extra_params, limit),
        ).fetchall()

    features = []
    for r in rows:
        bid = r["business_id"]
        props = {
            "business_id": bid,
            "name": scrub_name(r["name"], bid),
            "category": r["category"],
            "county": r["county"],
            "icp_score": r["icp_score"],
            "revenue_tier": r["revenue_tier"],
            "status": r["status"],
            "segment": r["segment"],
            "batch_id": r["batch_id"],
        }
        if mode == "cadence":
            last = r["last_completed_at"]
            props["last_completed_at"] = last
            props["next_scheduled_for"] = r["next_scheduled_for"]
            props["overdue"] = bool(r["overdue"])
            if last:
                try:
                    last_d = datetime.fromisoformat(str(last)[:10]).date()
                    props["days_since_touch"] = (date.today() - last_d).days
                except ValueError:
                    props["days_since_touch"] = None
            else:
                props["days_since_touch"] = None
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]},
            "properties": props,
        })
    return {"type": "FeatureCollection", "features": features}
