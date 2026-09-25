"""FastAPI CRM application."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import analytics, campaigns, enrich, leads, map_router, me, meta, pipeline, queue, search, stats, views

app = FastAPI(
    title="Philly Outreach CRM",
    description="Local CRM for Philadelphia metro business outreach",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(me.router, prefix="/api", tags=["me"])
app.include_router(stats.router, prefix="/api", tags=["stats"])
app.include_router(meta.router, prefix="/api", tags=["meta"])
app.include_router(queue.router, prefix="/api", tags=["queue"])
app.include_router(leads.router, prefix="/api", tags=["leads"])
app.include_router(map_router.router, prefix="/api", tags=["map"])
app.include_router(search.router, prefix="/api", tags=["search"])
app.include_router(enrich.router, prefix="/api", tags=["enrich"])
app.include_router(campaigns.router, prefix="/api", tags=["campaigns"])
app.include_router(pipeline.router, prefix="/api", tags=["pipeline"])
app.include_router(analytics.router, prefix="/api", tags=["analytics"])
app.include_router(views.router, prefix="/api", tags=["views"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
