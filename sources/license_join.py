"""
Join Philadelphia business licenses onto Overture businesses.
Licenses are city-only; matching runs for Philadelphia County businesses.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

import pandas as pd

from config import DATA_DIR, NON_BUSINESS_LICENSE_TYPES
from db import DB_PATH, connect, init_db, utc_now


def normalize_name(name: str) -> str:
    text = (name or "").upper()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_address(address: str) -> str:
    text = (address or "").upper()
    replacements = {
        " STREET": " ST",
        " AVENUE": " AVE",
        " ROAD": " RD",
        " BOULEVARD": " BLVD",
        " DRIVE": " DR",
        " LANE": " LN",
        " COURT": " CT",
        " PLACE": " PL",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_real_licenses() -> list[dict]:
    path = DATA_DIR / "all_licenses.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run: python fetch_licenses.py"
        )

    df = pd.read_csv(path, low_memory=False)
    df = df[df["is_active"] == True].copy()  # noqa: E712
    df = df[~df["licensetype"].isin(NON_BUSINESS_LICENSE_TYPES)].copy()
    df = df.dropna(subset=["business_name", "address", "lat", "lng"])

    records = []
    for row in df.itertuples(index=False):
        records.append({
            "norm_name": normalize_name(row.business_name),
            "norm_address": normalize_address(row.address),
            "lat": float(row.lat),
            "lng": float(row.lng),
        })
    return records


def join_licenses(db_path=DB_PATH, max_distance_miles: float = 0.25) -> dict[str, int]:
    print("=" * 60)
    print("JOIN: Philadelphia business licenses")
    print("=" * 60)

    init_db(db_path)
    licenses = load_real_licenses()
    print(f"  Real active licenses loaded: {len(licenses):,}")

    by_name: dict[str, list[dict]] = defaultdict(list)
    by_address: dict[str, list[dict]] = defaultdict(list)
    for lic in licenses:
        by_name[lic["norm_name"]].append(lic)
        if lic["norm_address"]:
            by_address[lic["norm_address"]].append(lic)

    with connect(db_path) as conn:
        businesses = conn.execute(
            """
            SELECT gers_id, name, address, lat, lng
            FROM businesses
            WHERE lat IS NOT NULL AND lng IS NOT NULL
              AND (county = 'Philadelphia' OR city = 'Philadelphia')
            """
        ).fetchall()

    print(f"  Philadelphia-area businesses to match: {len(businesses):,}")

    matched_ids: set[str] = set()

    for biz in businesses:
        norm_name = normalize_name(biz["name"])
        norm_address = normalize_address(biz["address"] or "")

        candidates: list[dict] = []
        seen: set[tuple] = set()

        def add_candidate(lic: dict) -> None:
            key = (lic["norm_name"], lic["norm_address"], lic["lat"], lic["lng"])
            if key not in seen:
                seen.add(key)
                candidates.append(lic)

        for lic in by_name.get(norm_name, []):
            add_candidate(lic)

        if norm_address:
            for lic in by_address.get(norm_address, []):
                add_candidate(lic)

        best_score = -1.0
        for lic in candidates:
            distance = haversine_miles(biz["lat"], biz["lng"], lic["lat"], lic["lng"])
            if distance > max_distance_miles:
                continue

            name_score = 1.0 if lic["norm_name"] == norm_name else 0.7
            addr_score = 1.0 if norm_address and lic["norm_address"] == norm_address else 0.0
            score = name_score + addr_score - (distance * 0.5)
            if score > best_score:
                best_score = score

        if best_score >= 0.8:
            matched_ids.add(biz["gers_id"])

    now = utc_now()
    with connect(db_path) as conn:
        conn.execute("UPDATE businesses SET has_active_license = 0, updated_at = ?", (now,))
        conn.executemany(
            "UPDATE businesses SET has_active_license = 1, updated_at = ? WHERE gers_id = ?",
            [(now, gers_id) for gers_id in matched_ids],
        )

    print(f"  Matched licenses: {len(matched_ids):,}")
    return {"licenses": len(licenses), "matched": len(matched_ids)}


if __name__ == "__main__":
    join_licenses()
