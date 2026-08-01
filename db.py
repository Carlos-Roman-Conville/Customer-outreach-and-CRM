"""
SQLite persistence for the outreach pipeline and CRM.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from config import DATA_DIR

DB_PATH = DATA_DIR / "outreach.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    gers_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    basic_category TEXT,
    taxonomy TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    zip TEXT,
    county TEXT,
    lat REAL,
    lng REAL,
    confidence REAL,
    website TEXT,
    has_active_license INTEGER NOT NULL DEFAULT 0,
    name_frequency INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('email', 'phone', 'website')),
    value TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL,
    verify_status TEXT,
    verified_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (business_id, kind, value),
    FOREIGN KEY (business_id) REFERENCES businesses(gers_id)
);

CREATE TABLE IF NOT EXISTS targets (
    business_id TEXT PRIMARY KEY,
    segment TEXT,
    icp_score REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'working', 'meeting', 'won', 'dead')),
    do_not_contact INTEGER NOT NULL DEFAULT 0,
    batch_id TEXT,
    owner_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (business_id) REFERENCES businesses(gers_id)
);

CREATE TABLE IF NOT EXISTS touches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('email', 'call')),
    step INTEGER NOT NULL DEFAULT 1,
    scheduled_for TEXT,
    completed_at TEXT,
    disposition TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (business_id) REFERENCES businesses(gers_id)
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'owner' CHECK (role IN ('owner', 'caller')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    changed_by INTEGER,
    changed_at TEXT NOT NULL,
    FOREIGN KEY (business_id) REFERENCES businesses(gers_id),
    FOREIGN KEY (changed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id TEXT NOT NULL UNIQUE,
    value REAL NOT NULL DEFAULT 2500,
    probability REAL NOT NULL DEFAULT 0.2,
    expected_close TEXT,
    stage TEXT NOT NULL DEFAULT 'new',
    owner_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (business_id) REFERENCES businesses(gers_id),
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS email_sends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT,
    business_id TEXT NOT NULL,
    contact_id INTEGER,
    step INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'sent', 'opened', 'replied', 'bounced')),
    sent_at TEXT,
    meta TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (business_id) REFERENCES businesses(gers_id),
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    segment TEXT,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'email',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id TEXT NOT NULL,
    user_id INTEGER,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (business_id) REFERENCES businesses(gers_id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS saved_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    filters_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('enrich', 'verify', 'pull')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    progress REAL NOT NULL DEFAULT 0,
    message TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contacts_business ON contacts(business_id);
CREATE INDEX IF NOT EXISTS idx_contacts_kind ON contacts(kind);
CREATE INDEX IF NOT EXISTS idx_targets_score ON targets(icp_score DESC);
CREATE INDEX IF NOT EXISTS idx_targets_status ON targets(status);
CREATE INDEX IF NOT EXISTS idx_touches_business ON touches(business_id);
CREATE INDEX IF NOT EXISTS idx_touches_scheduled ON touches(scheduled_for);
CREATE INDEX IF NOT EXISTS idx_status_history_business ON status_history(business_id);
CREATE INDEX IF NOT EXISTS idx_deals_business ON deals(business_id);
CREATE INDEX IF NOT EXISTS idx_notes_business ON notes(business_id);
CREATE INDEX IF NOT EXISTS idx_businesses_county ON businesses(county);
CREATE INDEX IF NOT EXISTS idx_businesses_lat_lng ON businesses(lat, lng);
"""

DEFAULT_OWNER = {
    "name": "Owner",
    "email": "owner@local.crm",
    "role": "owner",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def connect(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def migrate_db(conn: sqlite3.Connection) -> None:
    if not _column_exists(conn, "targets", "owner_id"):
        conn.execute("ALTER TABLE targets ADD COLUMN owner_id INTEGER")


def seed_owner(conn: sqlite3.Connection) -> int:
    existing = conn.execute(
        "SELECT id FROM users WHERE email = ?",
        (DEFAULT_OWNER["email"],),
    ).fetchone()
    if existing:
        return int(existing["id"])
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO users (name, email, role, active, created_at, updated_at)
        VALUES (?, ?, ?, 1, ?, ?)
        """,
        (DEFAULT_OWNER["name"], DEFAULT_OWNER["email"], DEFAULT_OWNER["role"], now, now),
    )
    return int(cur.lastrowid)


def clear_stale_demo_seed(conn: sqlite3.Connection) -> None:
    """Reset auto-seeded pipeline state when there is no real outreach activity."""
    touches = conn.execute(
        "SELECT COUNT(*) FROM touches WHERE completed_at IS NOT NULL"
    ).fetchone()[0]
    if touches > 0:
        return

    touched = """
        SELECT DISTINCT business_id FROM touches WHERE completed_at IS NOT NULL
    """
    stale = conn.execute(
        f"""
        SELECT COUNT(*) FROM targets
        WHERE status != 'new'
          AND business_id NOT IN ({touched})
        """
    ).fetchone()[0]
    if stale == 0 and conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == 0:
        return

    now = utc_now()
    conn.execute("DELETE FROM deals")
    conn.execute(
        f"""
        UPDATE targets SET status = 'new', updated_at = ?
        WHERE status != 'new'
          AND business_id NOT IN ({touched})
        """,
        (now,),
    )


def seed_sample_deals(conn: sqlite3.Connection, owner_id: int, limit: int = 12) -> None:
    """Seed deals on top-scored working/meeting targets for demo charts."""
    existing = conn.execute("SELECT COUNT(*) AS n FROM deals").fetchone()["n"]
    if existing >= limit:
        return
    now = utc_now()
    rows = conn.execute(
        """
        SELECT t.business_id, t.status, t.icp_score
        FROM targets t
        WHERE t.segment != 'excluded'
          AND t.icp_score >= 80
          AND t.business_id NOT IN (SELECT business_id FROM deals)
        ORDER BY t.icp_score DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    stages = ["new", "working", "working", "meeting", "meeting", "won"]
    for idx, row in enumerate(rows):
        stage = stages[idx % len(stages)]
        value = 1500 + (idx * 250)
        prob = {"new": 0.1, "working": 0.25, "meeting": 0.5, "won": 1.0}.get(stage, 0.2)
        conn.execute(
            """
            INSERT INTO deals (business_id, value, probability, stage, owner_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (row["business_id"], value, prob, stage, owner_id, now, now),
        )
        if stage != row["status"]:
            conn.execute(
                "UPDATE targets SET status = ?, updated_at = ? WHERE business_id = ?",
                (stage, now, row["business_id"]),
            )


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        migrate_db(conn)
        seed_owner(conn)
        clear_stale_demo_seed(conn)


def get_default_owner_id(db_path: Path = DB_PATH) -> int:
    init_db(db_path)
    with connect(db_path) as conn:
        return seed_owner(conn)


def upsert_business(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO businesses (
            gers_id, name, category, basic_category, taxonomy,
            address, city, state, zip, county, lat, lng, confidence,
            website, has_active_license, name_frequency, created_at, updated_at
        ) VALUES (
            :gers_id, :name, :category, :basic_category, :taxonomy,
            :address, :city, :state, :zip, :county, :lat, :lng, :confidence,
            :website, :has_active_license, :name_frequency, :created_at, :updated_at
        )
        ON CONFLICT(gers_id) DO UPDATE SET
            name = excluded.name,
            category = excluded.category,
            basic_category = excluded.basic_category,
            taxonomy = excluded.taxonomy,
            address = excluded.address,
            city = excluded.city,
            state = excluded.state,
            zip = excluded.zip,
            county = excluded.county,
            lat = excluded.lat,
            lng = excluded.lng,
            confidence = excluded.confidence,
            website = COALESCE(excluded.website, businesses.website),
            has_active_license = MAX(businesses.has_active_license, excluded.has_active_license),
            name_frequency = excluded.name_frequency,
            updated_at = excluded.updated_at
        """,
        {
            "created_at": now,
            "updated_at": now,
            "has_active_license": 0,
            "name_frequency": 1,
            **row,
        },
    )


def upsert_contact(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO contacts (
            business_id, kind, value, source, confidence,
            verify_status, verified_at, created_at, updated_at
        ) VALUES (
            :business_id, :kind, :value, :source, :confidence,
            :verify_status, :verified_at, :created_at, :updated_at
        )
        ON CONFLICT(business_id, kind, value) DO UPDATE SET
            source = excluded.source,
            confidence = COALESCE(excluded.confidence, contacts.confidence),
            verify_status = COALESCE(excluded.verify_status, contacts.verify_status),
            verified_at = COALESCE(excluded.verified_at, contacts.verified_at),
            updated_at = excluded.updated_at
        """,
        {
            "confidence": None,
            "verify_status": None,
            "verified_at": None,
            "created_at": now,
            "updated_at": now,
            **row,
        },
    )


def upsert_target(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO targets (
            business_id, segment, icp_score, status, do_not_contact,
            batch_id, owner_id, created_at, updated_at
        ) VALUES (
            :business_id, :segment, :icp_score, :status, :do_not_contact,
            :batch_id, :owner_id, :created_at, :updated_at
        )
        ON CONFLICT(business_id) DO UPDATE SET
            segment = excluded.segment,
            icp_score = excluded.icp_score,
            status = CASE
                WHEN targets.status IN ('won', 'dead') THEN targets.status
                ELSE excluded.status
            END,
            do_not_contact = MAX(targets.do_not_contact, excluded.do_not_contact),
            batch_id = COALESCE(excluded.batch_id, targets.batch_id),
            owner_id = COALESCE(excluded.owner_id, targets.owner_id),
            updated_at = excluded.updated_at
        """,
        {
            "status": "new",
            "do_not_contact": 0,
            "batch_id": None,
            "owner_id": None,
            "created_at": now,
            "updated_at": now,
            **row,
        },
    )


def insert_touch(conn: sqlite3.Connection, row: dict[str, Any]) -> int:
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO touches (
            business_id, channel, step, scheduled_for, completed_at,
            disposition, notes, created_at, updated_at
        ) VALUES (
            :business_id, :channel, :step, :scheduled_for, :completed_at,
            :disposition, :notes, :created_at, :updated_at
        )
        """,
        {
            "scheduled_for": None,
            "completed_at": None,
            "disposition": None,
            "notes": None,
            "created_at": now,
            "updated_at": now,
            **row,
        },
    )
    return int(cur.lastrowid)


def update_touch(conn: sqlite3.Connection, touch_id: int, **fields: Any) -> None:
    fields["updated_at"] = utc_now()
    assignments = ", ".join(f"{key} = :{key}" for key in fields)
    conn.execute(
        f"UPDATE touches SET {assignments} WHERE id = :touch_id",
        {"touch_id": touch_id, **fields},
    )


def insert_status_history(
    conn: sqlite3.Connection,
    business_id: str,
    from_status: str | None,
    to_status: str,
    changed_by: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO status_history (business_id, from_status, to_status, changed_by, changed_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (business_id, from_status, to_status, changed_by, utc_now()),
    )


def upsert_deal(
    conn: sqlite3.Connection,
    business_id: str,
    stage: str,
    owner_id: int | None = None,
    value: float | None = None,
    probability: float | None = None,
) -> None:
    from config import DEFAULT_DEAL_VALUE

    now = utc_now()
    existing = conn.execute(
        "SELECT id, value, probability FROM deals WHERE business_id = ?",
        (business_id,),
    ).fetchone()
    deal_value = value if value is not None else (existing["value"] if existing else DEFAULT_DEAL_VALUE)
    prob_map = {"new": 0.1, "working": 0.25, "meeting": 0.5, "won": 1.0, "dead": 0.0}
    deal_prob = probability if probability is not None else prob_map.get(stage, 0.2)
    if existing:
        conn.execute(
            """
            UPDATE deals SET stage = ?, value = ?, probability = ?, owner_id = COALESCE(?, owner_id), updated_at = ?
            WHERE business_id = ?
            """,
            (stage, deal_value, deal_prob, owner_id, now, business_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO deals (business_id, value, probability, stage, owner_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (business_id, deal_value, deal_prob, stage, owner_id, now, now),
        )


def bulk_upsert_businesses(rows: Iterable[dict[str, Any]], db_path: Path = DB_PATH) -> int:
    count = 0
    with connect(db_path) as conn:
        for row in rows:
            upsert_business(conn, row)
            count += 1
    return count


def bulk_upsert_contacts(rows: Iterable[dict[str, Any]], db_path: Path = DB_PATH) -> int:
    count = 0
    with connect(db_path) as conn:
        for row in rows:
            upsert_contact(conn, row)
            count += 1
    return count


def get_business(conn: sqlite3.Connection, gers_id: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM businesses WHERE gers_id = ?",
        (gers_id,),
    ).fetchone()


def count_table(table: str, db_path: Path = DB_PATH) -> int:
    with connect(db_path) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
