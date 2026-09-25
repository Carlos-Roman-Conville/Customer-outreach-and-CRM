"""
Philadelphia Business Outreach Pipeline
========================================
Overture-first, SQLite-backed pipeline with call queue and email cadence.

Usage:
    python pipeline.py pull              # Overture POI pull
    python pipeline.py join              # License enrichment (PA + CAL + DE)
    python pipeline.py enrich-licenses   # Full license enrichment pipeline
    python pipeline.py score             # ICP scoring
    python pipeline.py queue show        # Daily call queue
    python call_queue.py log <id> ...    # Record disposition
    python pipeline.py enrich            # Email waterfall
    python pipeline.py verify            # Required before any email export
    python pipeline.py signals           # Scan websites for booking software
    python pipeline.py places            # Fetch Google Places ratings (Tier A)
    python pipeline.py campaign assign   # Weekly batches (excludes non-targets)
    python pipeline.py campaign schedule # Mon/Wed/Fri cadence
    python pipeline.py export            # Blocked until verify completes
    python pipeline.py run-core          # pull + join + score (dial-ready)
"""
from __future__ import annotations

import argparse
import sys

from campaign import assign_batches, schedule_cadence
from enrich import enrich_emails
from export import export_active_batches
from icp import score_targets
from call_queue import show_queue
from sources.licenses import run_all as enrich_licenses
from sources.overture import pull_overture
from verify import verify_emails
from signals import scan_business_sites
from sources.places import fetch_places_data


def run_core(skip_nj: bool = True, force_fetch: bool = False) -> None:
    pull_overture()
    enrich_licenses(skip_nj=skip_nj, force_fetch=force_fetch)
    score_targets()
    print("\nCore pipeline complete. Start dialing:")
    print("  python pipeline.py queue show")
    print("  python call_queue.py log <gers_id> connected --notes \"...\" ")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Philadelphia Business Outreach Pipeline")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("pull", help="Pull Overture places into SQLite")
    join_parser = sub.add_parser(
        "join", help="License enrichment (PA + Philly CAL + DE; skips NJ)"
    )
    join_parser.add_argument("--force", action="store_true", dest="force_fetch")
    licenses_parser = sub.add_parser(
        "enrich-licenses", help="Full license enrichment pipeline"
    )
    licenses_parser.add_argument("--skip-nj", action="store_true", default=False)
    licenses_parser.add_argument("--force", action="store_true", dest="force_fetch")
    licenses_parser.add_argument("--nj-limit", type=int, default=500)
    licenses_parser.add_argument("--nj-tier", default=None)
    sub.add_parser("score", help="Score ICP targets")
    core_parser = sub.add_parser("run-core", help="pull + license enrich + score")
    core_parser.add_argument("--force", action="store_true", dest="force_fetch")
    core_parser.add_argument(
        "--with-nj",
        action="store_true",
        help="Also scrape NJ registrations (slow)",
    )

    queue_parser = sub.add_parser("queue", help="Call queue commands")
    queue_sub = queue_parser.add_subparsers(dest="queue_cmd")
    show_parser = queue_sub.add_parser("show", help="Show call queue")
    show_parser.add_argument("--limit", type=int, default=40)

    enrich_parser = sub.add_parser("enrich", help="Run email enrichment waterfall")
    enrich_parser.add_argument("--limit", type=int, default=None)

    verify_parser = sub.add_parser("verify", help="Verify scraped emails")
    verify_parser.add_argument("--limit", type=int, default=None)

    signals_parser = sub.add_parser("signals", help="Scan websites for booking software")
    signals_parser.add_argument("--limit", type=int, default=None)
    signals_parser.add_argument("--rescan-days", type=int, default=90)
    signals_parser.add_argument(
        "--queue-only",
        action="store_true",
        help="Only scan businesses currently in the call queue",
    )

    places_parser = sub.add_parser("places", help="Fetch Google Places ratings for Tier A leads")
    places_parser.add_argument("--limit", type=int, default=500)
    places_parser.add_argument("--refresh-days", type=int, default=None)

    campaign_parser = sub.add_parser("campaign", help="Campaign scheduling")
    campaign_sub = campaign_parser.add_subparsers(dest="campaign_cmd")
    assign_parser = campaign_sub.add_parser("assign", help="Assign weekly batches")
    assign_parser.add_argument("--batch-size", type=int, default=200)
    schedule_parser = campaign_sub.add_parser("schedule", help="Schedule cadence touches")
    schedule_parser.add_argument("--batch-id", default=None)

    export_parser = sub.add_parser("export", help="Export email batches and call sheets")
    export_parser.add_argument("--batch-id", action="append", default=None)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "pull":
        pull_overture()
    elif args.command == "join":
        enrich_licenses(skip_nj=True, force_fetch=args.force_fetch)
    elif args.command == "enrich-licenses":
        enrich_licenses(
            skip_nj=args.skip_nj,
            force_fetch=args.force_fetch,
            nj_limit=args.nj_limit,
            nj_tier=args.nj_tier,
        )
    elif args.command == "score":
        score_targets()
    elif args.command == "run-core":
        run_core(skip_nj=not args.with_nj, force_fetch=args.force_fetch)
    elif args.command == "queue":
        if args.queue_cmd == "show":
            show_queue(limit=args.limit)
        else:
            queue_parser.print_help()
    elif args.command == "enrich":
        enrich_emails(limit=args.limit)
    elif args.command == "verify":
        verify_emails(limit=args.limit)
    elif args.command == "signals":
        result = scan_business_sites(
            limit=args.limit,
            rescan_days=args.rescan_days,
            queue_only=args.queue_only,
        )
        print(result)
    elif args.command == "places":
        result = fetch_places_data(limit=args.limit, refresh_days=args.refresh_days)
        print(result)
    elif args.command == "campaign":
        if args.campaign_cmd == "assign":
            assign_batches(batch_size=args.batch_size)
        elif args.campaign_cmd == "schedule":
            schedule_cadence(batch_id=args.batch_id)
        else:
            campaign_parser.print_help()
    elif args.command == "export":
        export_active_batches(batch_ids=args.batch_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
