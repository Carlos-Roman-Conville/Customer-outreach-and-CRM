import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.jobs import enrichment_progress, job_stream_sleep, latest_job, start_job
from api.schemas import EnrichStartIn

router = APIRouter()


@router.get("/enrich/progress")
def progress():
    return enrichment_progress()


@router.post("/enrich/start")
def start_enrichment(body: EnrichStartIn):
    return start_job(body.kind, limit=body.limit)


@router.get("/enrich/stream")
def stream_job(job_id: int | None = None):
    jid = job_id or (latest_job() or {}).get("id")
    if not jid:
        return {"message": "No job"}

    def event_generator():
        for item in job_stream_sleep(int(jid)):
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
