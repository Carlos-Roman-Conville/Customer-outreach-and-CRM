from fastapi import APIRouter

from api.demo import demo_flag, demo_stats_flag
from api.deps import ensure_db
from db import connect

router = APIRouter()


@router.get("/me")
def get_me():
    ensure_db()
    with connect() as conn:
        user = conn.execute(
            "SELECT id, name, email, role FROM users WHERE active = 1 ORDER BY id LIMIT 1"
        ).fetchone()
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "demo_mode": demo_flag(),
        "demo_stats": demo_stats_flag(),
    }
