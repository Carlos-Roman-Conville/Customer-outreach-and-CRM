# Philly Outreach CRM

A local-first CRM built on top of a real Philadelphia metro lead pipeline — **141,300 businesses**, Overture Maps ingestion, ICP scoring, call cadence tracking, and email verification.

> "I built the system I use to find and contact my own clients."

## What it does

1. **Data pipeline (CLI)** — Pull POIs from Overture, join Philly business licenses, score ICP, enrich emails, verify MX records, assign campaign batches.
2. **CRM (web)** — FastAPI + React dashboard for daily calling, territory map, lead search, pipeline board, campaigns, and enrichment jobs.

## Quick start (local, no Docker)

```bash
# 1. Python deps
pip install -r requirements.txt

# 2. Initialize DB + run pipeline (if not already done)
python pipeline.py run-core

# 3. API (terminal 1)
uvicorn api.main:app --reload --port 8000

# 4. Frontend (terminal 2)
cd web
npm install
npm run dev
```

Open **http://127.0.0.1:5173** · API docs at **http://127.0.0.1:8000/docs**

## CRM pages

| Page | Purpose |
|------|---------|
| Dashboard | KPIs, activity chart, email health |
| Call Mode | Full-screen dialer UX, keyboard dispositions 1–5 |
| Territory Map | MapLibre heatmap + load viewport as call queue |
| Lead Database | Search/filter 141k leads, detail drawer |
| Email Campaigns | Batch list, verify status, cadence steps |
| Pipeline Board | Kanban New → Won/Dead |
| Enrichment | Start verify/enrich jobs, progress bars |
| Analytics | ICP deciles, connect-by-hour, segment funnel |

**Cmd/Ctrl+K** — global search palette

## CLI (still works)

```bash
python pipeline.py queue show
python call_queue.py log <gers_id> connected --notes "Interested"
python pipeline.py verify          # required before email export
python pipeline.py export --batch-id batch_001
```

## Work mode vs demo display

| Launcher | Use |
|----------|-----|
| `start.bat` | Daily CRM — real stats, real contact data |
| `start-demo.bat` | Portfolio / screenshots — PII scrambled, sample funnel metrics |

Demo mode sets `DEMO_MODE=1` (scramble names, phones, emails in API responses) and
`DEMO_STATS=1` (sample meetings, pipeline, activity chart). Your SQLite file is unchanged;
outreach numbers are overlaid at read time only.

For normal use, always launch with `start.bat` so dashboard stats reflect your actual calls.

## Architecture

```
Overture S3 → DuckDB pull → SQLite (outreach.db)
                              ↑
CLI pipeline ─────────────────┤
                              ↓
                    FastAPI (:8000) ← Vite React (:5173)
```

**Stack:** Python 3.11, SQLite WAL, FastAPI, React 19, TanStack Query, MapLibre GL, Recharts.

## Portfolio story

- Real data, not Lorem ipsum — 8-county metro, 94% phone coverage
- Full funnel: acquisition → scoring → outreach → disposition → pipeline value
- Call-led GTM with email air cover (Mon email / Wed call / Fri follow-up)
- Verification gate prevents burning sending domains

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEMO_MODE` | `0` | Scramble PII in API responses |
| `DEMO_STATS` | `0` | Overlay sample outreach KPIs on dashboard |
| `DEFAULT_DEAL_VALUE` | `2500` | Default deal size on status change |
| `API_PORT` | `8000` | FastAPI port |

## License

Private / portfolio use. Overture Maps data subject to [Overture terms](https://overturemaps.org).
