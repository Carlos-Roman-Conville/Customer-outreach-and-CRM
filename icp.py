"""
ICP scoring and target selection for call-led outreach.
"""
from __future__ import annotations

import re
from collections import Counter

from config import CALL_QUEUE_MIN_SCORE
from db import DB_PATH, connect, init_db, utc_now

TIER_1_KEYWORDS = {
    "plumb", "electric", "hvac", "roof", "landscap", "lawn", "tree",
    "pest", "locksmith", "garage_door", "handyman", "cleaning",
    "salon", "barber", "nail", "spa", "beauty", "hair",
    "auto_repair", "mechanic", "tire", "body_shop", "car_wash",
}
TIER_2_KEYWORDS = {
    "dentist", "dental", "chiropract", "veterinar", "vet", "optomet",
    "med_spa", "physical_therapy", "urgent_care",
    "law", "attorney", "account", "cpa", "insurance", "real_estate",
    "mortgage", "financial",
}
TIER_3_KEYWORDS = {
    "gym", "fitness", "yoga", "pilates", "crossfit",
    "restaurant", "cafe", "pizza", "bakery", "cater",
}

EXCLUDE_KEYWORDS = {
    "retirement_home", "hospital", "government", "school", "church",
    "police", "fire_station", "post_office", "library", "university",
}
CHAIN_NAME_THRESHOLD = 8


def normalize_name(name: str) -> str:
    text = (name or "").upper()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def classify_segment(category_text: str) -> tuple[str, int]:
    for keyword in TIER_1_KEYWORDS:
        if keyword in category_text:
            return "tier1_home_personal_auto", 40
    for keyword in TIER_2_KEYWORDS:
        if keyword in category_text:
            return "tier2_health_professional", 30
    for keyword in TIER_3_KEYWORDS:
        if keyword in category_text:
            return "tier3_fitness_food", 20
    return "other", 10


def _category_text(row) -> str:
    parts = [
        row["category"] or "",
        row["basic_category"] or "",
        row["taxonomy"] or "",
        row["name"] or "",
    ]
    return " ".join(parts).lower().replace("-", "_").replace(" ", "_")


def score_business(row, has_phone: bool, has_email: bool, name_frequency: int) -> tuple[str, float]:
    category_text = _category_text(row)
    segment, base = classify_segment(category_text)

    score = float(base)
    confidence = row["confidence"] or 0.0
    score += confidence * 20.0

    if has_phone:
        score += 25.0
    else:
        score -= 50.0

    if row["website"]:
        score += 8.0
    if has_email:
        score += 5.0
    if row["has_active_license"]:
        score += 10.0

    if name_frequency >= CHAIN_NAME_THRESHOLD:
        score -= 15.0
    elif name_frequency <= 2:
        score += 5.0

    if any(keyword in category_text for keyword in EXCLUDE_KEYWORDS):
        return "excluded", -100.0

    return segment, round(score, 2)


def score_targets(db_path=DB_PATH) -> dict[str, int]:
    print("=" * 60)
    print("SCORE: ICP ranking")
    print("=" * 60)

    init_db(db_path)
    now = utc_now()

    with connect(db_path) as conn:
        names = [row["name"] for row in conn.execute("SELECT name FROM businesses").fetchall()]
        name_freq = Counter(normalize_name(n) for n in names if n)

        businesses = conn.execute(
            """
            SELECT b.*,
                   EXISTS (
                       SELECT 1 FROM contacts c
                       WHERE c.business_id = b.gers_id AND c.kind = 'phone'
                   ) AS has_phone,
                   EXISTS (
                       SELECT 1 FROM contacts c
                       WHERE c.business_id = b.gers_id AND c.kind = 'email'
                   ) AS has_email
            FROM businesses b
            """
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
        for row in businesses:
            freq = name_freq.get(normalize_name(row["name"]), 1)
            segment, icp_score = score_business(
                row,
                has_phone=bool(row["has_phone"]),
                has_email=bool(row["has_email"]),
                name_frequency=freq,
            )
            target_rows.append((row["gers_id"], segment, icp_score, "new", 0, now, now))
            if row["has_phone"] and icp_score >= CALL_QUEUE_MIN_SCORE:
                call_eligible += 1

        conn.executemany(
            """
            INSERT INTO targets (
                business_id, segment, icp_score, status, do_not_contact,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(business_id) DO UPDATE SET
                segment = excluded.segment,
                icp_score = excluded.icp_score,
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
    }

    print(f"  Scored {stats['targets']:,} targets")
    print(f"  Call-eligible (phone + score >= {CALL_QUEUE_MIN_SCORE}): {stats['call_eligible']:,}")
    print(f"  Top queue depth available: {stats['top_2000']:,}")
    return stats


if __name__ == "__main__":
    score_targets()
