# T01 - Project skeleton, tooling, docker compose

**ADRs:** 0001, 0005, 0006

## Scope
- `pyproject.toml` managed by uv, Python 3.12.
- Layout: `app/` (`api/`, `core/`, `db/`, `processing/`, `worker/`), `tests/`, `migrations/`, `scripts/`, `docs/`.
- `docker-compose.yml`: `api`, `worker`, `db` (postgis/postgis), `redis`; shared uploads volume.
- Settings via pydantic-settings (`DATABASE_URL`, `REDIS_URL`, `UPLOAD_DIR`, `MAX_UPLOAD_BYTES`, `INLINE_MAX_BYTES`).
- `GET /api/health/`.
- ruff + mypy config.

## Acceptance
- `docker compose up` starts all services and `/api/health/` returns 200.
- `uv run ruff check`, `uv run mypy app` pass.
