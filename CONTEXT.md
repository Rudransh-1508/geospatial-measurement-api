# Context

Glossary for the Geospatial File Measurement API. Code, docs and tickets use these terms with exactly these meanings.

## Domain terms

- **Upload** - one file submitted to `POST /api/files/`. Has an id, original filename, stored path, status and file-level CRS.
- **Layer** - a named collection of features inside an upload. A Shapefile zip can contain several layers (one per `.shp`); a KML/KMZ yields one layer per folder/document as exposed by GDAL.
- **Feature** - one geometry plus its properties (attributes) inside a layer. Identified by a stable index within the upload.
- **Geometry type** - the OGC type of a feature's geometry: `Point`, `LineString`, `Polygon`, their `Multi*` variants, or `GeometryCollection`.
- **Properties** - the non-geometry attributes of a feature (Shapefile DBF columns, KML ExtendedData/name/description).

## Coordinate reference systems

- **CRS** - coordinate reference system. Defines what coordinate numbers mean on the Earth.
- **Source CRS** - the CRS declared by the uploaded file (`.prj` for Shapefile; always EPSG:4326 for KML/KMZ).
- **Geographic CRS** - coordinates are angles (longitude/latitude in degrees), e.g. EPSG:4326. Never measured directly.
- **Projected CRS** - coordinates are planar distances (usually metres), produced by a map projection. Every projection distorts something.
- **Normalized geometry** - a feature's geometry transformed from its source CRS to EPSG:4326. All measurement starts from here.
- **Assumed CRS** - EPSG:4326 applied to a Shapefile that has no `.prj` but whose coordinates all fit valid lon/lat ranges. Flagged with `crs_assumed: true`.
- **Local projection** - a projected CRS built on the fly and centred on a single feature:
  - **LAEA** (Lambert Azimuthal Equal-Area) for areas; preserves area exactly.
  - **AEQD** (Azimuthal Equidistant) for lengths; preserves distance from the centre, low distortion nearby.
- **Feature centre** - the point a local projection is centred on. Computed on the sphere so it stays correct across the antimeridian.
- **Antimeridian** - the ±180° longitude line. Naive averaging of longitudes breaks for features crossing it.

## Measurements

- **Measurement** - the computed size of a feature: `area` (+ `perimeter`) for polygons, `length` for lines, `none` for points.
- **Projected value** - the measurement computed in the feature's local projection. This is the primary `value` returned.
- **Geodesic value** - the same measurement computed directly on the WGS84 ellipsoid (`pyproj.Geod`). Used as a reference.
- **Relative difference** - `|projected - geodesic| / geodesic`. Exposes projection error per feature.
- **Measurement method** - which technique produced the value (`local_laea`, `local_aeqd`) plus the exact proj string used.
- **Unsupported feature** - a feature that cannot be measured (empty geometry, GeometryCollection, unknown CRS). Gets `status: unsupported` and a reason; never crashes processing.
- **Warning** - a non-fatal note attached to a feature or upload (e.g. `z_dropped`, `geometry_repaired`, `crs_assumed`).

## Processing

- **Upload status** - lifecycle of an upload: `PENDING` -> `PROCESSING` -> `COMPLETED` | `FAILED`.
- **Processing task** - the Celery task that reads, normalizes and measures an upload's features. Idempotent: re-running replaces the upload's features.
- **Inline processing** - `?wait=true` on small uploads runs the same processing function inside the HTTP request instead of via Celery.
