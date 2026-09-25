"""One-time reset of scan data for signal overhaul v3."""
from __future__ import annotations

import argparse
import sys

from db import DB_PATH, connect, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset signal scan data")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt (for non-interactive runs)",
    )
    args = parser.parse_args()

    init_db()
    with connect(DB_PATH) as conn:
        signals = conn.execute("SELECT COUNT(*) FROM business_signals").fetchone()[0]
        scanned = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE site_scanned_at IS NOT NULL"
        ).fetchone()[0]

        print(f"Will delete {signals:,} old signal rows")
        print(f"Will reset site_scanned_at on {scanned:,} businesses")
        print("Will clear booking_platform, site_phone, site_address, site_hours, site_structured_data")

        if not args.yes:
            confirm = input("Proceed? (yes/no): ")
            if confirm.strip().lower() != "yes":
                print("Aborted.")
                sys.exit(0)

        conn.execute("DELETE FROM business_signals")
        conn.execute(
            """
            UPDATE businesses SET
                site_scanned_at = NULL,
                booking_platform = NULL,
                site_phone = NULL,
                site_address = NULL,
                site_hours = NULL,
                site_structured_data = NULL
            """
        )
        print("Done. Run `python signals.py --queue-only` to re-scan queue leads first.")


if __name__ == "__main__":
    main()
