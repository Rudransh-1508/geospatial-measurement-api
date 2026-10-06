# T06 - Processing pipeline, Celery task, inline mode

**ADRs:** 0006

## Scope
- `process_upload(session, upload_id)`: PROCESSING -> read -> measure -> replace features in one transaction -> COMPLETED; on invalid file FAILED + error.
- Celery app (Redis broker, no result backend, `acks_late`, `task_reject_on_worker_lost`), task with retries on transient DB errors.
- `?wait=true` under `INLINE_MAX_BYTES` runs inline.

## Acceptance
- Re-running processing leaves exactly one set of features.
- Corrupt file -> FAILED with reason.
