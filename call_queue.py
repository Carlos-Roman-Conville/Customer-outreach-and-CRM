"""
Daily call queue CLI with disposition tracking.
"""
from __future__ import annotations

import argparse

from services.dispositions import DISPOSITIONS, record_disposition
from db import DB_PATH, connect, init_db
from config import CALL_QUEUE_MIN_SCORE
from datetime import date


def _today() -> str:
    return date.today().isoformat()


def _fetch_queue(limit: int, db_path=DB_PATH, bbox: tuple | None = None):
    bbox_clause = ""
    params: list = [CALL_QUEUE_MIN_SCORE, _today()]
    if bbox:
        west, south, east, north = bbox
        bbox_clause = " AND b.lat BETWEEN ? AND ? AND b.lng BETWEEN ? AND ?"
        params.extend([south, north, west, east])
    params.append(limit)

    with connect(db_path) as conn:
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
                b.website,
                b.lat,
                b.lng,
                (
                    SELECT c.value FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'phone'
                    ORDER BY c.confidence DESC NULLS LAST, c.id
                    LIMIT 1
                ) AS phone,
                (
                    SELECT c.value FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'email'
                    ORDER BY c.confidence DESC NULLS LAST, c.id
                    LIMIT 1
                ) AS email,
                (
                    SELECT disposition FROM touches
                    WHERE business_id = b.gers_id AND channel = 'call'
                    ORDER BY completed_at DESC NULLS LAST, id DESC
                    LIMIT 1
                ) AS last_disposition,
                (
                    SELECT scheduled_for FROM touches
                    WHERE business_id = b.gers_id
                      AND channel = 'call'
                      AND disposition = 'callback'
                      AND completed_at IS NULL
                    ORDER BY scheduled_for ASC, id DESC
                    LIMIT 1
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
    return rows


def show_queue(limit: int = 40, db_path=DB_PATH) -> None:
    init_db(db_path)
    rows = _fetch_queue(limit, db_path=db_path)

    print("=" * 60)
    print(f"CALL QUEUE ({len(rows)} targets)")
    print("=" * 60)

    if not rows:
        print("  No call targets available. Run: python pipeline.py run-core")
        return

    for idx, row in enumerate(rows, start=1):
        location = ", ".join(part for part in [row["city"], row["county"]] if part)
        prior = row["last_disposition"] or "none"
        print(f"\n[{idx}] {row['name']}")
        print(f"    ID: {row['business_id']}")
        print(f"    Segment: {row['segment']} | Score: {row['icp_score']}")
        print(f"    Phone: {row['phone'] or 'n/a'}")
        print(f"    Prior call: {prior}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily call queue")
    sub = parser.add_subparsers(dest="command", required=True)

    show_parser = sub.add_parser("show", help="Show today's call queue")
    show_parser.add_argument("--limit", type=int, default=40)

    log_parser = sub.add_parser("log", help="Record a call disposition")
    log_parser.add_argument("business_id", help="Overture gers_id")
    log_parser.add_argument("disposition", choices=sorted(DISPOSITIONS))
    log_parser.add_argument("--notes", default="")
    log_parser.add_argument("--callback-days", type=int, default=2)

    args = parser.parse_args()
    if args.command == "show":
        show_queue(limit=args.limit)
    elif args.command == "log":
        result = record_disposition(
            args.business_id,
            args.disposition,
            notes=args.notes,
            callback_days=args.callback_days,
        )
        print(f"Recorded {args.disposition} for {result['business_name']} (touch #{result['touch_id']})")


if __name__ == "__main__":
    main()
