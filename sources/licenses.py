"""
License and business registration enrichment pipeline.

Data sources:
  1. PA Department of State Business Registration (Socrata API)
  2. PA Sales Tax Licenses (Socrata API)
  3. Philadelphia Commercial Activity Licenses (CARTO SQL API)
  4. Philadelphia L&I Business Licenses (CARTO SQL API)
  5. NPPES Healthcare NPI Registry (CMS bulk download)
  6. Delaware Division of Revenue Business Licenses (Socrata API)
  7. NJ Division of Revenue Business Search (web scrape)
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import re
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from config import (
    CARTO_API,
    DATA_DIR,
    DB_PATH,
    DE_LICENSE_API,
    LICENSE_DATA_MAX_AGE_DAYS,
    NON_BUSINESS_LICENSE_TYPES,
    NJ_REQUEST_DELAY,
    NJ_SEARCH_URL,
    NPPES_FILES_PAGE,
    NPPES_TARGET_STATES,
    PA_DOS_API,
    PA_EXCLUDED_REGISTRATION_TYPES,
    PA_SALES_TAX_API,
    PHILLY_BLI_TABLE,
    PHILLY_CAL_TABLE,
    REQUEST_TIMEOUT,
    USER_AGENT,
)
from db import connect, init_db, utc_now

PA_REG_PATH = DATA_DIR / "pa_registrations.csv"
PA_SALES_TAX_PATH = DATA_DIR / "pa_sales_tax.csv"
PHILLY_CAL_PATH = DATA_DIR / "philly_cal_licenses.csv"
PHILLY_BLI_PATH = DATA_DIR / "philly_business_licenses.csv"
DE_LICENSE_PATH = DATA_DIR / "de_licenses.csv"
NPPES_ZIP_PATH = DATA_DIR / "nppes_full.zip"
NPPES_TRISTATE_PATH = DATA_DIR / "nppes_tristate.csv"

NAME_SUFFIXES = (
    "LLC",
    "INC",
    "CORP",
    "CORPORATION",
    "INCORPORATED",
    "LIMITED",
    "LTD",
    "LP",
    "LLP",
    "LLLP",
    "CO",
    "COMPANY",
    "ENTERPRISES",
    "ENTERPRISE",
    "SERVICES",
    "SERVICE",
    "GROUP",
    "HOLDINGS",
    "PARTNERS",
    "ASSOCIATES",
    "PC",
    "PA",
    "PLLC",
)

_SUFFIX_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(s) for s in NAME_SUFFIXES) + r")\b\.?",
    re.IGNORECASE,
)


def normalize_name(name: str | None) -> str:
    """Normalize business name for matching (uppercase, strip suffixes/punct)."""
    text = (name or "").upper()
    text = _SUFFIX_RE.sub(" ", text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_address(address: str | None) -> str:
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
        " SUITE": " STE",
        " FLOOR": " FL",
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
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT})
    return sess


def _file_is_fresh(path: Path, max_age_days: int = LICENSE_DATA_MAX_AGE_DAYS) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc
    )
    return age <= timedelta(days=max_age_days)


def _request_with_retry(
    sess: requests.Session,
    method: str,
    url: str,
    *,
    max_retries: int = 6,
    **kwargs: Any,
) -> requests.Response:
    delay = 5.0
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = sess.request(method, url, timeout=REQUEST_TIMEOUT * 4, **kwargs)
            if resp.status_code == 429:
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
                continue
            resp.raise_for_status()
            return resp
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    raise RuntimeError(f"Request failed after {max_retries} retries: {url}") from last_exc


def _parse_geo_point(value: Any) -> tuple[float | None, float | None]:
    """Parse Socrata/GeoJSON point into (lat, lng)."""
    if value is None:
        return None, None
    if isinstance(value, dict):
        if "latitude" in value and "longitude" in value:
            try:
                return float(value["latitude"]), float(value["longitude"])
            except (TypeError, ValueError):
                return None, None
        coords = value.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            try:
                return float(coords[1]), float(coords[0])
            except (TypeError, ValueError):
                return None, None
    if isinstance(value, str) and value.strip():
        # POINT (lng lat) or "lat, lng"
        text = value.strip()
        m = re.search(r"(-?\d+\.?\d*)\s+(-?\d+\.?\d*)", text)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            # Heuristic: PA/DE lng is negative and around -75
            if a < 0:
                return b, a
            return a, b
    return None, None


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    return text[:10]


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------


def fetch_pa_registrations(force: bool = False) -> Path:
    """Download PA business registrations statewide via SODA API."""
    print("=" * 60)
    print("FETCH: PA Department of State registrations (full state)")
    print("=" * 60)

    if _file_is_fresh(PA_REG_PATH) and not force:
        print(f"  Using cached {PA_REG_PATH} (< {LICENSE_DATA_MAX_AGE_DAYS} days old)")
        return PA_REG_PATH

    excluded = ",".join(f"'{t}'" for t in sorted(PA_EXCLUDED_REGISTRATION_TYPES))
    where = f"typeofbusinessregistration not in({excluded})"

    page_size = 10000
    offset = 0
    total_written = 0
    fieldnames = [
        "business_name",
        "filing_number",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "zip",
        "typeofbusinessregistration",
        "creationdate",
        "shortcountyname",
        "lat",
        "lng",
    ]

    sess = _session()
    PA_REG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = PA_REG_PATH.with_suffix(".tmp.csv")

    # Approximate page count for progress (spec totals minus nonprofits ~1.49M)
    expected = 1_490_000
    pbar = tqdm(total=expected, desc="PA registrations", unit="rows")

    seen_filings: set[str] = set()
    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        while True:
            params = {
                "$where": where,
                "$limit": page_size,
                "$offset": offset,
                "$order": "filing_number,last_name,first_name",
                "$select": (
                    "business_name,filing_number,address_line1,address_line2,"
                    "city,state,zip,typeofbusinessregistration,creationdate,"
                    "shortcountyname,georeferenced_latitude__longitude"
                ),
            }
            resp = _request_with_retry(sess, "GET", PA_DOS_API, params=params)
            rows = resp.json()
            if not rows:
                break

            for row in rows:
                filing = (row.get("filing_number") or "").strip()
                if not filing or filing in seen_filings:
                    continue
                seen_filings.add(filing)

                lat, lng = _parse_geo_point(row.get("georeferenced_latitude__longitude"))
                address = " ".join(
                    part
                    for part in [
                        (row.get("address_line1") or "").strip(),
                        (row.get("address_line2") or "").strip(),
                    ]
                    if part
                )
                writer.writerow(
                    {
                        "business_name": row.get("business_name") or "",
                        "filing_number": filing,
                        "address_line1": address,
                        "address_line2": "",
                        "city": row.get("city") or "",
                        "state": row.get("state") or "",
                        "zip": row.get("zip") or "",
                        "typeofbusinessregistration": row.get(
                            "typeofbusinessregistration"
                        )
                        or "",
                        "creationdate": _iso_date(row.get("creationdate")) or "",
                        "shortcountyname": row.get("shortcountyname") or "",
                        "lat": lat if lat is not None else "",
                        "lng": lng if lng is not None else "",
                    }
                )
                total_written += 1

            pbar.update(len(rows))
            offset += page_size
            if len(rows) < page_size:
                break
            time.sleep(0.05)

    pbar.close()
    tmp_path.replace(PA_REG_PATH)
    print(f"  Saved {total_written:,} unique filings to {PA_REG_PATH}")
    return PA_REG_PATH


def fetch_philly_cal(force: bool = False) -> Path:
    """Download active Philadelphia Commercial Activity Licenses via CARTO."""
    print("=" * 60)
    print("FETCH: Philadelphia Commercial Activity Licenses")
    print("=" * 60)

    if _file_is_fresh(PHILLY_CAL_PATH) and not force:
        print(f"  Using cached {PHILLY_CAL_PATH} (< {LICENSE_DATA_MAX_AGE_DAYS} days old)")
        return PHILLY_CAL_PATH

    page_size = 10000
    offset = 0
    total_written = 0
    fieldnames = [
        "companyname",
        "licensenum",
        "licensestatus",
        "issuedate",
        "legalentitytype",
        "ownercontact1mailingaddress",
        "ownercontact1city",
        "ownercontact1state",
        "ownercontact1zippostalcode",
        "legalfirstname",
        "legallastname",
    ]

    sess = _session()
    PHILLY_CAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = PHILLY_CAL_PATH.with_suffix(".tmp.csv")
    pbar = tqdm(desc="Philly CAL", unit="rows")

    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        while True:
            query = f"""
            SELECT companyname, licensenum, licensestatus, issuedate,
                   legalentitytype, ownercontact1mailingaddress,
                   ownercontact1city, ownercontact1state, ownercontact1zippostalcode,
                   legalfirstname, legallastname
            FROM {PHILLY_CAL_TABLE}
            WHERE licensestatus = 'Active'
            ORDER BY licensenum
            LIMIT {page_size} OFFSET {offset}
            """
            resp = _request_with_retry(
                sess, "GET", CARTO_API, params={"q": query, "format": "json"}
            )
            rows = resp.json().get("rows") or []
            if not rows:
                break

            for row in rows:
                writer.writerow({k: row.get(k) or "" for k in fieldnames})
                total_written += 1

            pbar.update(len(rows))
            offset += page_size
            if len(rows) < page_size:
                break

    pbar.close()
    tmp_path.replace(PHILLY_CAL_PATH)
    print(f"  Saved {total_written:,} active CALs to {PHILLY_CAL_PATH}")
    return PHILLY_CAL_PATH


def fetch_de_licenses(force: bool = False) -> Path:
    """Download Delaware business licenses via Socrata SODA API."""
    print("=" * 60)
    print("FETCH: Delaware Division of Revenue licenses")
    print("=" * 60)

    if _file_is_fresh(DE_LICENSE_PATH) and not force:
        print(f"  Using cached {DE_LICENSE_PATH} (< {LICENSE_DATA_MAX_AGE_DAYS} days old)")
        return DE_LICENSE_PATH

    page_size = 50000
    offset = 0
    total_written = 0
    fieldnames = [
        "business_name",
        "trade_name",
        "category",
        "current_license_valid_from",
        "current_license_valid_to",
        "address_1",
        "address_2",
        "city",
        "state",
        "zip",
        "license_number",
        "lat",
        "lng",
    ]

    sess = _session()
    DE_LICENSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = DE_LICENSE_PATH.with_suffix(".tmp.csv")
    pbar = tqdm(desc="DE licenses", unit="rows")

    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        while True:
            params = {
                "$limit": page_size,
                "$offset": offset,
                "$order": "license_number",
            }
            resp = _request_with_retry(sess, "GET", DE_LICENSE_API, params=params)
            rows = resp.json()
            if not rows:
                break

            for row in rows:
                lat, lng = _parse_geo_point(row.get("geocoded_location"))
                writer.writerow(
                    {
                        "business_name": row.get("business_name") or "",
                        "trade_name": row.get("trade_name") or "",
                        "category": row.get("category") or "",
                        "current_license_valid_from": _iso_date(
                            row.get("current_license_valid_from")
                        )
                        or "",
                        "current_license_valid_to": _iso_date(
                            row.get("current_license_valid_to")
                        )
                        or "",
                        "address_1": row.get("address_1") or "",
                        "address_2": row.get("address_2") or "",
                        "city": row.get("city") or "",
                        "state": row.get("state") or "",
                        "zip": row.get("zip") or "",
                        "license_number": row.get("license_number") or "",
                        "lat": lat if lat is not None else "",
                        "lng": lng if lng is not None else "",
                    }
                )
                total_written += 1

            pbar.update(len(rows))
            offset += page_size
            if len(rows) < page_size:
                break

    pbar.close()
    tmp_path.replace(DE_LICENSE_PATH)
    print(f"  Saved {total_written:,} DE licenses to {DE_LICENSE_PATH}")
    return DE_LICENSE_PATH


def fetch_pa_sales_tax(force: bool = False) -> Path:
    """Download PA Sales/Use/Hotel Occupancy tax licenses statewide."""
    print("=" * 60)
    print("FETCH: PA Sales Tax licenses (full state)")
    print("=" * 60)

    if _file_is_fresh(PA_SALES_TAX_PATH) and not force:
        print(
            f"  Using cached {PA_SALES_TAX_PATH} (< {LICENSE_DATA_MAX_AGE_DAYS} days old)"
        )
        return PA_SALES_TAX_PATH

    page_size = 10000
    offset = 0
    total_written = 0
    today = date.today().isoformat()
    fieldnames = [
        "row_id",
        "legal_name",
        "trade_name",
        "street_address",
        "city",
        "county",
        "postal_code",
        "license_type",
        "expiration_date",
        "account",
        "lat",
        "lng",
    ]

    sess = _session()
    PA_SALES_TAX_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = PA_SALES_TAX_PATH.with_suffix(".tmp.csv")
    pbar = tqdm(desc="PA sales tax", unit="rows")

    seen_ids: set[str] = set()
    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        while True:
            params = {
                "$limit": page_size,
                "$offset": offset,
                "$order": "account",
                "$select": (
                    ":id,legal_name,trade_name,street_address,city,county,"
                    "postal_code,license_type,expiration_date,account,"
                    "georeferenced_latitude_longitude_points"
                ),
            }
            resp = _request_with_retry(sess, "GET", PA_SALES_TAX_API, params=params)
            rows = resp.json()
            if not rows:
                break

            for row in rows:
                row_id = (row.get(":id") or "").strip()
                if not row_id or row_id in seen_ids:
                    continue
                seen_ids.add(row_id)

                exp = _iso_date(row.get("expiration_date"))
                if exp and exp < today:
                    continue

                lat, lng = _parse_geo_point(
                    row.get("georeferenced_latitude_longitude_points")
                )
                writer.writerow(
                    {
                        "row_id": row_id,
                        "legal_name": row.get("legal_name") or "",
                        "trade_name": row.get("trade_name") or "",
                        "street_address": row.get("street_address") or "",
                        "city": row.get("city") or "",
                        "county": row.get("county") or "",
                        "postal_code": row.get("postal_code") or "",
                        "license_type": row.get("license_type") or "",
                        "expiration_date": exp or "",
                        "account": row.get("account") or "",
                        "lat": lat if lat is not None else "",
                        "lng": lng if lng is not None else "",
                    }
                )
                total_written += 1

            pbar.update(len(rows))
            offset += page_size
            if len(rows) < page_size:
                break
            time.sleep(0.05)

    pbar.close()
    tmp_path.replace(PA_SALES_TAX_PATH)
    print(f"  Saved {total_written:,} active PA tax licenses to {PA_SALES_TAX_PATH}")
    return PA_SALES_TAX_PATH


def _find_nppes_v2_zip_url(sess: requests.Session) -> str:
    """Locate the current monthly NPPES V.2 full-file download URL."""
    resp = _request_with_retry(sess, "GET", NPPES_FILES_PAGE)
    patterns = [
        re.compile(r"href='(\./NPPES_Data_Dissemination_[^']+V2\.zip)'", re.IGNORECASE),
        re.compile(
            r'href="(\./NPPES_Data_Dissemination_[^"]+V2\.zip)"', re.IGNORECASE
        ),
        re.compile(r"(NPPES_Data_Dissemination_[A-Za-z]+_\d{4}_V2\.zip)", re.IGNORECASE),
    ]
    candidates: list[str] = []
    for pattern in patterns:
        candidates.extend(pattern.findall(resp.text))
    monthly = [
        c
        for c in candidates
        if "Weekly" not in c
        and "Deactivated" not in c
        and re.search(r"_V2\.zip$", c, re.IGNORECASE)
    ]
    if not monthly:
        raise RuntimeError("Could not find NPPES V.2 download URL on CMS page")
    href = monthly[0]
    if href.startswith("./"):
        href = href[2:]
    if href.startswith("http"):
        return href
    return f"https://download.cms.gov/nppes/{href}"


def fetch_nppes(force: bool = False) -> Path:
    """Download and filter NPPES NPI registry to tristate Type 1 + Type 2 records."""
    print("=" * 60)
    print("FETCH: NPPES NPI registry (tristate filter)")
    print("=" * 60)

    if _file_is_fresh(NPPES_TRISTATE_PATH) and not force:
        print(
            f"  Using cached {NPPES_TRISTATE_PATH} (< {LICENSE_DATA_MAX_AGE_DAYS} days old)"
        )
        return NPPES_TRISTATE_PATH

    sess = _session()
    zip_url = _find_nppes_v2_zip_url(sess)
    print(f"  Download URL: {zip_url}")

    NPPES_ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not NPPES_ZIP_PATH.exists() or force:
        print("  Downloading NPPES zip (this may take several minutes)...")
        with _request_with_retry(sess, "GET", zip_url, stream=True) as resp:
            with NPPES_ZIP_PATH.open("wb") as out:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        out.write(chunk)
        print(f"  Saved zip to {NPPES_ZIP_PATH}")

    fieldnames = [
        "npi",
        "entity_type",
        "org_name",
        "other_org_name",
        "provider_last_name",
        "provider_first_name",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "taxonomy",
        "enumeration_date",
    ]

    tmp_path = NPPES_TRISTATE_PATH.with_suffix(".tmp.csv")
    total_written = 0

    with zipfile.ZipFile(NPPES_ZIP_PATH) as zf:
        csv_names = [n for n in zf.namelist() if n.startswith("npidata_pfile") and n.endswith(".csv")]
        if not csv_names:
            raise RuntimeError("NPPES zip missing npidata_pfile CSV")
        csv_name = csv_names[0]
        print(f"  Streaming {csv_name} ...")

        with zf.open(csv_name) as raw, tmp_path.open(
            "w", newline="", encoding="utf-8"
        ) as out_fh:
            text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
            reader = csv.DictReader(text)
            writer = csv.DictWriter(out_fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()

            for row in tqdm(reader, desc="NPPES filter", unit="rows"):
                entity_type = (row.get("Entity Type Code") or "").strip()
                if entity_type not in ("1", "2"):
                    continue
                if (row.get("NPI Deactivation Date") or "").strip():
                    continue
                state = (
                    row.get("Provider Business Practice Location Address State Name") or ""
                ).strip().upper()
                if state not in NPPES_TARGET_STATES:
                    continue

                addr1 = row.get("Provider First Line Business Practice Location Address") or ""
                addr2 = row.get("Provider Second Line Business Practice Location Address") or ""
                writer.writerow(
                    {
                        "npi": row.get("NPI") or "",
                        "entity_type": entity_type,
                        "org_name": row.get("Provider Organization Name (Legal Business Name)") or "",
                        "other_org_name": row.get("Provider Other Organization Name") or "",
                        "provider_last_name": row.get("Provider Last Name (Legal Name)") or "",
                        "provider_first_name": row.get("Provider First Name") or "",
                        "address_line1": addr1,
                        "address_line2": addr2,
                        "city": row.get("Provider Business Practice Location Address City Name") or "",
                        "state": state,
                        "postal_code": row.get(
                            "Provider Business Practice Location Address Postal Code"
                        )
                        or "",
                        "taxonomy": row.get("Healthcare Provider Taxonomy Code_1") or "",
                        "enumeration_date": _iso_date(row.get("Provider Enumeration Date")) or "",
                    }
                )
                total_written += 1

    tmp_path.replace(NPPES_TRISTATE_PATH)
    print(f"  Saved {total_written:,} tristate NPPES records to {NPPES_TRISTATE_PATH}")
    return NPPES_TRISTATE_PATH


def fetch_philly_bli(force: bool = False) -> Path:
    """Download active Philadelphia L&I business licenses (non-rental)."""
    print("=" * 60)
    print("FETCH: Philadelphia L&I business licenses")
    print("=" * 60)

    if _file_is_fresh(PHILLY_BLI_PATH) and not force:
        print(
            f"  Using cached {PHILLY_BLI_PATH} (< {LICENSE_DATA_MAX_AGE_DAYS} days old)"
        )
        return PHILLY_BLI_PATH

    page_size = 10000
    offset = 0
    total_written = 0
    fieldnames = [
        "business_name",
        "legalname",
        "licensetype",
        "licensestatus",
        "address",
        "zip",
        "cal_number",
        "licensenum",
        "lat",
        "lng",
        "initialissuedate",
        "expirationdate",
    ]

    excluded = ", ".join(f"'{t}'" for t in sorted(NON_BUSINESS_LICENSE_TYPES))
    sess = _session()
    PHILLY_BLI_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = PHILLY_BLI_PATH.with_suffix(".tmp.csv")
    pbar = tqdm(desc="Philly BLI", unit="rows")

    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        while True:
            query = f"""
            SELECT business_name, legalname, licensetype, licensestatus,
                   address, zip, cal_number, licensenum,
                   ST_X(the_geom) AS lng, ST_Y(the_geom) AS lat,
                   initialissuedate, expirationdate
            FROM {PHILLY_BLI_TABLE}
            WHERE licensestatus = 'Active'
              AND licensetype NOT IN ({excluded})
            ORDER BY licensenum
            LIMIT {page_size} OFFSET {offset}
            """
            resp = _request_with_retry(
                sess, "GET", CARTO_API, params={"q": query, "format": "json"}
            )
            rows = resp.json().get("rows") or []
            if not rows:
                break

            for row in rows:
                writer.writerow(
                    {
                        "business_name": row.get("business_name") or "",
                        "legalname": row.get("legalname") or "",
                        "licensetype": row.get("licensetype") or "",
                        "licensestatus": row.get("licensestatus") or "",
                        "address": row.get("address") or "",
                        "zip": row.get("zip") or "",
                        "cal_number": str(row.get("cal_number") or ""),
                        "licensenum": str(row.get("licensenum") or ""),
                        "lat": row.get("lat") if row.get("lat") is not None else "",
                        "lng": row.get("lng") if row.get("lng") is not None else "",
                        "initialissuedate": row.get("initialissuedate") or "",
                        "expirationdate": row.get("expirationdate") or "",
                    }
                )
                total_written += 1

            pbar.update(len(rows))
            offset += page_size
            if len(rows) < page_size:
                break

    pbar.close()
    tmp_path.replace(PHILLY_BLI_PATH)
    print(f"  Saved {total_written:,} Philly BLI records to {PHILLY_BLI_PATH}")
    return PHILLY_BLI_PATH


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _score_candidate(
    *,
    name_exact: bool,
    addr_exact: bool,
    biz_lat: float | None,
    biz_lng: float | None,
    cand_lat: float | None,
    cand_lng: float | None,
    max_distance_miles: float,
) -> float:
    if not name_exact and not addr_exact:
        return -1.0

    score = 0.0
    if name_exact:
        score += 1.0
    if addr_exact:
        score += 0.5

    if (
        biz_lat is not None
        and biz_lng is not None
        and cand_lat is not None
        and cand_lng is not None
    ):
        distance = haversine_miles(biz_lat, biz_lng, cand_lat, cand_lng)
        if distance > max_distance_miles:
            # Name+address exact can still pass; pure geo mismatch rejects weak matches
            if not (name_exact and addr_exact):
                return -1.0
        else:
            score -= distance * 0.5

    return score


def _score_pa_sales_tax(
    *,
    trade_match: bool,
    legal_match: bool,
    addr_exact: bool,
    biz_lat: float | None,
    biz_lng: float | None,
    cand_lat: float | None,
    cand_lng: float | None,
    max_distance_miles: float,
) -> float:
    """PA Sales Tax matching: trade name is primary; GPS confirms when present."""
    gps_ok = False
    gps_distance: float | None = None
    if (
        biz_lat is not None
        and biz_lng is not None
        and cand_lat is not None
        and cand_lng is not None
    ):
        gps_distance = haversine_miles(biz_lat, biz_lng, cand_lat, cand_lng)
        gps_ok = gps_distance <= max_distance_miles

    if trade_match:
        if gps_ok and gps_distance is not None:
            return 1.0 - gps_distance * 0.1
        return 1.0

    if legal_match:
        if addr_exact or gps_ok:
            score = 0.7
            if gps_ok and gps_distance is not None:
                score -= gps_distance * 0.1
            return score
        if (
            biz_lat is not None
            and biz_lng is not None
            and cand_lat is not None
            and cand_lng is not None
            and not gps_ok
        ):
            return -1.0
        return -1.0

    if addr_exact and gps_ok:
        return 0.5

    return -1.0


def _build_bli_by_cal_number(
    bli_rows: list[dict[str, str]],
) -> dict[str, list[dict[str, Any]]]:
    """Index BLI records by cal_number for CAL address enrichment."""
    by_cal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in bli_rows:
        cal_num = (row.get("cal_number") or "").strip()
        if not cal_num:
            continue
        address = (row.get("address") or "").strip()
        by_cal[cal_num].append(
            {
                "address": address,
                "norm_address": normalize_address(address),
                "lat": _float_or_none(row.get("lat")),
                "lng": _float_or_none(row.get("lng")),
                "business_name": row.get("business_name") or "",
                "legalname": row.get("legalname") or "",
            }
        )
    return by_cal


def _match_with_address_threshold(
    *,
    norm_name: str,
    norm_address: str,
    biz_lat: float | None,
    biz_lng: float | None,
    by_name: dict[str, list[dict[str, Any]]],
    by_address: dict[str, list[dict[str, Any]]],
    max_distance_miles: float = 0.5,
    name_threshold: float = 0.8,
    address_threshold: float = 0.5,
) -> dict[str, Any] | None:
    """Match using name score or single-tenant address-only accept."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(rec: dict[str, Any]) -> None:
        key = rec.get("key") or f"{rec.get('norm_name')}|{rec.get('norm_address')}"
        if key not in seen:
            seen.add(key)
            candidates.append(rec)

    if norm_name:
        for rec in by_name.get(norm_name, []):
            add(rec)
    if norm_address:
        for rec in by_address.get(norm_address, []):
            add(rec)

    best: dict[str, Any] | None = None
    best_score = -1.0
    for rec in candidates:
        name_exact = bool(norm_name) and rec.get("norm_name") == norm_name
        addr_exact = bool(norm_address) and rec.get("norm_address") == norm_address
        score = _score_candidate(
            name_exact=name_exact,
            addr_exact=addr_exact,
            biz_lat=biz_lat,
            biz_lng=biz_lng,
            cand_lat=rec.get("lat"),
            cand_lng=rec.get("lng"),
            max_distance_miles=max_distance_miles,
        )
        if score > best_score:
            best_score = score
            best = rec

    if best is not None and best_score >= name_threshold:
        return best

    if norm_address:
        at_addr = by_address.get(norm_address, [])
        if len(at_addr) == 1:
            rec = at_addr[0]
            score = _score_candidate(
                name_exact=False,
                addr_exact=True,
                biz_lat=biz_lat,
                biz_lng=biz_lng,
                cand_lat=rec.get("lat"),
                cand_lng=rec.get("lng"),
                max_distance_miles=max_distance_miles,
            )
            if score >= address_threshold:
                return rec

    return None


def _registration_source_expr() -> str:
    """SQL fragment building registration_source from all license columns."""
    sources = [
        ("pa_registration_status", "'registered'", "pa_dos"),
        ("pa_sales_tax_status", "'active'", "pa_sales_tax"),
        ("philly_cal_status", "'active'", "philly_cal"),
        ("philly_bli_status", "'active'", "philly_bli"),
        ("nj_registration_status", "'registered'", "nj_dor"),
        ("de_license_status", "'active'", "de_dor"),
        ("nppes_status", "'active'", "nppes"),
    ]
    parts: list[str] = []
    for idx, (col, val, label) in enumerate(sources):
        prefix = ""
        if idx > 0:
            prior = " OR ".join(f"{c} = {v}" for c, v, _ in sources[:idx])
            prefix = f"CASE WHEN {prior} THEN '+' ELSE '' END || "
        parts.append(
            f"CASE WHEN {col} = {val} THEN {prefix}'{label}' ELSE '' END"
        )
    return " || ".join(parts)


def _has_active_license_expr() -> str:
    checks = [
        "pa_registration_status = 'registered'",
        "pa_sales_tax_status = 'active'",
        "philly_cal_status = 'active'",
        "philly_bli_status = 'active'",
        "nj_registration_status = 'registered'",
        "de_license_status = 'active'",
        "nppes_status = 'active'",
    ]
    return " OR ".join(checks)


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def update_license_rollup(db_path=DB_PATH) -> dict[str, int]:
    """Recompute has_active_license and registration_source from enrichment columns."""
    init_db(db_path)
    now = utc_now()
    active_expr = _has_active_license_expr()
    source_expr = _registration_source_expr()
    with connect(db_path) as conn:
        conn.execute(
            f"""
            UPDATE businesses
            SET has_active_license = CASE
                WHEN {active_expr}
                THEN 1 ELSE 0 END,
                registration_source = CASE
                    WHEN {active_expr}
                    THEN trim({source_expr})
                    ELSE NULL
                END,
                updated_at = ?
            """,
            (now,),
        )
        licensed = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE has_active_license = 1"
        ).fetchone()[0]
    return {"licensed": int(licensed)}


# ---------------------------------------------------------------------------
# Joiners
# ---------------------------------------------------------------------------


def join_pa_registrations(max_distance_miles: float = 0.5, db_path=DB_PATH) -> dict[str, int]:
    """Match PA registration data to businesses in DB."""
    print("=" * 60)
    print("JOIN: PA state registrations")
    print("=" * 60)

    if not PA_REG_PATH.exists():
        raise FileNotFoundError(f"Missing {PA_REG_PATH}. Run: python -m sources.licenses fetch-pa")

    init_db(db_path)
    rows = _load_csv_rows(PA_REG_PATH)
    print(f"  Loaded {len(rows):,} PA filings")

    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_address: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rec = {
            "norm_name": normalize_name(row.get("business_name")),
            "norm_address": normalize_address(row.get("address_line1")),
            "filing_number": row.get("filing_number") or "",
            "reg_type": row.get("typeofbusinessregistration") or "",
            "creationdate": row.get("creationdate") or "",
            "lat": _float_or_none(row.get("lat")),
            "lng": _float_or_none(row.get("lng")),
        }
        if rec["norm_name"]:
            by_name[rec["norm_name"]].append(rec)
        if rec["norm_address"]:
            by_address[rec["norm_address"]].append(rec)

    with connect(db_path) as conn:
        businesses = conn.execute(
            """
            SELECT gers_id, name, address, lat, lng, county, state, city
            FROM businesses
            WHERE state = 'PA'
            """,
        ).fetchall()

    print(f"  PA businesses to match: {len(businesses):,}")
    matches: dict[str, dict[str, Any]] = {}

    for biz in tqdm(businesses, desc="Matching PA"):
        norm_name = normalize_name(biz["name"])
        norm_address = normalize_address(biz["address"] or "")
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(rec: dict[str, Any]) -> None:
            key = rec["filing_number"] or f"{rec['norm_name']}|{rec['norm_address']}"
            if key not in seen:
                seen.add(key)
                candidates.append(rec)

        if norm_name:
            for rec in by_name.get(norm_name, []):
                add(rec)
        if norm_address:
            for rec in by_address.get(norm_address, []):
                add(rec)

        best_score = -1.0
        best: dict[str, Any] | None = None
        for rec in candidates:
            score = _score_candidate(
                name_exact=bool(norm_name) and rec["norm_name"] == norm_name,
                addr_exact=bool(norm_address) and rec["norm_address"] == norm_address,
                biz_lat=biz["lat"],
                biz_lng=biz["lng"],
                cand_lat=rec["lat"],
                cand_lng=rec["lng"],
                max_distance_miles=max_distance_miles,
            )
            if score > best_score:
                best_score = score
                best = rec

        if best is not None and best_score >= 0.8:
            matches[biz["gers_id"]] = best

    now = utc_now()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE businesses
            SET pa_registration_status = NULL,
                pa_filing_number = NULL,
                pa_registration_type = NULL,
                business_creation_date = NULL,
                registration_checked_at = ?,
                updated_at = ?
            WHERE state = 'PA'
            """,
            (now, now),
        )
        conn.executemany(
            """
            UPDATE businesses
            SET pa_registration_status = 'registered',
                pa_filing_number = ?,
                pa_registration_type = ?,
                business_creation_date = ?,
                registration_checked_at = ?,
                updated_at = ?
            WHERE gers_id = ?
            """,
            [
                (
                    m["filing_number"],
                    m["reg_type"],
                    m["creationdate"] or None,
                    now,
                    now,
                    gers_id,
                )
                for gers_id, m in matches.items()
            ],
        )

    update_license_rollup(db_path)
    stats = {
        "matched": len(matches),
        "unmatched": len(businesses) - len(matches),
        "total": len(businesses),
    }
    print(f"  Matched {stats['matched']:,} / {stats['total']:,}")
    return stats


def join_pa_sales_tax(max_distance_miles: float = 0.5, db_path=DB_PATH) -> dict[str, int]:
    """Match PA Sales Tax licenses to PA businesses."""
    print("=" * 60)
    print("JOIN: PA Sales Tax licenses")
    print("=" * 60)

    if not PA_SALES_TAX_PATH.exists():
        raise FileNotFoundError(
            f"Missing {PA_SALES_TAX_PATH}. Run: python -m sources.licenses fetch-pa-tax"
        )

    init_db(db_path)
    rows = _load_csv_rows(PA_SALES_TAX_PATH)
    print(f"  Loaded {len(rows):,} PA tax licenses")

    by_trade: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_legal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_address: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        trade_norm = normalize_name(row.get("trade_name"))
        legal_norm = normalize_name(row.get("legal_name"))
        address = (row.get("street_address") or "").strip()
        rec = {
            "trade_norm": trade_norm,
            "legal_norm": legal_norm,
            "norm_address": normalize_address(address),
            "trade_name": row.get("trade_name") or "",
            "address": address,
            "license_type": row.get("license_type") or "",
            "expiration_date": row.get("expiration_date") or "",
            "lat": _float_or_none(row.get("lat")),
            "lng": _float_or_none(row.get("lng")),
            "row_id": row.get("row_id") or "",
        }
        if trade_norm:
            by_trade[trade_norm].append(rec)
        if legal_norm and legal_norm != trade_norm:
            by_legal[legal_norm].append(rec)
        if rec["norm_address"]:
            by_address[rec["norm_address"]].append(rec)

    with connect(db_path) as conn:
        businesses = conn.execute(
            """
            SELECT gers_id, name, address, lat, lng, state
            FROM businesses
            WHERE state = 'PA'
            """
        ).fetchall()

    print(f"  PA businesses to match: {len(businesses):,}")
    matches: dict[str, dict[str, Any]] = {}

    for biz in tqdm(businesses, desc="Matching PA tax"):
        norm_name = normalize_name(biz["name"])
        norm_address = normalize_address(biz["address"] or "")
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(rec: dict[str, Any]) -> None:
            key = rec["row_id"] or f"{rec['trade_norm']}|{rec['norm_address']}"
            if key not in seen:
                seen.add(key)
                candidates.append(rec)

        if norm_name:
            for rec in by_trade.get(norm_name, []):
                add(rec)
            for rec in by_legal.get(norm_name, []):
                add(rec)
        if norm_address:
            for rec in by_address.get(norm_address, []):
                add(rec)

        best_score = -1.0
        best: dict[str, Any] | None = None
        for rec in candidates:
            trade_match = bool(norm_name) and rec["trade_norm"] == norm_name
            legal_match = bool(norm_name) and rec["legal_norm"] == norm_name
            score = _score_pa_sales_tax(
                trade_match=trade_match,
                legal_match=legal_match,
                addr_exact=bool(norm_address) and rec["norm_address"] == norm_address,
                biz_lat=biz["lat"],
                biz_lng=biz["lng"],
                cand_lat=rec["lat"],
                cand_lng=rec["lng"],
                max_distance_miles=max_distance_miles,
            )
            if score > best_score:
                best_score = score
                best = rec

        if best is not None and best_score >= 0.7:
            matches[biz["gers_id"]] = best

    now = utc_now()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE businesses
            SET pa_sales_tax_status = NULL,
                pa_sales_tax_trade_name = NULL,
                pa_sales_tax_address = NULL,
                pa_sales_tax_license_type = NULL,
                pa_sales_tax_expiration = NULL,
                pa_sales_tax_checked_at = ?,
                updated_at = ?
            WHERE state = 'PA'
            """,
            (now, now),
        )
        conn.executemany(
            """
            UPDATE businesses
            SET pa_sales_tax_status = 'active',
                pa_sales_tax_trade_name = ?,
                pa_sales_tax_address = ?,
                pa_sales_tax_license_type = ?,
                pa_sales_tax_expiration = ?,
                pa_sales_tax_checked_at = ?,
                updated_at = ?
            WHERE gers_id = ?
            """,
            [
                (
                    m["trade_name"],
                    m["address"],
                    m["license_type"],
                    m["expiration_date"] or None,
                    now,
                    now,
                    gers_id,
                )
                for gers_id, m in matches.items()
            ],
        )

    update_license_rollup(db_path)
    stats = {
        "matched": len(matches),
        "unmatched": len(businesses) - len(matches),
        "total": len(businesses),
    }
    print(f"  Matched {stats['matched']:,} / {stats['total']:,}")
    return stats


def join_philly_cal(
    max_distance_miles: float = 0.5, db_path=DB_PATH
) -> dict[str, int]:
    """Match Philly CAL data using BLI premises addresses when available."""
    print("=" * 60)
    print("JOIN: Philadelphia Commercial Activity Licenses")
    print("=" * 60)

    if not PHILLY_CAL_PATH.exists():
        raise FileNotFoundError(
            f"Missing {PHILLY_CAL_PATH}. Run: python -m sources.licenses fetch-cal"
        )
    if not PHILLY_BLI_PATH.exists():
        raise FileNotFoundError(
            f"Missing {PHILLY_BLI_PATH}. Run: python -m sources.licenses fetch-philly-bli"
        )

    init_db(db_path)
    cal_rows = _load_csv_rows(PHILLY_CAL_PATH)
    bli_rows = _load_csv_rows(PHILLY_BLI_PATH)
    print(f"  Loaded {len(cal_rows):,} active CALs, {len(bli_rows):,} BLI records")

    by_cal = _build_bli_by_cal_number(bli_rows)

    enriched: list[dict[str, Any]] = []
    for row in cal_rows:
        company = (row.get("companyname") or "").strip()
        if not company:
            first = (row.get("legalfirstname") or "").strip()
            last = (row.get("legallastname") or "").strip()
            company = " ".join(p for p in (first, last) if p)
        norm_name = normalize_name(company)
        if not norm_name:
            continue

        licensenum = str(row.get("licensenum") or "")
        bli_hits = by_cal.get(licensenum, [])
        if bli_hits:
            premises = bli_hits[0]
            norm_address = premises["norm_address"]
            lat = premises["lat"]
            lng = premises["lng"]
        else:
            norm_address = normalize_address(row.get("ownercontact1mailingaddress"))
            lat = None
            lng = None

        enriched.append(
            {
                "key": licensenum or norm_name,
                "norm_name": norm_name,
                "norm_address": norm_address,
                "licensenum": licensenum,
                "lat": lat,
                "lng": lng,
            }
        )

    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_address: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in enriched:
        by_name[rec["norm_name"]].append(rec)
        if rec["norm_address"]:
            by_address[rec["norm_address"]].append(rec)

    with connect(db_path) as conn:
        businesses = conn.execute(
            """
            SELECT gers_id, name, address, lat, lng, city, county
            FROM businesses
            WHERE county = 'Philadelphia' OR city = 'Philadelphia'
            """
        ).fetchall()

    print(f"  Philadelphia businesses to match: {len(businesses):,}")
    matches: dict[str, dict[str, Any]] = {}

    for biz in tqdm(businesses, desc="Matching CAL"):
        norm_name = normalize_name(biz["name"])
        norm_address = normalize_address(biz["address"] or "")
        if not norm_name and not norm_address:
            continue

        best = _match_with_address_threshold(
            norm_name=norm_name,
            norm_address=norm_address,
            biz_lat=biz["lat"],
            biz_lng=biz["lng"],
            by_name=by_name,
            by_address=by_address,
            max_distance_miles=max_distance_miles,
        )
        if best is not None:
            matches[biz["gers_id"]] = best

    now = utc_now()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE businesses
            SET philly_cal_status = NULL,
                philly_cal_license_num = NULL,
                registration_checked_at = ?,
                updated_at = ?
            WHERE county = 'Philadelphia' OR city = 'Philadelphia'
            """,
            (now, now),
        )
        conn.executemany(
            """
            UPDATE businesses
            SET philly_cal_status = 'active',
                philly_cal_license_num = ?,
                registration_checked_at = ?,
                updated_at = ?
            WHERE gers_id = ?
            """,
            [
                (m["licensenum"], now, now, gers_id)
                for gers_id, m in matches.items()
            ],
        )

    update_license_rollup(db_path)
    stats = {
        "matched": len(matches),
        "unmatched": len(businesses) - len(matches),
        "total": len(businesses),
    }
    print(f"  Matched {stats['matched']:,} / {stats['total']:,}")
    return stats


def join_philly_bli(
    max_distance_miles: float = 0.5, db_path=DB_PATH
) -> dict[str, int]:
    """Match Philadelphia L&I business licenses to Philly businesses."""
    print("=" * 60)
    print("JOIN: Philadelphia L&I business licenses")
    print("=" * 60)

    if not PHILLY_BLI_PATH.exists():
        raise FileNotFoundError(
            f"Missing {PHILLY_BLI_PATH}. Run: python -m sources.licenses fetch-philly-bli"
        )

    init_db(db_path)
    rows = _load_csv_rows(PHILLY_BLI_PATH)
    print(f"  Loaded {len(rows):,} Philly BLI records")

    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_address: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        address = (row.get("address") or "").strip()
        rec = {
            "key": row.get("licensenum") or address,
            "norm_name": "",
            "norm_address": normalize_address(address),
            "license_type": row.get("licensetype") or "",
            "address": address,
            "lat": _float_or_none(row.get("lat")),
            "lng": _float_or_none(row.get("lng")),
        }
        names: set[str] = set()
        for raw in (row.get("business_name"), row.get("legalname")):
            norm = normalize_name(raw)
            if norm:
                names.add(norm)
        if not names and not rec["norm_address"]:
            continue
        for norm in names:
            rec_copy = {**rec, "norm_name": norm}
            by_name[norm].append(rec_copy)
        if rec["norm_address"]:
            by_address[rec["norm_address"]].append({**rec, "norm_name": next(iter(names), "")})

    with connect(db_path) as conn:
        businesses = conn.execute(
            """
            SELECT gers_id, name, address, lat, lng, city, county
            FROM businesses
            WHERE county = 'Philadelphia' OR city = 'Philadelphia'
            """
        ).fetchall()

    print(f"  Philadelphia businesses to match: {len(businesses):,}")
    matches: dict[str, dict[str, Any]] = {}

    for biz in tqdm(businesses, desc="Matching BLI"):
        norm_name = normalize_name(biz["name"])
        norm_address = normalize_address(biz["address"] or "")
        best = _match_with_address_threshold(
            norm_name=norm_name,
            norm_address=norm_address,
            biz_lat=biz["lat"],
            biz_lng=biz["lng"],
            by_name=by_name,
            by_address=by_address,
            max_distance_miles=max_distance_miles,
        )
        if best is not None:
            matches[biz["gers_id"]] = best

    now = utc_now()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE businesses
            SET philly_bli_status = NULL,
                philly_bli_license_type = NULL,
                philly_bli_address = NULL,
                philly_bli_checked_at = ?,
                updated_at = ?
            WHERE county = 'Philadelphia' OR city = 'Philadelphia'
            """,
            (now, now),
        )
        conn.executemany(
            """
            UPDATE businesses
            SET philly_bli_status = 'active',
                philly_bli_license_type = ?,
                philly_bli_address = ?,
                philly_bli_checked_at = ?,
                updated_at = ?
            WHERE gers_id = ?
            """,
            [
                (m["license_type"], m["address"], now, now, gers_id)
                for gers_id, m in matches.items()
            ],
        )

    update_license_rollup(db_path)
    stats = {
        "matched": len(matches),
        "unmatched": len(businesses) - len(matches),
        "total": len(businesses),
    }
    print(f"  Matched {stats['matched']:,} / {stats['total']:,}")
    return stats


def join_nppes(max_distance_miles: float = 0.5, db_path=DB_PATH) -> dict[str, int]:
    """Match NPPES healthcare providers to tristate businesses."""
    print("=" * 60)
    print("JOIN: NPPES NPI registry")
    print("=" * 60)

    if not NPPES_TRISTATE_PATH.exists():
        raise FileNotFoundError(
            f"Missing {NPPES_TRISTATE_PATH}. Run: python -m sources.licenses fetch-nppes"
        )

    init_db(db_path)
    rows = _load_csv_rows(NPPES_TRISTATE_PATH)
    print(f"  Loaded {len(rows):,} tristate NPPES records")

    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_address: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        address = " ".join(
            p
            for p in [
                (row.get("address_line1") or "").strip(),
                (row.get("address_line2") or "").strip(),
            ]
            if p
        )
        entity_type = row.get("entity_type") or ""
        names: set[str] = set()
        if entity_type == "2":
            for raw in (row.get("org_name"), row.get("other_org_name")):
                norm = normalize_name(raw)
                if norm:
                    names.add(norm)
        else:
            last = (row.get("provider_last_name") or "").strip()
            first = (row.get("provider_first_name") or "").strip()
            full = normalize_name(f"{first} {last}")
            if full:
                names.add(full)
            if last:
                names.add(normalize_name(last))

        rec = {
            "key": row.get("npi") or address,
            "norm_address": normalize_address(address),
            "npi": row.get("npi") or "",
            "org_name": row.get("org_name") or f"{row.get('provider_first_name', '')} {row.get('provider_last_name', '')}".strip(),
            "address": address,
            "taxonomy": row.get("taxonomy") or "",
            "entity_type": entity_type,
            "lat": None,
            "lng": None,
        }
        if not names and not rec["norm_address"]:
            continue
        for norm in names:
            by_name[norm].append({**rec, "norm_name": norm})
        if rec["norm_address"]:
            by_address[rec["norm_address"]].append(
                {**rec, "norm_name": next(iter(names), "")}
            )

    with connect(db_path) as conn:
        businesses = conn.execute(
            """
            SELECT b.gers_id, b.name, b.address, b.lat, b.lng, b.state,
                   t.revenue_tier, t.category_path
            FROM businesses b
            LEFT JOIN targets t ON t.business_id = b.gers_id
            WHERE b.state IN ('PA', 'NJ', 'DE')
            ORDER BY
                CASE WHEN t.category_path LIKE 'health_care%' THEN 0 ELSE 1 END,
                CASE WHEN t.revenue_tier = 'A' THEN 0
                     WHEN t.revenue_tier = 'B' THEN 1
                     ELSE 2 END,
                t.icp_score DESC NULLS LAST
            """
        ).fetchall()

    print(f"  Tristate businesses to match: {len(businesses):,}")
    matches: dict[str, dict[str, Any]] = {}

    for biz in tqdm(businesses, desc="Matching NPPES"):
        norm_name = normalize_name(biz["name"])
        norm_address = normalize_address(biz["address"] or "")
        best = _match_with_address_threshold(
            norm_name=norm_name,
            norm_address=norm_address,
            biz_lat=biz["lat"],
            biz_lng=biz["lng"],
            by_name=by_name,
            by_address=by_address,
            max_distance_miles=max_distance_miles,
        )
        if best is not None:
            matches[biz["gers_id"]] = best

    now = utc_now()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE businesses
            SET nppes_status = NULL,
                nppes_npi = NULL,
                nppes_org_name = NULL,
                nppes_address = NULL,
                nppes_taxonomy = NULL,
                nppes_entity_type = NULL,
                nppes_checked_at = ?,
                updated_at = ?
            WHERE state IN ('PA', 'NJ', 'DE')
            """,
            (now, now),
        )
        conn.executemany(
            """
            UPDATE businesses
            SET nppes_status = 'active',
                nppes_npi = ?,
                nppes_org_name = ?,
                nppes_address = ?,
                nppes_taxonomy = ?,
                nppes_entity_type = ?,
                nppes_checked_at = ?,
                updated_at = ?
            WHERE gers_id = ?
            """,
            [
                (
                    m["npi"],
                    m["org_name"],
                    m["address"],
                    m["taxonomy"],
                    m["entity_type"],
                    now,
                    now,
                    gers_id,
                )
                for gers_id, m in matches.items()
            ],
        )

    update_license_rollup(db_path)
    stats = {
        "matched": len(matches),
        "unmatched": len(businesses) - len(matches),
        "total": len(businesses),
    }
    print(f"  Matched {stats['matched']:,} / {stats['total']:,}")
    return stats


def join_de_licenses(max_distance_miles: float = 0.5, db_path=DB_PATH) -> dict[str, int]:
    """Match DE license data to Delaware businesses in DB."""
    print("=" * 60)
    print("JOIN: Delaware business licenses")
    print("=" * 60)

    if not DE_LICENSE_PATH.exists():
        raise FileNotFoundError(
            f"Missing {DE_LICENSE_PATH}. Run: python -m sources.licenses fetch-de"
        )

    init_db(db_path)
    today = date.today().isoformat()
    rows = _load_csv_rows(DE_LICENSE_PATH)

    current: list[dict[str, Any]] = []
    for row in rows:
        valid_to = (row.get("current_license_valid_to") or "").strip()
        if valid_to and valid_to < today:
            continue
        row_state = (row.get("state") or "").strip().upper()
        if row_state not in ("DE", "DELAWARE", ""):
            continue

        address = " ".join(
            p for p in [(row.get("address_1") or "").strip(), (row.get("address_2") or "").strip()] if p
        )
        rec = {
            "business_name": row.get("business_name") or "",
            "trade_name": row.get("trade_name") or "",
            "norm_names": set(),
            "norm_address": normalize_address(address),
            "license_number": str(row.get("license_number") or ""),
            "valid_to": valid_to,
            "lat": _float_or_none(row.get("lat")),
            "lng": _float_or_none(row.get("lng")),
        }
        for raw in (rec["business_name"], rec["trade_name"]):
            norm = normalize_name(raw)
            if norm:
                rec["norm_names"].add(norm)
        if rec["norm_names"]:
            current.append(rec)

    print(f"  Current DE licenses: {len(current):,} (of {len(rows):,} total)")

    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_address: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in current:
        for norm in rec["norm_names"]:
            by_name[norm].append(rec)
        if rec["norm_address"]:
            by_address[rec["norm_address"]].append(rec)

    with connect(db_path) as conn:
        businesses = conn.execute(
            """
            SELECT gers_id, name, address, lat, lng, state, city, county
            FROM businesses
            WHERE state = 'DE'
            """,
        ).fetchall()

    print(f"  DE-area businesses to match: {len(businesses):,}")
    matches: dict[str, dict[str, Any]] = {}

    for biz in tqdm(businesses, desc="Matching DE"):
        norm_name = normalize_name(biz["name"])
        norm_address = normalize_address(biz["address"] or "")
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(rec: dict[str, Any]) -> None:
            key = rec["license_number"] or "|".join(sorted(rec["norm_names"]))
            if key not in seen:
                seen.add(key)
                candidates.append(rec)

        if norm_name:
            for rec in by_name.get(norm_name, []):
                add(rec)
        if norm_address:
            for rec in by_address.get(norm_address, []):
                add(rec)

        best_score = -1.0
        best: dict[str, Any] | None = None
        for rec in candidates:
            score = _score_candidate(
                name_exact=bool(norm_name) and norm_name in rec["norm_names"],
                addr_exact=bool(norm_address) and rec["norm_address"] == norm_address,
                biz_lat=biz["lat"],
                biz_lng=biz["lng"],
                cand_lat=rec["lat"],
                cand_lng=rec["lng"],
                max_distance_miles=max_distance_miles,
            )
            if score > best_score:
                best_score = score
                best = rec

        if best is not None and best_score >= 0.8:
            matches[biz["gers_id"]] = best

    now = utc_now()
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE businesses
            SET de_license_status = NULL,
                de_license_number = NULL,
                de_license_valid_to = NULL,
                registration_checked_at = ?,
                updated_at = ?
            WHERE state = 'DE'
            """,
            (now, now),
        )
        conn.executemany(
            """
            UPDATE businesses
            SET de_license_status = 'active',
                de_license_number = ?,
                de_license_valid_to = ?,
                registration_checked_at = ?,
                updated_at = ?
            WHERE gers_id = ?
            """,
            [
                (m["license_number"], m["valid_to"] or None, now, now, gers_id)
                for gers_id, m in matches.items()
            ],
        )

    update_license_rollup(db_path)
    stats = {
        "matched": len(matches),
        "unmatched": len(businesses) - len(matches),
        "total": len(businesses),
    }
    print(f"  Matched {stats['matched']:,} / {stats['total']:,}")
    return stats


# ---------------------------------------------------------------------------
# NJ scrape
# ---------------------------------------------------------------------------


def _nj_search(session: requests.Session, business_name: str) -> list[dict[str, str]]:
    """POST a business-name search to the NJ portal and parse result rows."""
    page = _request_with_retry(session, "GET", NJ_SEARCH_URL)
    soup = BeautifulSoup(page.text, "html.parser")
    token_input = soup.find("input", {"name": "__RequestVerificationToken"})
    if token_input is None:
        raise RuntimeError("NJ portal: missing CSRF token")

    token = token_input.get("value") or ""
    resp = _request_with_retry(
        session,
        "POST",
        NJ_SEARCH_URL,
        data={
            "__RequestVerificationToken": token,
            "BusinessName": business_name,
        },
    )
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if table is None:
        return []

    headers = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
    results: list[dict[str, str]] = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if not cells:
            continue
        row = {
            headers[i] if i < len(headers) else f"col{i}": cells[i]
            for i in range(len(cells))
        }
        results.append(row)
    return results


def _nj_name_match(query_norm: str, result_name: str) -> bool:
    result_norm = normalize_name(result_name)
    if not query_norm or not result_norm:
        return False
    if query_norm == result_norm:
        return True
    # Allow containment when both sides are reasonably long
    if len(query_norm) >= 8 and len(result_norm) >= 8:
        if query_norm in result_norm or result_norm in query_norm:
            return True
    return False


def enrich_nj_registrations(
    limit: int = 500,
    tier: str | None = None,
    db_path=DB_PATH,
) -> dict[str, int]:
    """Search NJ portal for each NJ business in DB (rate-limited)."""
    print("=" * 60)
    print("ENRICH: NJ Division of Revenue business search")
    print("=" * 60)

    init_db(db_path)
    params: list[Any] = []
    tier_clause = ""
    if tier:
        tier_clause = "AND t.revenue_tier = ?"
        params.append(tier.upper())
    params.append(limit)

    with connect(db_path) as conn:
        businesses = conn.execute(
            f"""
            SELECT b.gers_id, b.name, t.icp_score, t.revenue_tier
            FROM businesses b
            LEFT JOIN targets t ON t.business_id = b.gers_id
            WHERE b.state = 'NJ'
              AND b.nj_registration_status IS NULL
              AND b.registration_checked_at IS NULL
              {tier_clause}
            ORDER BY
                CASE WHEN t.revenue_tier = 'A' THEN 0
                     WHEN t.revenue_tier = 'B' THEN 1
                     WHEN t.revenue_tier = 'C' THEN 2
                     ELSE 3 END,
                t.icp_score DESC NULLS LAST,
                b.name ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    print(f"  Searching {len(businesses):,} NJ businesses (delay={NJ_REQUEST_DELAY}s)")
    session = _session()
    matched = 0
    not_found = 0
    errors = 0
    consecutive_errors = 0
    now = utc_now()

    for biz in tqdm(businesses, desc="NJ portal"):
        gers_id = biz["gers_id"]
        raw_name = biz["name"] or ""
        search_name = normalize_name(raw_name) or raw_name.strip()
        if len(search_name) < 3:
            not_found += 1
            with connect(db_path) as conn:
                conn.execute(
                    """
                    UPDATE businesses
                    SET registration_checked_at = ?, updated_at = ?
                    WHERE gers_id = ?
                    """,
                    (now, now, gers_id),
                )
            continue

        try:
            results = _nj_search(session, search_name)
            query_norm = normalize_name(raw_name)
            hit = False
            for result in results:
                result_name = (
                    result.get("business name")
                    or result.get("businessname")
                    or result.get("name")
                    or next(iter(result.values()), "")
                )
                if _nj_name_match(query_norm, result_name):
                    hit = True
                    break

            with connect(db_path) as conn:
                if hit:
                    conn.execute(
                        """
                        UPDATE businesses
                        SET nj_registration_status = 'registered',
                            registration_checked_at = ?,
                            updated_at = ?
                        WHERE gers_id = ?
                        """,
                        (now, now, gers_id),
                    )
                    matched += 1
                else:
                    conn.execute(
                        """
                        UPDATE businesses
                        SET registration_checked_at = ?,
                            updated_at = ?
                        WHERE gers_id = ?
                        """,
                        (now, now, gers_id),
                    )
                    not_found += 1
            consecutive_errors = 0
        except Exception as exc:
            errors += 1
            consecutive_errors += 1
            print(f"  Error for {raw_name!r}: {exc}")
            with connect(db_path) as conn:
                conn.execute(
                    """
                    UPDATE businesses
                    SET registration_checked_at = ?, updated_at = ?
                    WHERE gers_id = ?
                    """,
                    (now, now, gers_id),
                )
            if consecutive_errors >= 5:
                print("  5 consecutive errors — pausing 60s")
                time.sleep(60)
                consecutive_errors = 0

        time.sleep(NJ_REQUEST_DELAY)

    update_license_rollup(db_path)
    stats = {
        "matched": matched,
        "not_found": not_found,
        "errors": errors,
        "total": len(businesses),
    }
    print(
        f"  NJ: matched={matched:,} not_found={not_found:,} "
        f"errors={errors:,} total={stats['total']:,}"
    )
    return stats


# ---------------------------------------------------------------------------
# Stats / orchestration
# ---------------------------------------------------------------------------


def print_stats(db_path=DB_PATH) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
        pa_total = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE state = 'PA'"
        ).fetchone()[0]
        philly_total = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE county = 'Philadelphia' OR city = 'Philadelphia'"
        ).fetchone()[0]
        nj_total = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE state = 'NJ'"
        ).fetchone()[0]
        de_total = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE state = 'DE'"
        ).fetchone()[0]

        pa_matched = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE pa_registration_status = 'registered'"
        ).fetchone()[0]
        pa_tax_matched = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE pa_sales_tax_status = 'active'"
        ).fetchone()[0]
        cal_matched = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE philly_cal_status = 'active'"
        ).fetchone()[0]
        bli_matched = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE philly_bli_status = 'active'"
        ).fetchone()[0]
        nppes_matched = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE nppes_status = 'active'"
        ).fetchone()[0]
        nj_matched = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE nj_registration_status = 'registered'"
        ).fetchone()[0]
        de_matched = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE de_license_status = 'active'"
        ).fetchone()[0]
        any_license = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE has_active_license = 1"
        ).fetchone()[0]
        nj_licensed = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE state = 'NJ' AND has_active_license = 1"
        ).fetchone()[0]

        tier_a_licensed = conn.execute(
            """
            SELECT COUNT(*) FROM businesses b
            JOIN targets t ON t.business_id = b.gers_id
            WHERE b.has_active_license = 1 AND t.revenue_tier = 'A'
            """
        ).fetchone()[0]

    def pct(n: int, d: int) -> str:
        return f"{(100.0 * n / d):.1f}%" if d else "n/a"

    print("=" * 60)
    print("LICENSE ENRICHMENT STATS")
    print("=" * 60)
    print(f"PA Registration matches:  {pa_matched:>7,} / {pa_total:>7,} ({pct(pa_matched, pa_total)})")
    print(f"PA Sales Tax matches:     {pa_tax_matched:>7,} / {pa_total:>7,} ({pct(pa_tax_matched, pa_total)})")
    print(f"Philly CAL matches:       {cal_matched:>7,} / {philly_total:>7,} ({pct(cal_matched, philly_total)})   [Philly only]")
    print(f"Philly BLI matches:       {bli_matched:>7,} / {philly_total:>7,} ({pct(bli_matched, philly_total)})   [Philly only]")
    print(f"NPPES matches:            {nppes_matched:>7,} / {total:>7,} ({pct(nppes_matched, total)})      [tristate]")
    print(f"DE License matches:       {de_matched:>7,} / {de_total:>7,} ({pct(de_matched, de_total)})     [DE only]")
    print(f"NJ Registration matches:  {nj_matched:>7,} / {nj_total:>7,} ({pct(nj_matched, nj_total)})     [NJ only]")
    print(f"NJ with any license:      {nj_licensed:>7,} / {nj_total:>7,} ({pct(nj_licensed, nj_total)})     [NJ rollup]")
    print(f"Total with any license:   {any_license:>7,} / {total:>7,} ({pct(any_license, total)})")
    print(f"Tier A with license:      {tier_a_licensed:>7,}")


def run_all(
    skip_nj: bool = False,
    force_fetch: bool = False,
    nj_limit: int = 500,
    nj_tier: str | None = None,
) -> None:
    """Run fetch + join for all license sources, optionally NJ scrape."""
    fetch_pa_registrations(force=force_fetch)
    fetch_pa_sales_tax(force=force_fetch)
    fetch_philly_cal(force=force_fetch)
    fetch_philly_bli(force=force_fetch)
    fetch_de_licenses(force=force_fetch)
    fetch_nppes(force=force_fetch)

    pa_result = join_pa_registrations()
    print(f"PA DOS: {pa_result['matched']} matched / {pa_result['total']} total")

    pa_tax_result = join_pa_sales_tax()
    print(
        f"PA Tax: {pa_tax_result['matched']} matched / {pa_tax_result['total']} total"
    )

    bli_result = join_philly_bli()
    print(f"BLI: {bli_result['matched']} matched / {bli_result['total']} total")

    cal_result = join_philly_cal()
    print(f"CAL: {cal_result['matched']} matched / {cal_result['total']} total")

    de_result = join_de_licenses()
    print(f"DE: {de_result['matched']} matched / {de_result['total']} total")

    nppes_result = join_nppes()
    print(f"NPPES: {nppes_result['matched']} matched / {nppes_result['total']} total")

    if not skip_nj:
        nj_result = enrich_nj_registrations(limit=nj_limit, tier=nj_tier)
        print(f"NJ: {nj_result['matched']} matched / {nj_result['total']} total")

    update_license_rollup()
    print_stats()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="License / registration enrichment")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("fetch-pa", "Download PA DOS registrations"),
        ("fetch-pa-tax", "Download PA Sales Tax licenses"),
        ("fetch-cal", "Download Philly CAL licenses"),
        ("fetch-philly-bli", "Download Philly L&I business licenses"),
        ("fetch-de", "Download DE business licenses"),
        ("fetch-nppes", "Download NPPES NPI registry (large)"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--force", action="store_true")

    p = sub.add_parser("join-pa", help="Match PA registrations to businesses")
    p.add_argument("--max-distance", type=float, default=0.5)

    p = sub.add_parser("join-pa-tax", help="Match PA Sales Tax to businesses")
    p.add_argument("--max-distance", type=float, default=0.5)

    p = sub.add_parser("join-cal", help="Match Philly CAL to businesses")
    p.add_argument("--max-distance", type=float, default=0.5)

    p = sub.add_parser("join-philly-bli", help="Match Philly BLI to businesses")
    p.add_argument("--max-distance", type=float, default=0.5)

    p = sub.add_parser("join-nppes", help="Match NPPES to businesses")
    p.add_argument("--max-distance", type=float, default=0.5)

    p = sub.add_parser("join-de", help="Match DE licenses to businesses")
    p.add_argument("--max-distance", type=float, default=0.5)

    p = sub.add_parser("enrich-nj", help="Scrape NJ portal (slow)")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--tier", default=None, help="Limit to revenue tier (A/B/C)")

    p = sub.add_parser("run", help="Fetch + join all sources")
    p.add_argument("--skip-nj", action="store_true")
    p.add_argument("--force", action="store_true", dest="force_fetch")
    p.add_argument("--nj-limit", type=int, default=500)
    p.add_argument("--nj-tier", default=None)

    sub.add_parser("stats", help="Print match statistics")
    sub.add_parser("rollup", help="Recompute has_active_license rollup")

    args = parser.parse_args(argv)

    if args.command == "fetch-pa":
        fetch_pa_registrations(force=args.force)
    elif args.command == "fetch-pa-tax":
        fetch_pa_sales_tax(force=args.force)
    elif args.command == "fetch-cal":
        fetch_philly_cal(force=args.force)
    elif args.command == "fetch-philly-bli":
        fetch_philly_bli(force=args.force)
    elif args.command == "fetch-de":
        fetch_de_licenses(force=args.force)
    elif args.command == "fetch-nppes":
        fetch_nppes(force=args.force)
    elif args.command == "join-pa":
        join_pa_registrations(max_distance_miles=args.max_distance)
    elif args.command == "join-pa-tax":
        join_pa_sales_tax(max_distance_miles=args.max_distance)
    elif args.command == "join-cal":
        join_philly_cal(max_distance_miles=args.max_distance)
    elif args.command == "join-philly-bli":
        join_philly_bli(max_distance_miles=args.max_distance)
    elif args.command == "join-nppes":
        join_nppes(max_distance_miles=args.max_distance)
    elif args.command == "join-de":
        join_de_licenses(max_distance_miles=args.max_distance)
    elif args.command == "enrich-nj":
        enrich_nj_registrations(limit=args.limit, tier=args.tier)
    elif args.command == "run":
        run_all(
            skip_nj=args.skip_nj,
            force_fetch=args.force_fetch,
            nj_limit=args.nj_limit,
            nj_tier=args.nj_tier,
        )
    elif args.command == "stats":
        print_stats()
    elif args.command == "rollup":
        result = update_license_rollup()
        print(result)
        print_stats()


if __name__ == "__main__":
    main()
