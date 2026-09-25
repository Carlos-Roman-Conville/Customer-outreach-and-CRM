"""
ICP scoring and target selection for call-led outreach.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone

from category_tiers import classify_business
from config import (
    CALL_QUEUE_MIN_SCORE,
    ICP_PENALTIES,
    ICP_SCORE_VERSION,
    ICP_WEIGHTS,
    KNOWN_BOOKING_VENDORS,
    SENDABLE_VERIFY_STATUSES,
    SOLO_OPERATOR_CATEGORIES,
)
from db import DB_PATH, connect, init_db, utc_now


def normalize_name(name: str) -> str:
    text = (name or "").upper()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _booking_tier(platform: str | None) -> str:
    if not platform:
        return "none"
    if platform in KNOWN_BOOKING_VENDORS:
        return "known"
    return "generic"


def _business_age_years(creation_date: str | None) -> float | None:
    if not creation_date or creation_date <= "1900-01-01":
        return None
    try:
        created = datetime.fromisoformat(creation_date.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return round((now - created).days / 365.25, 1)
    except (TypeError, ValueError):
        return None


def _data_coverage(row) -> float:
    checks = (
        row["places_fetched_at"],
        row["site_scanned_at"],
        row["registration_checked_at"],
    )
    return round(sum(1 for value in checks if value) / 3.0 * 100.0, 1)


def _location_points(name_frequency: int) -> tuple[str, int]:
    if name_frequency <= 2:
        return "independent", ICP_WEIGHTS["independent"]
    if name_frequency <= 6:
        return "multi_indie", ICP_WEIGHTS["multi_location_indie"]
    if name_frequency <= 14:
        return "mid_chain", ICP_PENALTIES["chain_mid"]
    return "chain", ICP_PENALTIES["chain_hard"]


def score_business(
    row,
    has_verified_email: bool,
    name_frequency: int,
) -> tuple[str, str, int, str, str, float, str, int]:
    """
    Return (segment, revenue_tier, icp_score, category_path, classification_source,
            data_coverage, score_breakdown_json, score_version).
    """
    revenue_tier, segment, category_path, classification_source = classify_business(
        row["taxonomy"],
        row["category"],
    )

    if revenue_tier == "X":
        breakdown = json.dumps(
            {
                "version": ICP_SCORE_VERSION,
                "excluded": True,
                "raw_total": -100,
                "clamped_score": -100,
                "data_coverage": 0.0,
            }
        )
        return segment, revenue_tier, -100, category_path, classification_source, 0.0, breakdown, ICP_SCORE_VERSION

    tier_pts = ICP_WEIGHTS["revenue_tier"][revenue_tier]
    license_pts = ICP_WEIGHTS["has_license"] if row["has_active_license"] else 0
    email_pts = ICP_WEIGHTS["has_email"] if has_verified_email else 0
    website_pts = ICP_WEIGHTS["has_website"] if row["website"] else 0

    location_type, location_pts = _location_points(name_frequency)

    solo_penalty = 0
    if category_path and any(
        category_path.startswith(cat) for cat in SOLO_OPERATOR_CATEGORIES
    ):
        solo_penalty = ICP_PENALTIES["solo_operator"]

    raw_total = tier_pts + license_pts + email_pts + website_pts + location_pts + solo_penalty
    icp_score = max(0, raw_total)
    coverage = _data_coverage(row)

    booking_platform = row["booking_platform"]
    breakdown = {
        "version": ICP_SCORE_VERSION,
        "tier": tier_pts,
        "license": license_pts,
        "license_known": bool(row["registration_checked_at"]),
        "email": email_pts,
        "website": website_pts,
        "location_type": location_type,
        "location_pts": location_pts,
        "penalties": {
            "solo_operator": solo_penalty,
            "chain": location_pts if location_pts < 0 else 0,
        },
        "raw_total": raw_total,
        "clamped_score": icp_score,
        "data_coverage": coverage,
        "tiebreaker_data": {
            "review_count": row["review_count"],
            "booking_vendor": booking_platform,
            "booking_tier": _booking_tier(booking_platform),
            "business_age_years": _business_age_years(row["business_creation_date"]),
        },
    }

    return (
        segment,
        revenue_tier,
        icp_score,
        category_path,
        classification_source,
        coverage,
        json.dumps(breakdown),
        ICP_SCORE_VERSION,
    )


def score_targets(db_path=DB_PATH) -> dict[str, int]:
    print("=" * 60)
    print("SCORE: ICP ranking")
    print("=" * 60)

    init_db(db_path)
    now = utc_now()
    sendable = ", ".join("?" * len(SENDABLE_VERIFY_STATUSES))

    with connect(db_path) as conn:
        names = [row["name"] for row in conn.execute("SELECT name FROM businesses").fetchall()]
        name_freq = Counter(normalize_name(n) for n in names if n)

        businesses = conn.execute(
            f"""
            SELECT b.*,
                   EXISTS (
                       SELECT 1 FROM contacts c
                       WHERE c.business_id = b.gers_id AND c.kind = 'phone'
                   ) AS has_phone,
                   EXISTS (
                       SELECT 1 FROM contacts c
                       WHERE c.business_id = b.gers_id AND c.kind = 'email'
                         AND c.verify_status IN ({sendable})
                   ) AS has_verified_email
            FROM businesses b
            """,
            SENDABLE_VERIFY_STATUSES,
        ).fetchall()

        freq_updates = [
            (name_freq.get(normalize_name(row["name"]), 1), row["gers_id"])
            for row in businesses
        ]
        conn.executemany(
            "UPDATE businesses SET name_frequency = ? WHERE gers_id = ?",
            freq_updates,
        )

        target_rows = []
        call_eligible = 0
        tier_counts: Counter[str] = Counter()
        for row in businesses:
            freq = name_freq.get(normalize_name(row["name"]), 1)
            (
                segment,
                revenue_tier,
                icp_score,
                category_path,
                classification_source,
                data_coverage,
                score_breakdown,
                score_version,
            ) = score_business(
                row,
                has_verified_email=bool(row["has_verified_email"]),
                name_frequency=freq,
            )
            tier_counts[revenue_tier] += 1
            target_rows.append(
                (
                    row["gers_id"],
                    segment,
                    icp_score,
                    revenue_tier,
                    category_path,
                    classification_source,
                    "new",
                    0,
                    data_coverage,
                    score_breakdown,
                    score_version,
                    now,
                    now,
                )
            )
            if (
                row["has_phone"]
                and revenue_tier in ("A", "B", "C", "U")
                and icp_score >= CALL_QUEUE_MIN_SCORE
            ):
                call_eligible += 1

        conn.executemany(
            """
            INSERT INTO targets (
                business_id, segment, icp_score, revenue_tier, category_path,
                classification_source, status, do_not_contact,
                data_coverage, score_breakdown, score_version,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(business_id) DO UPDATE SET
                segment = excluded.segment,
                icp_score = excluded.icp_score,
                revenue_tier = excluded.revenue_tier,
                category_path = excluded.category_path,
                classification_source = excluded.classification_source,
                data_coverage = excluded.data_coverage,
                score_breakdown = excluded.score_breakdown,
                score_version = excluded.score_version,
                status = CASE
                    WHEN targets.status IN ('won', 'dead') THEN targets.status
                    ELSE excluded.status
                END,
                updated_at = excluded.updated_at
            """,
            target_rows,
        )

    stats = {
        "targets": len(target_rows),
        "call_eligible": call_eligible,
        "top_2000": min(2000, len(target_rows)),
        "tier_a": tier_counts.get("A", 0),
        "tier_b": tier_counts.get("B", 0),
        "tier_c": tier_counts.get("C", 0),
        "tier_u": tier_counts.get("U", 0),
        "tier_x": tier_counts.get("X", 0),
    }

    print(f"  Scored {stats['targets']:,} targets")
    print(
        f"  Revenue tiers: A={stats['tier_a']:,} B={stats['tier_b']:,} "
        f"C={stats['tier_c']:,} U={stats['tier_u']:,} X={stats['tier_x']:,}"
    )
    print(
        f"  Call-eligible (phone + tier A/B/C/U + score >= {CALL_QUEUE_MIN_SCORE}): "
        f"{stats['call_eligible']:,}"
    )
    print(f"  Top queue depth available: {stats['top_2000']:,}")
    return stats


if __name__ == "__main__":
    score_targets()
