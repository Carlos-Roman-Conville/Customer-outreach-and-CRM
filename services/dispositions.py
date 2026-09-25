"""
Shared outreach disposition and pipeline status logic for CLI and API.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from db import (
    DB_PATH,
    connect,
    get_default_owner_id,
    init_db,
    insert_status_history,
    insert_touch,
    upsert_deal,
    upsert_discovery,
    utc_now,
)

DISPOSITIONS = {
    "connected",
    "no_answer",
    "gatekeeper",
    "callback",
    "not_interested",
    "dead",
    "voicemail",
}

STATUS_BY_DISPOSITION = {
    "connected": "working",
    "callback": "working",
    "not_interested": "dead",
    "dead": "dead",
    "no_answer": "working",
    "gatekeeper": "working",
    "voicemail": "working",
}


def update_target_status(
    conn,
    business_id: str,
    new_status: str,
    do_not_contact: int = 0,
    changed_by: int | None = None,
) -> str | None:
    row = conn.execute(
        "SELECT status FROM targets WHERE business_id = ?",
        (business_id,),
    ).fetchone()
    if not row:
        return None
    old_status = row["status"]
    now = utc_now()
    conn.execute(
        """
        UPDATE targets
        SET status = ?, do_not_contact = ?, updated_at = ?
        WHERE business_id = ?
        """,
        (new_status, do_not_contact, now, business_id),
    )
    if old_status != new_status:
        insert_status_history(conn, business_id, old_status, new_status, changed_by)
        if new_status in {"meeting", "won", "working", "dead", "new"}:
            upsert_deal(conn, business_id, new_status, owner_id=changed_by)
    return old_status


def record_disposition(
    business_id: str,
    disposition: str,
    notes: str = "",
    callback_days: int = 2,
    callback_date: str | None = None,
    discovery: dict | None = None,
    changed_by: int | None = None,
    db_path=DB_PATH,
) -> dict:
    disposition = disposition.lower().strip()
    if disposition not in DISPOSITIONS:
        raise ValueError(f"Invalid disposition. Choose from: {', '.join(sorted(DISPOSITIONS))}")

    init_db(db_path)
    if changed_by is None:
        changed_by = get_default_owner_id(db_path)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    result = {"touch_id": None, "callback_touch_id": None, "business_name": None}

    with connect(db_path) as conn:
        business = conn.execute(
            "SELECT gers_id, name FROM businesses WHERE gers_id = ?",
            (business_id,),
        ).fetchone()
        if not business:
            raise ValueError(f"Unknown business_id: {business_id}")

        result["business_name"] = business["name"]
        touch_id = insert_touch(conn, {
            "business_id": business_id,
            "channel": "call",
            "step": 1,
            "completed_at": now,
            "disposition": disposition,
            "notes": notes or None,
        })
        result["touch_id"] = touch_id

        new_status = STATUS_BY_DISPOSITION.get(disposition, "working")
        do_not_contact = 1 if disposition in {"not_interested", "dead"} else 0
        update_target_status(
            conn, business_id, new_status, do_not_contact, changed_by=changed_by
        )

        if discovery:
            upsert_discovery(conn, business_id, discovery, user_id=changed_by)

        if disposition == "callback":
            cb_date = callback_date or (date.today() + timedelta(days=callback_days)).isoformat()
            cb_id = insert_touch(conn, {
                "business_id": business_id,
                "channel": "call",
                "step": 2,
                "scheduled_for": cb_date,
                "disposition": "callback",
                "notes": notes or "Scheduled callback",
            })
            result["callback_touch_id"] = cb_id
            result["callback_date"] = cb_date

    return result


def patch_lead_status(
    business_id: str,
    new_status: str,
    changed_by: int | None = None,
    db_path=DB_PATH,
) -> None:
    allowed = {"new", "working", "meeting", "won", "dead"}
    if new_status not in allowed:
        raise ValueError(f"Invalid status: {new_status}")
    init_db(db_path)
    if changed_by is None:
        changed_by = get_default_owner_id(db_path)
    do_not_contact = 1 if new_status == "dead" else 0
    with connect(db_path) as conn:
        if not conn.execute(
            "SELECT 1 FROM targets WHERE business_id = ?",
            (business_id,),
        ).fetchone():
            raise ValueError(f"Unknown business_id: {business_id}")
        update_target_status(
            conn, business_id, new_status, do_not_contact, changed_by=changed_by
        )


def undo_last_disposition(business_id: str, db_path=DB_PATH) -> bool:
    """Remove the most recent completed call touch for a business."""
    init_db(db_path)
    with connect(db_path) as conn:
        touch = conn.execute(
            """
            SELECT id FROM touches
            WHERE business_id = ? AND channel = 'call' AND completed_at IS NOT NULL
            ORDER BY completed_at DESC, id DESC LIMIT 1
            """,
            (business_id,),
        ).fetchone()
        if not touch:
            return False
        conn.execute("DELETE FROM touches WHERE id = ?", (touch["id"],))
        prev = conn.execute(
            """
            SELECT to_status FROM status_history
            WHERE business_id = ?
            ORDER BY changed_at DESC, id DESC LIMIT 1
            """,
            (business_id,),
        ).fetchone()
        if prev:
            conn.execute(
                "DELETE FROM status_history WHERE id = ("
                "SELECT id FROM status_history WHERE business_id = ? "
                "ORDER BY changed_at DESC, id DESC LIMIT 1)",
                (business_id,),
            )
            restore = conn.execute(
                """
                SELECT to_status FROM status_history
                WHERE business_id = ?
                ORDER BY changed_at DESC, id DESC LIMIT 1
                """,
                (business_id,),
            ).fetchone()
            status = restore["to_status"] if restore else "new"
        else:
            status = "new"
        conn.execute(
            "UPDATE targets SET status = ?, do_not_contact = 0, updated_at = ? WHERE business_id = ?",
            (status, utc_now(), business_id),
        )
    return True
