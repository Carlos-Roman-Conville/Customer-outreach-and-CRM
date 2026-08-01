import json

from fastapi import APIRouter, HTTPException

from api.deps import current_user_id, ensure_db
from api.schemas import SavedViewIn
from db import connect, utc_now

router = APIRouter()


@router.get("/views")
def list_views():
    ensure_db()
    user_id = current_user_id()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, filters_json, created_at FROM saved_views WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()
    return {
        "items": [
            {"id": r["id"], "name": r["name"], "filters": json.loads(r["filters_json"]), "created_at": r["created_at"]}
            for r in rows
        ]
    }


@router.post("/views")
def create_view(body: SavedViewIn):
    ensure_db()
    user_id = current_user_id()
    now = utc_now()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO saved_views (user_id, name, filters_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, body.name, json.dumps(body.filters), now, now),
        )
        view_id = int(cur.lastrowid)
    return {"id": view_id, "name": body.name, "filters": body.filters}


@router.delete("/views/{view_id}")
def delete_view(view_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM saved_views WHERE id = ?", (view_id,))
    return {"ok": True}
