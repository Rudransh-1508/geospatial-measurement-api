# 0001 - FastAPI + SQLAlchemy 2 + Alembic

## Context
The assignment allows Django + DRF or FastAPI. The service is a small, API-only backend with three resource endpoints and background processing.

## Options considered
- **Django + DRF + GeoDjango** - batteries included, geometry-aware ORM and admin. Heavier, GeoDjango needs system GDAL/GEOS, more framework surface to explain.
- **FastAPI + SQLAlchemy 2 + Alembic** - typed request/response models (Pydantic) double as documentation, free OpenAPI UI at `/docs`, explicit and small.

## Decision
FastAPI, SQLAlchemy 2 (typed ORM), Alembic migrations, GeoAlchemy2 for PostGIS columns.

## Consequences
- Pydantic schemas are the single definition of the API contract; OpenAPI is generated from them.
- No admin UI; not needed for this scope.
- Database migrations are explicit and reviewable.
