"""Shared API dependencies."""
from __future__ import annotations

from db import get_default_owner_id, init_db


def ensure_db() -> None:
    init_db()


def current_user_id() -> int:
    ensure_db()
    return get_default_owner_id()
