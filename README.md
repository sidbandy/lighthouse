# Lighthouse

Lighthouse is a self-hosted command center for the software engineering internship and
new-grad search. It ingests postings from company boards and aggregators, tracks every
application through to offer, builds intel on the companies behind those postings, and
turns the résumé gaps and interview loops it observes into study and practice work. The
value is not in any single phase but in the connections between them: what you discover
shapes what you track, what you track shapes which companies you research, company intel
and rejections shape what you study and practice, and the daily briefing pulls the whole
graph into one short list of what to do next.

## Requirements

- Python 3.11–3.13
- Node 20+
- PostgreSQL 16 with the `pgvector` extension

## Setup

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e "backend[dev,resume]"

createdb lighthouse
psql lighthouse -c "CREATE EXTENSION IF NOT EXISTS vector;"

cp .env.example .env   # edit if your Postgres URL differs
.venv/bin/alembic upgrade head
```

Optional extras: `embeddings` (local sentence-transformers model, large download) and
`aggregators` (breadth connectors). Install them the same way, e.g.
`.venv/bin/pip install -e "backend[dev,resume,embeddings]"`.

## Running

```sh
.venv/bin/uvicorn lighthouse.api:app --reload --app-dir backend
```

The API serves on http://127.0.0.1:8000.

## Testing

```sh
.venv/bin/pytest backend/tests
```

## Project layout

```
backend/
  lighthouse/
    core/                 settings, database session, SQLAlchemy models
    ingest/               normalization, dedupe, and the ingestion pipeline
      connectors/         per-source fetchers (company boards, aggregators)
    discover/             search, ranking, and fit scoring over ingested postings
    track/                applications, stages, and outcome history
    companies/            company profiles and research signals
    study/                topic coverage and spaced-repetition scheduling
    practice/             interview problem sets and session records
    briefing/             the daily digest assembled from every other phase
  tests/                  pytest suite, fixtures under tests/fixtures
web/                      React frontend
worker/                   scheduled ingestion and background jobs
scripts/                  operational one-offs
docs/                     design notes
```
