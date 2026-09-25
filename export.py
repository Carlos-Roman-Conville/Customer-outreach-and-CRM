"""
Export outreach batches and daily call sheets from SQLite.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from category_tiers import QUEUE_ELIGIBLE_WHERE, QUEUE_TIER_ORDER
from config import CALL_QUEUE_MIN_SCORE, DATA_DIR, SENDABLE_VERIFY_STATUSES
from db import DB_PATH, connect, init_db
from verify import verification_summary

EXPORT_DIR = DATA_DIR / "exports"

CAMPAIGN_TARGET_WHERE = f"""
    t.do_not_contact = 0
    AND {QUEUE_ELIGIBLE_WHERE}
    AND t.icp_score >= ?
"""


def _sendable_status_sql(alias: str = "c") -> str:
    placeholders = ", ".join("?" * len(SENDABLE_VERIFY_STATUSES))
    return f"{alias}.verify_status IN ({placeholders})"


def _require_verification_ready(db_path=DB_PATH) -> None:
    summary = verification_summary(db_path=db_path)
    if summary["unverified"] > 0:
        print(
            f"ERROR: {summary['unverified']:,} of {summary['total']:,} emails are still unverified.\n"
            "Run full verification before exporting email batches:\n"
            "  python pipeline.py verify"
        )
        sys.exit(1)


def export_email_batch(batch_id: str, db_path=DB_PATH) -> Path:
    _require_verification_ready(db_path=db_path)
    init_db(db_path)
    EXPORT_DIR.mkdir(exist_ok=True)

    sendable_sql = _sendable_status_sql("c")

    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                b.name AS business_name,
                b.address,
                b.city,
                b.state,
                b.zip,
                b.county,
                b.category AS business_type,
                b.website,
                (
                    SELECT c.value FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'email'
                      AND {sendable_sql}
                    ORDER BY c.confidence DESC NULLS LAST, c.id
                    LIMIT 1
                ) AS email,
                (
                    SELECT c.verify_status FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'email'
                      AND {sendable_sql}
                    ORDER BY c.confidence DESC NULLS LAST, c.id
                    LIMIT 1
                ) AS verify_status,
                (
                    SELECT c.value FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'phone'
                    ORDER BY c.id LIMIT 1
                ) AS phone,
                t.segment,
                t.icp_score,
                t.revenue_tier,
                t.batch_id
            FROM targets t
            JOIN businesses b ON b.gers_id = t.business_id
            WHERE t.batch_id = ?
              AND {CAMPAIGN_TARGET_WHERE}
            ORDER BY {QUEUE_TIER_ORDER}, t.icp_score DESC, b.name
            """,
            (*SENDABLE_VERIFY_STATUSES, *SENDABLE_VERIFY_STATUSES, batch_id, CALL_QUEUE_MIN_SCORE),
        ).fetchall()

    df = pd.DataFrame([dict(row) for row in rows])
    df = df[df["email"].notna()].copy()
    out_path = EXPORT_DIR / f"email_{batch_id}.csv"
    df.to_csv(out_path, index=False)
    print(f"  Email batch export: {out_path} ({len(df):,} verified rows)")
    return out_path


def export_call_sheet(
    for_date: date | None = None,
    db_path=DB_PATH,
) -> Path:
    init_db(db_path)
    EXPORT_DIR.mkdir(exist_ok=True)
    for_date = for_date or date.today()
    date_str = for_date.isoformat()

    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                b.name AS business_name,
                b.address,
                b.city,
                b.county,
                b.category AS business_type,
                b.website,
                (
                    SELECT c.value FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'phone'
                    ORDER BY c.id LIMIT 1
                ) AS phone,
                (
                    SELECT c.value FROM contacts c
                    WHERE c.business_id = b.gers_id AND c.kind = 'email'
                    ORDER BY c.id LIMIT 1
                ) AS email,
                t.segment,
                t.icp_score,
                t.revenue_tier,
                t.batch_id,
                touch.step,
                touch.notes AS touch_notes
            FROM touches touch
            JOIN businesses b ON b.gers_id = touch.business_id
            JOIN targets t ON t.business_id = touch.business_id
            WHERE touch.channel = 'call'
              AND touch.scheduled_for = ?
              AND touch.completed_at IS NULL
              AND {CAMPAIGN_TARGET_WHERE}
              AND t.status NOT IN ('won', 'dead')
            ORDER BY {QUEUE_TIER_ORDER}, t.icp_score DESC, b.name
            """,
            (date_str, CALL_QUEUE_MIN_SCORE),
        ).fetchall()

    df = pd.DataFrame([dict(row) for row in rows])
    out_path = EXPORT_DIR / f"call_sheet_{date_str}.csv"
    df.to_csv(out_path, index=False)
    print(f"  Call sheet export: {out_path} ({len(df):,} rows)")
    return out_path


def export_active_batches(batch_ids: list[str] | None = None, db_path=DB_PATH) -> list[Path]:
    """
    Export call sheet plus email CSVs for selected batches.
    Email exports require full verification to be complete first.
    """
    print("=" * 60)
    print("EXPORT: Campaign files")
    print("=" * 60)

    init_db(db_path)
    paths: list[Path] = []

    with connect(db_path) as conn:
        if batch_ids is None:
            rows = conn.execute(
                f"""
                SELECT DISTINCT t.batch_id
                FROM targets t
                JOIN touches touch ON touch.business_id = t.business_id
                WHERE t.batch_id IS NOT NULL
                  AND {CAMPAIGN_TARGET_WHERE}
                  AND touch.scheduled_for IS NOT NULL
                  AND touch.completed_at IS NULL
                ORDER BY t.batch_id
                LIMIT 5
                """,
                (CALL_QUEUE_MIN_SCORE,),
            ).fetchall()
            batch_ids = [row["batch_id"] for row in rows]

    for batch_id in batch_ids or []:
        paths.append(export_email_batch(batch_id, db_path=db_path))

    paths.append(export_call_sheet(db_path=db_path))
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Export outreach CSVs")
    parser.add_argument("--batch-id", action="append", help="Batch ID to export (repeatable)")
    args = parser.parse_args()
    export_active_batches(batch_ids=args.batch_id)


if __name__ == "__main__":
    main()
