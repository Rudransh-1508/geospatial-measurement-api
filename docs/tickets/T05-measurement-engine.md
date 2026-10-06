# T05 - Measurement engine

**ADRs:** 0003

## Scope
- Pure functions: `measure(geometry_4326) -> MeasurementResult`.
- Spherical feature centre (antimeridian safe).
- LAEA area + perimeter for (Multi)Polygon, holes subtracted; AEQD length for (Multi)LineString; points `not_applicable`.
- Geodesic reference via `pyproj.Geod`, relative difference.
- Z dropped with warning; invalid polygons repaired with `make_valid` and warning; empty / GeometryCollection `unsupported`.

## Acceptance
- Known-answer tests at 0°, 45°, 70°; antimeridian polygon; hole; MultiPolygon; real Indian plot; relative difference below 1e-4 for parcel-sized features.
