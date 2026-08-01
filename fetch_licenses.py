"""
Step 1: Fetch ALL Philadelphia business licenses from OpenDataPhilly.
Uses the CARTO SQL API — no API key required.
Returns business name, address, type, status, and coordinates.
"""
import requests
import pandas as pd
from config import CARTO_API, DATA_DIR, REQUEST_TIMEOUT


def fetch_all_licenses():
    """Pull every business license in Philadelphia."""
    print("=" * 60)
    print("STEP 1: Fetching ALL Philadelphia business licenses")
    print("=" * 60)

    query = """
    SELECT
        licensenum,
        business_name,
        address,
        zip,
        licensetype,
        licensestatus,
        initialissuedate,
        mostrecentissuedate,
        expirationdate,
        inactivedate,
        censustract,
        ST_Y(the_geom) AS lat,
        ST_X(the_geom) AS lng
    FROM business_licenses
    ORDER BY business_name
    """

    all_rows = []
    offset = 0
    page_size = 10000

    while True:
        paged = f"{query} LIMIT {page_size} OFFSET {offset}"
        resp = requests.get(
            CARTO_API,
            params={"q": paged, "format": "json"},
            timeout=REQUEST_TIMEOUT * 4,
        )
        resp.raise_for_status()
        rows = resp.json().get("rows", [])

        if not rows:
            break

        all_rows.extend(rows)
        print(f"  Fetched {len(all_rows):,} records...")
        offset += page_size

        if len(rows) < page_size:
            break

    df = pd.DataFrame(all_rows)

    for col in ["initialissuedate", "mostrecentissuedate", "expirationdate", "inactivedate"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    df["is_active"] = df["licensestatus"] == "Active"

    # Drop businesses with no name or address
    before = len(df)
    df = df.dropna(subset=["business_name", "address"])
    df = df[df["business_name"].str.strip() != ""]
    print(f"  Dropped {before - len(df):,} records with missing name/address")

    # Deduplicate: same business name + address = same business
    df["_dedup_key"] = (
        df["business_name"].str.upper().str.strip()
        + "|"
        + df["address"].str.upper().str.strip()
    )
    before = len(df)
    df = df.sort_values("mostrecentissuedate", ascending=False)
    df = df.drop_duplicates(subset="_dedup_key", keep="first")
    df = df.drop(columns=["_dedup_key"])
    print(f"  Deduplicated: {before:,} -> {len(df):,} unique businesses")

    out_path = DATA_DIR / "all_licenses.csv"
    df.to_csv(out_path, index=False)

    active = df["is_active"].sum()
    with_coords = df["lat"].notna().sum()
    license_types = df["licensetype"].nunique()

    print(f"\nSaved {len(df):,} businesses to {out_path}")
    print(f"  Active: {active:,}")
    print(f"  With coordinates: {with_coords:,}")
    print(f"  License types: {license_types}")
    print(f"\nTop 10 license types:")
    for ltype, count in df["licensetype"].value_counts().head(10).items():
        print(f"    {count:>6,}  {ltype}")

    return df


def load_licenses():
    """Load previously fetched licenses from CSV."""
    path = DATA_DIR / "all_licenses.csv"
    if not path.exists():
        raise FileNotFoundError(f"Run fetch_all_licenses() first. Missing: {path}")
    return pd.read_csv(path)


if __name__ == "__main__":
    fetch_all_licenses()
