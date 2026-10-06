# 0009 - Testing strategy

## Decision
- **Unit tests (pytest)** call the measurement and reading functions directly. Reference areas come from a closed-form WGS84 formula that does not use pyproj. Known-answer fixtures:
  - Meridian/parallel cells of exactly known area at latitudes 0° to 89°.
  - A polygon crossing the antimeridian.
  - A polygon with a hole; a MultiPolygon.
  - An irregular survey-sized plot near Pune, India, cross-checked against the geodesic value and PostGIS.
  - Lines with known geodesic length.
  - 3D geometries, invalid (self-intersecting) polygons, empty geometries, GeometryCollections.
  - Shapefile with/without `.prj`, multi-layer zip, zip-slip and zip-bomb archives, KML with nested folders, KMZ.
- **API tests** use FastAPI's TestClient with `?wait=true` (inline processing) against PostGIS.
- **One end-to-end test** in CI runs the full compose stack (api, worker, redis, postgis), uploads a file without `wait`, polls until `COMPLETED`, and checks measurements.
- **Independent check**: integration tests compare our area/length with PostGIS `ST_Area(geography)` / `ST_Length(geography)`.
- **Static checks**: ruff (lint + format) and mypy (strict on `app/`).
- **CI**: GitHub Actions runs all of the above on every push.

## Options considered
- Celery eager mode everywhere - fast, but hides real queue/serialization issues. Rejected in favour of direct function calls plus one real E2E test.
