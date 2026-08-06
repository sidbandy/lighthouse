# Deployment

Target: permanently free, no card, nothing that sleeps in a way that matters.

| Piece | Host | Why |
|---|---|---|
| Frontend | Vercel | Free tier is permanent and static hosting is what it is best at |
| Database | Supabase | Free Postgres with pgvector; the schema needs both |
| Scheduled ingest | GitHub Actions | Free, and a cron runner is the right shape for a job that takes a minute |
| API | Vercel Python functions | Free tier is permanent, and the API is request/response only |

Railway and Fly were ruled out: both are trial credit rather than a standing
free tier, and this needs to keep working without a monthly decision.

---

## What had to change to fit

A serverless function is frozen the moment it returns a response, so two things
in the app could not survive the move.

**Ingest ran in a worker thread.** A full run touches ~95 sources and takes
about a minute; the thread would be killed as soon as the triggering request
finished. It now runs in `.github/workflows/ingest.yml` on a schedule, which is
better regardless — new postings are waiting when you open the app instead of
being fetched when you remember to press a button. `POST /api/ingest/refresh`
still exists and still works when the API is running as a real process
(locally, or on any host that is not serverless).

**Two in-memory caches.** The match index is rebuilt from a dozen corpus facts
and costs milliseconds, so a cold process is fine. The market index is not: it
tokenises every sampled description and takes about a second at 425 postings.
On a platform where every request may be a cold start, that is paid every time.

> **Not yet done.** The market index still lives in process memory. The fix is
> to precompute it during ingest into a `posting_terms` table (posting_id, term,
> occurrences) and let `discover/coverage.py` read counts and reach as SQL
> instead of rebuilding sets in Python. At ~425 postings × ~200 signal terms
> that is around 85k rows, which Postgres will not notice, and it makes the
> corpus page O(query) instead of O(corpus). **Do this before deploying the API
> to Vercel**; until then, run the API on something that keeps a process.

---

## Setup

### 1. Supabase

Create the project, then:

- **Database → Extensions**: enable `vector`.
- **Authentication → Sign In / Providers → Email**: turn *Confirm email* off
  while building; back on before anyone else signs up.
- **Connect → Direct · Connection string**: copy the **Session pooler** URI
  (host `aws-0-<region>.pooler.supabase.com`, port `5432`).
  Not the direct connection, which is IPv6-only on the free tier and fails from
  most home networks. Not the transaction pooler on `6543`, which does not
  support the prepared statements SQLAlchemy issues.

Local `.env` (already gitignored):

```
LIGHTHOUSE_DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
LIGHTHOUSE_SUPABASE_URL=https://<ref>.supabase.co
LIGHTHOUSE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
LIGHTHOUSE_SUPABASE_SECRET_KEY=sb_secret_...
```

The keys Supabase's own snippets use (`NEXT_PUBLIC_SUPABASE_URL`,
`DATABASE_CONNECTION_STRING`, `SECRET_KEY`) are accepted as aliases, so a
copy-paste from the dashboard works without editing.

Then apply the schema:

```bash
cd backend && ../.venv/bin/alembic upgrade head
```

### 2. GitHub Actions

Repository → Settings → Secrets and variables → Actions → New secret:

- `LIGHTHOUSE_DATABASE_URL` — the same session-pooler URI as above.

The workflow runs at 06:00 and 18:00 UTC and can be triggered by hand from the
Actions tab. It migrates before ingesting, so a schema change deploys with the
next run.

### 3. Vercel

- Import the repo, set the root directory to `web/`.
- Environment variable `VITE_API_BASE` pointing at the API.
- The frontend needs no secrets: it holds only the publishable key, which is
  safe in a browser by design.

---

## Running it locally

Unchanged, and still the fastest way to work: local Postgres, `uvicorn`, and
`npm run dev`. See HANDOFF §6. The test suite runs against local Postgres in
about a second and should stay that way — pointing it at Supabase would put
every assertion behind a network round trip.
