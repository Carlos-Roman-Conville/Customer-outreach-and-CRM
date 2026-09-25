"""
Campaign scheduling: email Monday, call Wednesday, follow-up email.
"""
from __future__ import annotations

from datetime import date, timedelta

from category_tiers import QUEUE_ELIGIBLE_WHERE
from config import CALL_QUEUE_MIN_SCORE, SENDABLE_VERIFY_STATUSES
from db import DB_PATH, connect, init_db, insert_touch, utc_now

CAMPAIGN_TARGET_WHERE = f"""
    t.do_not_contact = 0
    AND t.status NOT IN ('won', 'dead')
    AND t.unsubscribed_at IS NULL
    AND {QUEUE_ELIGIBLE_WHERE}
    AND t.icp_score >= ?
"""


def _sendable_status_sql(alias: str = "c") -> str:
    placeholders = ", ".join("?" * len(SENDABLE_VERIFY_STATUSES))
    return f"{alias}.verify_status IN ({placeholders})"


def _next_weekday(start: date, weekday: int) -> date:
    """Return next occurrence of weekday (Mon=0)."""
    days_ahead = (weekday - start.weekday()) % 7
    if days_ahead == 0:
        return start
    return start + timedelta(days=days_ahead)


def _prune_ineligible_targets(conn) -> int:
    """Remove batch assignments from excluded / low-score targets."""
    cur = conn.execute(
        f"""
        UPDATE targets
        SET batch_id = NULL, updated_at = ?
        WHERE batch_id IS NOT NULL
          AND (segment = 'excluded' OR icp_score < ?)
        """,
        (utc_now(), CALL_QUEUE_MIN_SCORE),
    )
    return int(cur.rowcount)


def assign_batches(
    db_path=DB_PATH,
    batch_size: int = 200,
    start_batch: int = 1,
) -> dict[str, int]:
    print("=" * 60)
    print("CAMPAIGN: Assign weekly batches")
    print("=" * 60)

    init_db(db_path)
    stats = {"batches": 0, "assigned": 0, "pruned": 0}

    with connect(db_path) as conn:
        stats["pruned"] = _prune_ineligible_targets(conn)
        rows = conn.execute(
            f"""
            SELECT t.business_id, t.icp_score
            FROM targets t
            WHERE {CAMPAIGN_TARGET_WHERE}
              AND t.batch_id IS NULL
              AND EXISTS (
                  SELECT 1 FROM contacts c
                  WHERE c.business_id = t.business_id AND c.kind = 'phone'
              )
            ORDER BY t.icp_score DESC
            """,
            (CALL_QUEUE_MIN_SCORE,),
        ).fetchall()

        batch_num = start_batch
        while batch_num <= start_batch + 10000:
            batch_id = f"batch_{batch_num:03d}"
            existing = conn.execute(
                "SELECT 1 FROM targets WHERE batch_id = ? LIMIT 1",
                (batch_id,),
            ).fetchone()
            if not existing:
                break
            batch_num += 1

        for idx in range(0, len(rows), batch_size):
            chunk = rows[idx: idx + batch_size]
            batch_id = f"batch_{batch_num:03d}"
            for row in chunk:
                conn.execute(
                    """
                    UPDATE targets
                    SET batch_id = ?, updated_at = ?
                    WHERE business_id = ?
                    """,
                    (batch_id, utc_now(), row["business_id"]),
                )
                stats["assigned"] += 1
            stats["batches"] += 1
            batch_num += 1

    print(f"  Pruned ineligible from batches: {stats['pruned']:,}")
    print(f"  Batches created: {stats['batches']:,}")
    print(f"  Targets assigned: {stats['assigned']:,}")
    return stats


def schedule_cadence(
    db_path=DB_PATH,
    batch_id: str | None = None,
    week_start: date | None = None,
) -> dict[str, int]:
    """
    Schedule touches for a batch:
      - Monday: initial email (verified addresses only)
      - Wednesday: call
      - Friday: follow-up email (verified addresses only)
    """
    print("=" * 60)
    print("CAMPAIGN: Schedule cadence touches")
    print("=" * 60)

    init_db(db_path)
    week_start = week_start or date.today()
    monday = _next_weekday(week_start, 0)
    wednesday = monday + timedelta(days=2)
    friday = monday + timedelta(days=4)

    stats = {"scheduled": 0, "skipped_existing": 0, "skipped_ineligible": 0}
    sendable_sql = _sendable_status_sql("c")

    with connect(db_path) as conn:
        stats["skipped_ineligible"] = _prune_ineligible_targets(conn)

        if batch_id:
            targets = conn.execute(
                f"""
                SELECT business_id FROM targets t
                WHERE t.batch_id = ? AND {CAMPAIGN_TARGET_WHERE}
                """,
                (batch_id, CALL_QUEUE_MIN_SCORE),
            ).fetchall()
        else:
            targets = conn.execute(
                f"""
                SELECT business_id FROM targets t
                WHERE t.batch_id IS NOT NULL AND {CAMPAIGN_TARGET_WHERE}
                ORDER BY t.batch_id
                """,
                (CALL_QUEUE_MIN_SCORE,),
            ).fetchall()

        for row in targets:
            business_id = row["business_id"]
            existing = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM touches
                WHERE business_id = ? AND scheduled_for IS NOT NULL
                """,
                (business_id,),
            ).fetchone()["cnt"]
            if existing:
                stats["skipped_existing"] += 1
                continue

            has_verified_email = conn.execute(
                f"""
                SELECT 1 FROM contacts c
                WHERE c.business_id = ? AND c.kind = 'email'
                  AND {sendable_sql}
                LIMIT 1
                """,
                (business_id, *SENDABLE_VERIFY_STATUSES),
            ).fetchone()

            if has_verified_email:
                insert_touch(conn, {
                    "business_id": business_id,
                    "channel": "email",
                    "step": 1,
                    "scheduled_for": monday.isoformat(),
                    "notes": "Initial cold email",
                })

            insert_touch(conn, {
                "business_id": business_id,
                "channel": "call",
                "step": 1,
                "scheduled_for": wednesday.isoformat(),
                "notes": "Call 2-3 days after email",
            })

            if has_verified_email:
                insert_touch(conn, {
                    "business_id": business_id,
                    "channel": "email",
                    "step": 2,
                    "scheduled_for": friday.isoformat(),
                    "notes": "Follow-up email after call attempt",
                })

            stats["scheduled"] += 1

    print(f"  Pruned ineligible from batches: {stats['skipped_ineligible']:,}")
    print(f"  Targets scheduled: {stats['scheduled']:,}")
    print(f"  Skipped (already scheduled): {stats['skipped_existing']:,}")
    print(f"  Week: email {monday}, call {wednesday}, follow-up {friday}")
    return stats


if __name__ == "__main__":
    assign_batches()
    schedule_cadence()
