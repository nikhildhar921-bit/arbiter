# Arbiter

Arbiter is an explainable credit decisioning engine. A loan application
comes in with supporting documents; the system extracts structured data
from those documents, pulls (mocked) bureau data, runs a deterministic
decision, explains the outcome in plain language, and routes anything
it isn't confident about to a human reviewer. Every decision is
traceable and auditable.

The LLM in this system never makes the credit decision — it only
extracts data and writes explanations. Deterministic rules decide.
That's the core design choice the rest of the project follows from.

## Setup

`.env` is gitignored and never committed — copy the example and fill it
in before running the app:

```bash
cp .env.example .env
```

`OPEN_AI_KEY` is the only value you must set — the app won't start
without it. Everything else in `.env.example` (`DATABASE_URL`,
`REDIS_HOST`/`REDIS_PORT`/`REDIS_DB`, `LOAD_TEST_MODE`) already has a
working default and only needs changing if your local setup differs.

## Run with Docker Compose

This brings up Postgres, Redis, Jaeger (tracing), runs the database
migration automatically, then starts the app — one command, nothing
installed locally except Docker:

```bash
docker compose up --build
```

`OPEN_AI_KEY` must be set in your shell environment or `.env` before
running this — compose fails fast with a clear message if it's missing,
rather than starting half-configured.

Once it's up:
- **http://localhost:8000** — the demo UI (try a bundled sample document)
- **http://localhost:8000/docs** — the API reference (Swagger UI)
- **http://localhost:16686** — Jaeger, showing traces once a few requests
  have gone through

Qdrant (the vector store used for RAG retrieval) runs embedded inside the
app process itself, not as a separate service — its data is kept in a
named volume (`qdrantdata`) so it survives container restarts.
