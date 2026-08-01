"""PII scrubbing and demo display overlays."""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

from config import DEMO_MODE, DEMO_STATS


def _hash_label(seed: str, prefix: str) -> str:
    digest = hashlib.sha256(seed.encode()).hexdigest()[:6].upper()
    return f"{prefix}-{digest}"


def scrub_name(name: str | None, business_id: str) -> str | None:
    if not name or not DEMO_MODE:
        return name
    return _hash_label(business_id, "Business")


def scrub_phone(phone: str | None, business_id: str) -> str | None:
    if not phone or not DEMO_MODE:
        return phone
    digits = hashlib.sha256((business_id + "phone").encode()).hexdigest()
    return f"(555) {digits[:3]}-{digits[3:7]}"


def scrub_email(email: str | None, business_id: str) -> str | None:
    if not email or not DEMO_MODE:
        return email
    local = hashlib.sha256((business_id + "email").encode()).hexdigest()[:8]
    return f"{local}@demo.local"


def scrub_website(website: str | None, business_id: str) -> str | None:
    if not website or not DEMO_MODE:
        return website
    slug = hashlib.sha256(business_id.encode()).hexdigest()[:10]
    return f"https://demo-{slug}.example.com"


def scrub_address(address: str | None, business_id: str) -> str | None:
    if not address or not DEMO_MODE:
        return address
    num = int(hashlib.sha256((business_id + "addr").encode()).hexdigest()[:4], 16) % 9000 + 100
    return f"{num} Demo Street"


def demo_flag() -> bool:
    return DEMO_MODE


def demo_stats_flag() -> bool:
    return DEMO_STATS


def demo_stats_overlay(real: dict) -> dict:
    """Replace outreach funnel metrics with portfolio-friendly sample values."""
    today = date.today()
    activity = []
    for offset in range(29, -1, -1):
        day = today - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        activity.append({"day": day.isoformat(), "count": 12 + (offset % 6) * 4})

    return {
        **real,
        "contacted_this_week": 52,
        "meetings": 4,
        "won": 2,
        "working": 8,
        "win_rate": 16.7,
        "pipeline_value": 9325.0,
        "activity": activity,
    }
