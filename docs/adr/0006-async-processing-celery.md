# 0006 - Async processing with Celery + Redis, Postgres as status source of truth

## Context
Large Shapefiles can take seconds to minutes. The example response includes a `status` field, implying a lifecycle.

## Options considered
- **Synchronous** - simplest, but holds HTTP requests open and times out on large files.
- **FastAPI BackgroundTasks** - in-process; jobs are lost on restart and compete with request handling.
- **Postgres-backed job table (`SKIP LOCKED`)** - no extra infrastructure, but custom code to own.
- **Celery + Redis** - conventional, battle-tested, separate scalable worker processes.

## Decision
Celery with Redis as broker.
- `POST /api/files/` stores the file, creates the upload row with `PENDING`, enqueues `process_upload(upload_id)`, returns `202`.
- **Postgres is the single source of truth for status.** The task moves the row `PENDING -> PROCESSING -> COMPLETED | FAILED` and stores `error` on failure. Celery result backend is disabled.
- **Idempotent task**: processing deletes and rewrites the upload's features in one transaction, so retries never duplicate.
- `acks_late=True` and `task_reject_on_worker_lost=True`: a crashed worker's task is redelivered.
- Retries: up to 3 with exponential backoff, only for transient errors (DB connectivity). Unreadable/invalid files fail fast with a stored reason.
- `?wait=true`: uploads under 5 MB (configurable) are processed inline by calling the same processing function in the request; larger uploads ignore it and are queued.

## Consequences
- Workers scale independently (`docker compose up --scale worker=N`).
- Two extra services (Redis, worker) in compose.
- One processing function, two entry points (task, inline) - easy to test directly.
