"""
Google Places API (New) enrichment — rating and review count for Tier A leads.
"""
from __future__ import annotations

import argparse
import sys
import time

import requests
from tqdm import tqdm

from config import GOOGLE_API_KEY, PLACES_REQUEST_DELAY, REQUEST_TIMEOUT
from db import DB_PATH, connect, init_db, utc_now

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.rating,places.userRatingCount,places.formattedAddress,places.location"


class PlacesQuotaExceeded(Exception):
    """HTTP 429 or API quota error — stop the batch."""


def _require_api_key() -> None:
    if not GOOGLE_API_KEY or not GOOGLE_API_KEY.strip():
        print("ERROR: GOOGLE_API_KEY is not set. Add it to your .env file.")
        sys.exit(1)


def _build_text_query(row) -> str:
    parts = [row["name"] or ""]
    if row["address"]:
        parts.append(row["address"])
    if row["city"]:
        parts.append(row["city"])
    if row["state"]:
        parts.append(row["state"])
    return ", ".join(p.strip() for p in parts if p and p.strip())


def _search_place(text_query: str, lat: float | None, lng: float | None) -> dict | None:
    body: dict = {"textQuery": text_query}
    if lat is not None and lng is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": 500.0,
            }
        }

    resp = requests.post(
        PLACES_SEARCH_URL,
        json=body,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_API_KEY,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        timeout=REQUEST_TIMEOUT,
    )

    if resp.status_code == 429:
        raise PlacesQuotaExceeded("HTTP 429 — quota exceeded")

    if resp.status_code != 200:
        try:
            err = resp.json()
            status = err.get("error", {}).get("status", "")
            if status in ("RESOURCE_EXHAUSTED", "QUOTA_EXCEEDED"):
                raise PlacesQuotaExceeded(f"API quota error: {status}")
        except (ValueError, AttributeError):
            pass
        resp.raise_for_status()

    data = resp.json()
    places = data.get("places") or []
    return places[0] if places else None


def _stamp_no_match(conn, gers_id: str, now: str) -> None:
    conn.execute(
        """
        UPDATE businesses
        SET places_fetched_at = ?, updated_at = ?
        WHERE gers_id = ?
        """,
        (now, now, gers_id),
    )


def _write_match(conn, gers_id: str, place: dict, now: str) -> None:
    place_id = place.get("id")
    rating = place.get("rating")
    review_count = place.get("userRatingCount")
    conn.execute(
        """
        UPDATE businesses
        SET rating = ?, review_count = ?, place_id = ?,
            places_fetched_at = ?, updated_at = ?
        WHERE gers_id = ?
        """,
        (rating, review_count, place_id, now, now, gers_id),
    )


def fetch_places_data(
    db_path=DB_PATH,
    limit: int = 500,
    refresh_days: int | None = None,
) -> dict[str, int]:
    """
    Fetch Google Places ratings for Tier A businesses not yet enriched.
    """
    _require_api_key()
    init_db(db_path)
    now = utc_now()

    fetched_clause = "b.places_fetched_at IS NULL"
    params: list = []
    if refresh_days is not None:
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(days=refresh_days)).replace(
            microsecond=0
        ).isoformat()
        fetched_clause = "(b.places_fetched_at IS NULL OR b.places_fetched_at < ?)"
        params.append(cutoff)

    params.append(limit)

    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT b.gers_id, b.name, b.address, b.city, b.state, b.lat, b.lng
            FROM businesses b
            JOIN targets t ON t.business_id = b.gers_id
            WHERE t.revenue_tier = 'A'
              AND {fetched_clause}
              AND b.name IS NOT NULL
            ORDER BY t.revenue_tier ASC,
                     b.places_fetched_at IS NOT NULL ASC,
                     t.icp_score DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    stats = {
        "processed": 0,
        "matched": 0,
        "no_match": 0,
        "errors": 0,
        "quota_stopped": 0,
    }

    for row in tqdm(rows, desc="Places enrichment"):
        gers_id = row["gers_id"]
        try:
            text_query = _build_text_query(row)
            place = _search_place(text_query, row["lat"], row["lng"])
            with connect(db_path) as conn:
                if place:
                    _write_match(conn, gers_id, place, now)
                    stats["matched"] += 1
                else:
                    _stamp_no_match(conn, gers_id, now)
                    stats["no_match"] += 1
            stats["processed"] += 1
            time.sleep(PLACES_REQUEST_DELAY)
        except PlacesQuotaExceeded as exc:
            print(f"\nStopping batch: {exc}")
            stats["quota_stopped"] = 1
            break
        except Exception:
            stats["errors"] += 1
            try:
                with connect(db_path) as conn:
                    _stamp_no_match(conn, gers_id, now)
            except Exception:
                pass

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Google Places ratings for Tier A leads")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--refresh-days", type=int, default=None)
    args = parser.parse_args()
    result = fetch_places_data(limit=args.limit, refresh_days=args.refresh_days)
    print(result)
