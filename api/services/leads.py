"""Lead search and detail."""
from __future__ import annotations

from config import CALL_QUEUE_MIN_SCORE
from db import connect, upsert_deal, utc_now
from api.demo import scrub_address, scrub_email, scrub_name, scrub_phone, scrub_website


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


def search_leads(
    q: str | None = None,
    county: str | None = None,
    category: str | None = None,
    segment: str | None = None,
    status: str | None = None,
    min_score: float | None = None,
    has_email: bool | None = None,
    has_phone: bool | None = None,
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
    if category:
        where.append("b.category = ?")
        params.append(category)
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
                b.lat,
                b.lng,
                t.segment,
                t.icp_score,
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
            ORDER BY COALESCE(t.icp_score, 0) DESC, b.name
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
            SELECT b.*, t.segment, t.icp_score, t.status, t.batch_id, t.do_not_contact
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
    }


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
                   t.icp_score, t.status
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


def map_points(
    west: float,
    south: float,
    east: float,
    north: float,
    limit: int = 5000,
    min_score: float = CALL_QUEUE_MIN_SCORE,
) -> dict:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT b.gers_id AS business_id, b.name, b.lat, b.lng,
                   b.category, b.county, t.icp_score, t.status, t.segment
            FROM businesses b
            JOIN targets t ON t.business_id = b.gers_id
            WHERE b.lat BETWEEN ? AND ? AND b.lng BETWEEN ? AND ?
              AND t.segment != 'excluded'
              AND t.icp_score >= ?
            ORDER BY t.icp_score DESC
            LIMIT ?
            """,
            (south, north, west, east, min_score, limit),
        ).fetchall()

    features = []
    for r in rows:
        bid = r["business_id"]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["lng"], r["lat"]]},
            "properties": {
                "business_id": bid,
                "name": scrub_name(r["name"], bid),
                "category": r["category"],
                "county": r["county"],
                "icp_score": r["icp_score"],
                "status": r["status"],
                "segment": r["segment"],
            },
        })
    return {"type": "FeatureCollection", "features": features}
