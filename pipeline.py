"""
Philadelphia Business Outreach Pipeline
========================================
Overture-first, SQLite-backed pipeline with call queue and email cadence.

Usage:
    python pipeline.py pull              # Overture POI pull
    python pipeline.py join              # Match Philly licenses
    python pipeline.py score             # ICP scoring
    python pipeline.py queue show        # Daily call queue
    python call_queue.py log <id> ...    # Record disposition
    python pipeline.py enrich            # Email waterfall
    python pipeline.py verify            # Required before any email export
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
from sources.license_join import join_licenses
from sources.overture import pull_overture
from verify import verify_emails


def run_core() -> None:
    pull_overture()
    join_licenses()
    score_targets()
    print("\nCore pipeline complete. Start dialing:")
    print("  python pipeline.py queue show")
    print("  python call_queue.py log <gers_id> connected --notes \"...\" ")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Philadelphia Business Outreach Pipeline")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("pull", help="Pull Overture places into SQLite")
    sub.add_parser("join", help="Join Philadelphia business licenses")
    sub.add_parser("score", help="Score ICP targets")
    sub.add_parser("run-core", help="pull + join + score")

    queue_parser = sub.add_parser("queue", help="Call queue commands")
    queue_sub = queue_parser.add_subparsers(dest="queue_cmd")
    show_parser = queue_sub.add_parser("show", help="Show call queue")
    show_parser.add_argument("--limit", type=int, default=40)

    enrich_parser = sub.add_parser("enrich", help="Run email enrichment waterfall")
    enrich_parser.add_argument("--limit", type=int, default=None)

    verify_parser = sub.add_parser("verify", help="Verify scraped emails")
    verify_parser.add_argument("--limit", type=int, default=None)

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
        join_licenses()
    elif args.command == "score":
        score_targets()
    elif args.command == "run-core":
        run_core()
    elif args.command == "queue":
        if args.queue_cmd == "show":
            show_queue(limit=args.limit)
        else:
            queue_parser.print_help()
    elif args.command == "enrich":
        enrich_emails(limit=args.limit)
    elif args.command == "verify":
        verify_emails(limit=args.limit)
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
