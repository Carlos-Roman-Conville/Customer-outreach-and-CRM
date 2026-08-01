"""
Email verification: syntax, MX lookup, role-account flagging.
"""
from __future__ import annotations

import re
from typing import Optional

import dns.exception
import dns.resolver
from tqdm import tqdm

from config import EMAIL_PATTERN, SENDABLE_VERIFY_STATUSES
from db import DB_PATH, connect, init_db, utc_now

ROLE_LOCAL_PARTS = {
    "info", "contact", "hello", "support", "sales", "admin", "office",
    "team", "service", "help", "billing", "marketing", "hr", "jobs",
    "careers", "noreply", "no-reply",
}

VERIFY_BATCH_SIZE = 500


def is_valid_syntax(email: str) -> bool:
    return bool(re.fullmatch(EMAIL_PATTERN, email))


def is_role_account(email: str) -> bool:
    local = email.split("@", 1)[0].lower()
    return local in ROLE_LOCAL_PARTS


def mx_exists(domain: str, cache: dict[str, tuple[bool, Optional[str]]]) -> tuple[bool, Optional[str]]:
    if domain in cache:
        return cache[domain]

    try:
        answers = dns.resolver.resolve(domain, "MX")
        result = (bool(answers), None if answers else "no_mx")
    except dns.resolver.NXDOMAIN:
        result = (False, "nxdomain")
    except dns.resolver.NoAnswer:
        result = (False, "no_mx")
    except dns.exception.DNSException as exc:
        result = (False, f"dns_error:{exc.__class__.__name__}")

    cache[domain] = result
    return result


def verify_email(email: str, mx_cache: dict[str, tuple[bool, Optional[str]]] | None = None) -> str:
    cache = mx_cache if mx_cache is not None else {}
    email = email.strip().lower()
    if not is_valid_syntax(email):
        return "invalid_syntax"
    domain = email.split("@", 1)[1]
    ok, reason = mx_exists(domain, cache)
    if not ok:
        return reason or "no_mx"
    if is_role_account(email):
        return "role_ok"
    return "valid"


def verification_summary(db_path=DB_PATH) -> dict[str, int]:
    init_db(db_path)
    with connect(db_path) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM contacts WHERE kind = 'email'"
        ).fetchone()[0]
        verified = conn.execute(
            """
            SELECT COUNT(*) FROM contacts
            WHERE kind = 'email' AND verify_status IS NOT NULL AND verify_status != 'pending'
            """
        ).fetchone()[0]
        sendable = conn.execute(
            f"""
            SELECT COUNT(*) FROM contacts
            WHERE kind = 'email'
              AND verify_status IN ({",".join("?" * len(SENDABLE_VERIFY_STATUSES))})
            """,
            SENDABLE_VERIFY_STATUSES,
        ).fetchone()[0]
    return {
        "total": int(total),
        "verified": int(verified),
        "unverified": int(total - verified),
        "sendable": int(sendable),
    }


def verify_emails(db_path=DB_PATH, limit: int | None = None) -> dict[str, int]:
    print("=" * 60)
    print("VERIFY: Email addresses")
    print("=" * 60)

    init_db(db_path)
    stats: dict[str, int] = {}
    mx_cache: dict[str, tuple[bool, Optional[str]]] = {}

    with connect(db_path) as conn:
        sql = """
            SELECT id, value FROM contacts
            WHERE kind = 'email'
              AND (verify_status IS NULL OR verify_status = 'pending')
            ORDER BY id
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = conn.execute(sql).fetchall()
        print(f"  Emails to verify: {len(rows):,}")

        now = utc_now()
        pending_updates: list[tuple[str, str, str, int]] = []

        for row in tqdm(rows, desc="Verifying"):
            status = verify_email(row["value"], mx_cache=mx_cache)
            stats[status] = stats.get(status, 0) + 1
            pending_updates.append((status, now, now, row["id"]))

            if len(pending_updates) >= VERIFY_BATCH_SIZE:
                conn.executemany(
                    """
                    UPDATE contacts
                    SET verify_status = ?, verified_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    pending_updates,
                )
                pending_updates.clear()

        if pending_updates:
            conn.executemany(
                """
                UPDATE contacts
                SET verify_status = ?, verified_at = ?, updated_at = ?
                WHERE id = ?
                """,
                pending_updates,
            )

    print("\n  Verification results:")
    for status, count in sorted(stats.items(), key=lambda item: (-item[1], item[0])):
        print(f"    {status}: {count:,}")

    summary = verification_summary(db_path=db_path)
    print(f"\n  Total emails: {summary['total']:,}")
    print(f"  Verified: {summary['verified']:,}")
    print(f"  Still unverified: {summary['unverified']:,}")
    print(f"  Sendable (valid/role_ok/deliverable): {summary['sendable']:,}")

    if summary["unverified"] > 0:
        print("\n  Run `python pipeline.py verify` until unverified reaches 0 before exporting email batches.")

    print("\n  Hook: plug a paid verifier here (MillionVerifier, NeverBounce, etc.)")
    print("        before sending to production lists.")
    return stats


def run_paid_verifier_hook(db_path=DB_PATH) -> None:
    """
    Placeholder for a paid bulk verifier integration.

    Example:
        - Export contacts WHERE verify_status IN ('valid', 'role_ok')
        - Upload to provider API
        - Write back verify_status = 'deliverable' / 'undeliverable'
    """
    raise NotImplementedError(
        "Paid verifier hook not configured. Set HUNTER_API_KEY or integrate your provider."
    )


if __name__ == "__main__":
    verify_emails()
