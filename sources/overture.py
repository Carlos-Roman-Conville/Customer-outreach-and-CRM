"""
Pull Overture Maps places for PA, NJ, and DE and load into SQLite.
"""
from __future__ import annotations

import re
from typing import Any

import duckdb

from config import OVERTURE_S3_REGION, OVERTURE_STAC_URL, TRISTATE_BBOX, TRISTATE_STATES
from db import DB_PATH, bulk_upsert_businesses, bulk_upsert_contacts, init_db


def _normalize_phone(value: str) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return value.strip()
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def _normalize_email(value: str) -> str | None:
    if not value:
        return None
    email = value.strip().lower()
    if "@" not in email:
        return None
    return email


def _list_values(values: list | None) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    for item in values:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _get_latest_release(con: duckdb.DuckDBPyConnection) -> str:
    row = con.execute(
        f"SELECT latest FROM '{OVERTURE_STAC_URL}'"
    ).fetchone()
    if not row or not row[0]:
        raise RuntimeError("Could not resolve latest Overture release from STAC catalog")
    return str(row[0])


def _state_regions_sql(release: str) -> str:
    regions = ", ".join(f"'{r}'" for r in TRISTATE_STATES)
    return f"""
        SELECT
            names.primary AS state_name,
            region,
            geometry
        FROM read_parquet(
            's3://overturemaps-us-west-2/release/{release}/theme=divisions/type=division_area/*',
            filename=true,
            hive_partitioning=1
        )
        WHERE subtype = 'region'
          AND country = 'US'
          AND region IN ({regions})
    """


def _county_areas_sql(release: str) -> str:
    regions = ", ".join(f"'{r}'" for r in TRISTATE_STATES)
    return f"""
        SELECT
            names.primary AS county_name,
            region,
            geometry
        FROM read_parquet(
            's3://overturemaps-us-west-2/release/{release}/theme=divisions/type=division_area/*',
            filename=true,
            hive_partitioning=1
        )
        WHERE subtype = 'county'
          AND country = 'US'
          AND region IN ({regions})
    """


def pull_overture(db_path=DB_PATH, batch_size: int = 500) -> dict[str, int]:
    """Download tristate POIs from Overture and upsert into SQLite."""
    print("=" * 60)
    print("PULL: Overture Maps places (PA + NJ + DE)")
    print("=" * 60)

    init_db(db_path)
    con = duckdb.connect()
    con.execute("INSTALL spatial")
    con.execute("LOAD spatial")
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(f"SET s3_region='{OVERTURE_S3_REGION}'")

    release = _get_latest_release(con)
    print(f"  Overture release: {release}")

    bbox = TRISTATE_BBOX
    places_sql = f"""
        WITH tristate_regions AS (
            {_state_regions_sql(release)}
        ),
        county_areas AS (
            {_county_areas_sql(release)}
        ),
        raw_places AS (
            SELECT
                id AS gers_id,
                names.primary AS name,
                categories.primary AS category,
                basic_category,
                CAST(taxonomy AS VARCHAR) AS taxonomy,
                addresses[1].freeform AS address,
                addresses[1].locality AS city,
                addresses[1].region AS state,
                addresses[1].postcode AS zip,
                confidence,
                websites,
                phones,
                emails,
                socials,
                ST_Y(geometry) AS lat,
                ST_X(geometry) AS lng,
                geometry
            FROM read_parquet(
                's3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*',
                filename=true,
                hive_partitioning=1
            )
            WHERE operating_status = 'open'
              AND bbox.xmin BETWEEN {bbox['west']} AND {bbox['east']}
              AND bbox.ymin BETWEEN {bbox['south']} AND {bbox['north']}
        )
        SELECT
            p.gers_id,
            p.name,
            p.category,
            p.basic_category,
            p.taxonomy,
            p.address,
            p.city,
            p.state,
            p.zip,
            p.confidence,
            p.websites,
            p.phones,
            p.emails,
            p.socials,
            p.lat,
            p.lng,
            p.geometry,
            s.state_name,
            c.county_name AS county
        FROM raw_places p
        JOIN tristate_regions s
          ON ST_Contains(s.geometry, p.geometry)
        LEFT JOIN county_areas c
          ON c.region = s.region
         AND ST_Contains(c.geometry, p.geometry)
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY p.gers_id
            ORDER BY c.county_name NULLS LAST
        ) = 1
    """

    print("  Querying Overture (this may take several minutes)...")
    result = con.execute(places_sql)
    columns = [desc[0] for desc in result.description]

    stats = {
        "businesses": 0,
        "phones": 0,
        "emails": 0,
        "websites": 0,
        "with_phone": 0,
        "with_email": 0,
    }

    business_batch: list[dict[str, Any]] = []
    contact_batch: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal business_batch, contact_batch
        if business_batch:
            bulk_upsert_businesses(business_batch, db_path=db_path)
            business_batch = []
        if contact_batch:
            bulk_upsert_contacts(contact_batch, db_path=db_path)
            contact_batch = []

    seen_phone_businesses: set[str] = set()
    seen_email_businesses: set[str] = set()

    while True:
        rows = result.fetchmany(batch_size)
        if not rows:
            break

        for row in rows:
            record = dict(zip(columns, row))
            gers_id = record["gers_id"]
            websites = _list_values(record.get("websites"))
            phones = _list_values(record.get("phones"))
            emails = _list_values(record.get("emails"))

            county = record.get("county")
            if county and county.endswith(" County"):
                county = county[:-7]

            state = record.get("state")
            if state and state.startswith("US-"):
                state = state[3:]

            business = {
                "gers_id": gers_id,
                "name": record.get("name") or "Unknown",
                "category": record.get("category"),
                "basic_category": record.get("basic_category"),
                "taxonomy": record.get("taxonomy"),
                "address": record.get("address"),
                "city": record.get("city"),
                "state": state,
                "zip": record.get("zip"),
                "county": county,
                "lat": record.get("lat"),
                "lng": record.get("lng"),
                "confidence": record.get("confidence"),
                "website": websites[0] if websites else None,
            }
            business_batch.append(business)
            stats["businesses"] += 1

            for website in websites:
                contact_batch.append({
                    "business_id": gers_id,
                    "kind": "website",
                    "value": website,
                    "source": "overture",
                    "confidence": record.get("confidence"),
                })
                stats["websites"] += 1

            for phone in phones:
                normalized = _normalize_phone(phone)
                if not normalized:
                    continue
                contact_batch.append({
                    "business_id": gers_id,
                    "kind": "phone",
                    "value": normalized,
                    "source": "overture",
                    "confidence": record.get("confidence"),
                })
                stats["phones"] += 1
                seen_phone_businesses.add(gers_id)

            for email in emails:
                normalized = _normalize_email(email)
                if not normalized:
                    continue
                contact_batch.append({
                    "business_id": gers_id,
                    "kind": "email",
                    "value": normalized,
                    "source": "overture",
                    "confidence": record.get("confidence"),
                })
                stats["emails"] += 1
                seen_email_businesses.add(gers_id)

            if len(business_batch) >= batch_size:
                flush()

        flush()

    stats["with_phone"] = len(seen_phone_businesses)
    stats["with_email"] = len(seen_email_businesses)

    print(f"\n  Loaded {stats['businesses']:,} businesses")
    print(f"  With phone: {stats['with_phone']:,} ({stats['with_phone']/max(stats['businesses'],1)*100:.1f}%)")
    print(f"  With email: {stats['with_email']:,} ({stats['with_email']/max(stats['businesses'],1)*100:.1f}%)")
    print(f"  Phone contacts: {stats['phones']:,}")
    print(f"  Email contacts: {stats['emails']:,}")
    print(f"  Website contacts: {stats['websites']:,}")

    con.close()
    return stats


if __name__ == "__main__":
    pull_overture()
