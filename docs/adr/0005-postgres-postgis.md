# 0005 - Postgres + PostGIS for storage

## Context
We persist uploads, features, geometries and measurements, and serve them back paginated.

## Options considered
- **SQLite** - zero setup, but no native geometry and weak concurrency with a separate worker process.
- **Postgres** - solid, but geometry stored as text/JSON.
- **Postgres + PostGIS** - native geometry columns, spatial indexes, and an independent geodesic implementation (`ST_Area(geography)`, `ST_Length(geography)`).

## Decision
Postgres + PostGIS, run via docker compose. Normalized geometries stored as `geometry(Geometry, 4326)`.

## Consequences
- PostGIS gives a second, independent check on our numbers in integration tests.
- Future spatial queries (bbox filters, intersections) are cheap to add.
- Local setup requires Docker; `docker compose up` is the documented path.
