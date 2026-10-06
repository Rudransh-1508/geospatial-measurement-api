# Architecture Decision Records

Each ADR records one significant decision: context, options considered, the choice, and its consequences.

| # | Decision | Status |
|---|----------|--------|
| [0001](0001-fastapi-sqlalchemy.md) | FastAPI + SQLAlchemy 2 + Alembic | Accepted |
| [0002](0002-geo-library-stack.md) | pyogrio + Shapely 2 + pyproj, no GeoPandas | Accepted |
| [0003](0003-per-feature-local-projection.md) | Per-feature local projection with geodesic cross-check | Accepted |
| [0004](0004-crs-normalization-policy.md) | CRS normalization and missing-CRS policy | Accepted |
| [0005](0005-postgres-postgis.md) | Postgres + PostGIS for storage | Accepted |
| [0006](0006-async-processing-celery.md) | Async processing with Celery + Redis, Postgres as status source of truth | Accepted |
| [0007](0007-upload-safety-and-storage.md) | Upload validation, zip safety, and file storage | Accepted |
| [0008](0008-measurements-response-shape.md) | Measurements response shape | Accepted |
| [0009](0009-testing-strategy.md) | Testing strategy | Accepted |
