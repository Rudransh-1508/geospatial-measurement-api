# T02 - Database models and migrations

**ADRs:** 0005, 0006

## Scope
- `uploads`: id (uuid), filename, stored_path, size_bytes, file_format, status, source_crs, crs_assumed, feature_count, layer_count, error, warnings (jsonb), created_at, updated_at, processed_at.
- `features`: id, upload_id (fk, cascade), index, layer, geometry_type, geometry (`geometry(Geometry,4326)`, nullable), properties (jsonb), status, reason, warnings (jsonb), measurement fields (kind, value, unit, perimeter, method, projection, geodesic_value, relative_difference).
- Alembic initial migration enabling the `postgis` extension.

## Acceptance
- `alembic upgrade head` creates the schema on a fresh PostGIS database; the api container runs it at startup.
