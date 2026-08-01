"""Background job runner for enrichment and verification."""
from __future__ import annotations

import json
import threading
import time
from typing import Callable

from db import connect, utc_now

_lock = threading.Lock()
_active_job_id: int | None = None


def _update_job(job_id: int, **fields) -> None:
    fields["updated_at"] = utc_now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    with connect() as conn:
        conn.execute(
            f"UPDATE jobs SET {assignments} WHERE id = ?",
            [*fields.values(), job_id],
        )


def _run_job(job_id: int, kind: str, fn: Callable, limit: int | None) -> None:
    global _active_job_id
    try:
        _update_job(job_id, status="running", progress=0.0, message=f"Starting {kind}...", started_at=utc_now())
        result = fn(limit=limit) if limit else fn()
        _update_job(
            job_id,
            status="completed",
            progress=100.0,
            message=json.dumps(result)[:500],
            finished_at=utc_now(),
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            progress=0.0,
            message=str(exc)[:500],
            finished_at=utc_now(),
        )
    finally:
        with _lock:
            if _active_job_id == job_id:
                _active_job_id = None


def start_job(kind: str, limit: int | None = None) -> dict:
    global _active_job_id
    with _lock:
        if _active_job_id is not None:
            return {"job_id": _active_job_id, "status": "running", "message": "Job already running"}

        now = utc_now()
        with connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO jobs (kind, status, progress, message, created_at, updated_at)
                VALUES (?, 'pending', 0, ?, ?, ?)
                """,
                (kind, f"Queued {kind}", now, now),
            )
            job_id = int(cur.lastrowid)
        _active_job_id = job_id

    if kind == "enrich":
        from enrich import enrich_emails
        target = enrich_emails
    elif kind == "verify":
        from verify import verify_emails
        target = verify_emails
    else:
        raise ValueError(f"Unknown job kind: {kind}")

    thread = threading.Thread(target=_run_job, args=(job_id, kind, target, limit), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "pending", "kind": kind}


def latest_job() -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_job(job_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def enrichment_progress() -> dict:
    with connect() as conn:
        emails_total = conn.execute(
            "SELECT COUNT(*) FROM contacts WHERE kind = 'email'"
        ).fetchone()[0]
        emails_verified = conn.execute(
            """
            SELECT COUNT(*) FROM contacts
            WHERE kind = 'email' AND verify_status IS NOT NULL AND verify_status != 'pending'
            """
        ).fetchone()[0]
        websites = conn.execute(
            "SELECT COUNT(*) FROM contacts WHERE kind = 'website'"
        ).fetchone()[0]
        with_email = conn.execute(
            """
            SELECT COUNT(DISTINCT business_id) FROM contacts WHERE kind = 'email'
            """
        ).fetchone()[0]
        total_biz = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]

    job = latest_job()
    return {
        "emails_found": int(with_email),
        "emails_total_contacts": int(emails_total),
        "emails_verified": int(emails_verified),
        "websites_discovered": int(websites),
        "businesses_total": int(total_biz),
        "verification_pct": round(emails_verified / emails_total * 100, 1) if emails_total else 0,
        "latest_job": job,
    }


def job_stream_sleep(job_id: int, timeout_sec: int = 3600):
    """Generator for SSE job updates."""
    start = time.time()
    last_status = None
    while time.time() - start < timeout_sec:
        job = get_job(job_id)
        if not job:
            yield {"event": "error", "data": {"message": "Job not found"}}
            break
        payload = {
            "id": job["id"],
            "kind": job["kind"],
            "status": job["status"],
            "progress": job["progress"],
            "message": job["message"],
        }
        if job["status"] != last_status:
            yield {"event": "progress", "data": payload}
            last_status = job["status"]
        if job["status"] in {"completed", "failed"}:
            yield {"event": "done", "data": payload}
            break
        yield {"event": "progress", "data": payload}
        time.sleep(1)
