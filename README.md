<div align="center">

<img src="docs/logo.svg" alt="" height="72" />

# Geospatial File Measurement API

[![CI](https://img.shields.io/github/actions/workflow/status/Rudransh-1508/geospatial-measurement-api/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Rudransh-1508/geospatial-measurement-api/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776ab?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![PostGIS](https://img.shields.io/badge/PostGIS-336791?style=flat-square&logo=postgresql&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-37814a?style=flat-square&logo=celery&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker_Compose-2496ed?style=flat-square&logo=docker&logoColor=white)

**Upload a Shapefile, KML or KMZ. Get the area of every polygon and the length of every line, accurate anywhere on Earth.**

[Overview](#overview) • [Get started](#getting-started) • [API](#api) • [Architecture](#architecture) • [Design decisions](#design-decisions) • [Testing](#testing) • [Learnings](#learnings) • [Future scope](#future-scope)

![Home page: drop a survey file and see every measured file](docs/home.png)

</div>

Most tools measure map data in one global projection, which quietly distorts the result: Web Mercator doubles areas at 45° latitude. This service measures **each feature in its own projection, centred on that feature**: Lambert Azimuthal Equal-Area for areas and Azimuthal Equidistant for lengths. It then **checks every number against the WGS84 ellipsoid**, so each result comes with proof of its own accuracy.

> [!TIP]
> Have Docker? Run `docker compose up -d --build --wait`, open <http://localhost:8000> and click a sample file. You'll have measured plots on a map in under a minute.

## Overview

| Approach | Area error at 45° | Area error at 85° |
|---|---|---|
| Web Mercator (EPSG:3857) | 100% (2x too large) | 13,000% (130x) |
| UTM zone of the feature | 0.02% | 0.08% |
| **This service: local equal-area projection** | **0.0000000004%** | **0.0000000003%** |

<sub>Relative error for a ~1 km plot against an exact closed-form ellipsoid area. Full results: [docs/accuracy.md](docs/accuracy.md).</sub>

### Features

- **Accurate everywhere.** Each feature gets its own projection, so there are no UTM zone edges, no polar special cases, and features crossing the 180° antimeridian (such as Fiji) are measured correctly.
- **Results you can check.** Every measurement returns the exact PROJ string used, a geodesic reference value and their relative difference. Tests check the values against PostGIS `ST_Area(geography)`.
- **Handles real-world files.** These inputs become a clear `status`, `reason` or `warning`, never a crash:
  - multi-layer zips and nested KML folders
  - Shapefiles with no `.prj`
  - 3D coordinates, self-intersecting polygons, holes, multi-part features
  - empty or missing geometries
- **Built like a production service.**
  - Celery workers with retry-safe, idempotent tasks.
  - Protection against zip-slip and zip bombs; oversized uploads are rejected before the body is read.
  - Alembic migrations, strict mypy typing, and CI that runs the full stack end to end.
- **Fast.** 12,000 polygons are measured in about 2 seconds.
- **Usable without code.** A drag-and-drop home page with live status, and a map viewer for every file.

<div align="center">
  <img src="docs/viewer.png" alt="Map viewer showing four survey parcels near Pune with their areas" width="820" />
</div>

## Getting started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose
- Optional, for development: [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you)

### Run it

```bash
git clone https://github.com/Rudransh-1508/geospatial-measurement-api.git
cd geospatial-measurement-api
docker compose up -d --build --wait
```

This starts the API, a Celery worker, Redis and PostGIS. Database migrations run automatically.

| Open | For |
|---|---|
| <http://localhost:8000> | Home page: drop a file or click a sample, then choose **Open map** |
| <http://localhost:8000/docs> | Interactive API documentation |

Or call the API directly:

```bash
curl -F "file=@samples/parcels_utm43n.zip" "http://localhost:8000/api/files/?wait=true"
```

> [!NOTE]
> The official PostGIS image has no ARM build, so on Apple Silicon it runs under emulation. Everything works, but database steps are a little slower.

### Sample files

The [`samples/`](samples) folder has files for trying the service. Regenerate them with `uv run python -m scripts.make_samples`.

| File | What it shows |
|---|---|
| `pune_survey.kml` | Plots, roads and wells in nested folders, with ExtendedData attributes |
| `parcels_utm43n.zip` | Shapefile in a projected CRS (UTM 43N) |
| `village_layers.zip` | Three Shapefile layers in one zip, one in a subfolder |
| `edge_cases.kml` | Antimeridian (Fiji), 78°N (Svalbard), a hole, a self-intersecting polygon, a 120 km line, a MultiPolygon |
| `plots_no_prj.zip` | Shapefile without a `.prj` (CRS assumed and flagged) |
| `pune_plots.kmz` | Zipped KML |

<details>
<summary><b>Local development without Docker for the app</b></summary>

```bash
uv sync                                  # Python 3.12 + dependencies
docker compose up -d db redis            # PostGIS on :5433, Redis on :6380
uv run alembic upgrade head
uv run uvicorn app.main:app --reload     # API on :8000
uv run celery -A app.worker.celery_app worker --loglevel=INFO   # in a second terminal
```

</details>

<details>
<summary><b>Configuration</b></summary>

Settings are read from environment variables (see [`.env.example`](.env.example)).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://geomeasure:geomeasure@localhost:5433/geomeasure` | PostGIS connection |
| `REDIS_URL` | `redis://localhost:6380/0` | Celery broker |
| `UPLOAD_DIR` | `./data/uploads` | Where original uploads are stored |
| `MAX_UPLOAD_BYTES` | 50 MB | Upload size limit |
| `INLINE_MAX_BYTES` | 5 MB | Largest file `?wait=true` processes inside the request |
| `MAX_UNCOMPRESSED_BYTES` | 500 MB | Zip bomb limit for `.zip` and `.kmz` |

</details>

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/files/` | Upload and process a file |
| `GET` | `/api/files/{id}/` | File information and processing status |
| `GET` | `/api/files/{id}/measurements/` | Per-feature measurements with totals |
| `GET` | `/api/files/` | List uploads, newest first |
| `GET` | `/api/health/` | Liveness and database check |
| `GET` | `/` and `/viewer/{id}` | Home page and map viewer (HTML) |

### Upload a file

`POST /api/files/` takes a multipart form with a `file` field: `.zip` (Shapefile), `.kml` or `.kmz`.

- **By default** it returns `202 Accepted` with `status: PENDING`, and a worker processes the file. Poll `GET /api/files/{id}/` until the status is `COMPLETED` or `FAILED`.
- **With `?wait=true`**, files up to 5 MB are processed inside the request, and the response is `201 Created` with the final status. Larger files are queued as usual.

```bash
curl -F "file=@samples/pune_survey.kml" http://localhost:8000/api/files/
```

```json
{
  "id": "4678b360-1bd5-4c5b-a54c-f9d6abeec483",
  "filename": "pune_survey.kml",
  "file_format": "kml",
  "size_bytes": 2197,
  "status": "PENDING",
  "feature_count": null,
  "crs": null,
  "links": {
    "self": "/api/files/4678b360-1bd5-4c5b-a54c-f9d6abeec483/",
    "measurements": "/api/files/4678b360-1bd5-4c5b-a54c-f9d6abeec483/measurements/",
    "viewer": "/viewer/4678b360-1bd5-4c5b-a54c-f9d6abeec483"
  }
}
```

| Status | When |
|---|---|
| `415` | The extension is not `.zip`, `.kml` or `.kmz` |
| `413` | The file is larger than 50 MB; rejected from `Content-Length` before the body is read |
| `400` | Any of: an empty file; content that doesn't match the extension; a corrupt zip; unsafe paths in a zip (zip-slip); an archive that expands too much (zip bomb); a Shapefile missing `.shx` or `.dbf`; a KMZ with no `.kml` |
| `503` | The processing queue is unreachable; the upload is marked `FAILED` |

A file that passes these checks but which GDAL can't read ends as `status: FAILED`, with a readable `error`.

### Get file information

`GET /api/files/{id}/`

```json
{
  "id": "8d8fd6d9-81bb-4e21-9942-802e54a99482",
  "filename": "parcels_utm43n.zip",
  "file_format": "shapefile",
  "size_bytes": 1295,
  "status": "COMPLETED",
  "feature_count": 4,
  "layers": ["parcels_utm43n"],
  "crs": "EPSG:32643",
  "crs_assumed": false,
  "warnings": [],
  "error": null,
  "created_at": "2026-10-06T19:40:17.477526Z",
  "processed_at": "2026-10-06T19:40:17.555450Z",
  "links": { "self": "...", "measurements": "...", "viewer": "..." }
}
```

`crs` is the file's source CRS. When layers use different CRSs it is `MIXED`, and each feature reports its own.

### Get measurements

`GET /api/files/{id}/measurements/` accepts these query parameters:

| Parameter | Default | Meaning |
|---|---|---|
| `limit` | 100 | Features per page, 1 to 1000 |
| `offset` | 0 | Features to skip |
| `include_geometry` | `true` | Whether to return GeoJSON geometries |

It returns `409` until the file is `COMPLETED`, and `404` for unknown ids.

```json
{
  "file_id": "c93d5c12-12e4-4c95-8a68-9c05db2e316b",
  "status": "COMPLETED",
  "crs": "EPSG:4326",
  "totals": {
    "feature_count": 8,
    "by_geometry_type": { "LineString": 2, "Point": 2, "Polygon": 4 },
    "by_status": { "measured": 6, "not_applicable": 2 },
    "area_m2": 192242.7374064453,
    "length_m": 1329.7454498275429
  },
  "pagination": { "limit": 100, "offset": 0, "total": 8 },
  "features": [
    {
      "id": 3,
      "layer": "Plots",
      "geometry_type": "Polygon",
      "crs": "EPSG:4326",
      "properties": { "Name": "Plot S-104", "village": "Bavdhan", "survey_no": "S-104" },
      "geometry": { "type": "Polygon", "coordinates": [[[73.7826, 18.5338], [73.7849, 18.5341], [73.7853, 18.5322], [73.7829, 18.5321], [73.7826, 18.5338]]] },
      "status": "measured",
      "reason": null,
      "warnings": [],
      "measurement": {
        "kind": "area",
        "value": 50252.08816679674,
        "unit": "m2",
        "perimeter": 904.0554730942821,
        "perimeter_unit": "m",
        "method": "local_laea",
        "projection": "+proj=laea +lat_0=18.53 +lon_0=73.78 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs",
        "geodesic_value": 50252.08815480769,
        "geodesic_perimeter": 904.0554724937334,
        "relative_difference": 2.3857822005895523e-10
      }
    }
  ]
}
```

<details>
<summary><b>Field reference</b></summary>

| Field | Meaning |
|---|---|
| `id` | Feature index within the file, stable across pages |
| `layer` | Shapefile name or KML folder |
| `geometry_type` | Source geometry type (`Polygon`, `MultiLineString`, `Point`, ...) |
| `crs` | Source CRS of the feature's layer |
| `properties` | Attributes: DBF columns, or KML name, description and ExtendedData |
| `geometry` | GeoJSON in EPSG:4326, as RFC 7946 requires |
| `status` | `measured`, `not_applicable` (points) or `unsupported` (see `reason`) |
| `reason` | Why a feature wasn't measured: `missing_geometry`, `unknown_crs`, `empty_geometry`, `geometry_collection_not_supported`, `invalid_geometry_unrepairable`, `transform_failed` |
| `warnings` | `z_dropped` (non-zero heights ignored), `geometry_repaired` (invalid polygon fixed with `make_valid`) |
| `measurement.value` | Area (m²) or length (m), measured in the local projection |
| `measurement.perimeter` | Polygons only, including hole boundaries (m) |
| `measurement.projection` | The exact PROJ definition used, so the value is reproducible |
| `measurement.geodesic_value` | The same quantity measured on the WGS84 ellipsoid |
| `measurement.relative_difference` | `abs(value - geodesic_value) / geodesic_value` |

Units are always SI base units (m², m). Converting to hectares or km² is left to the client.

</details>

## Architecture

```
app/
  main.py              FastAPI app: routers, health, pages, static files
  api/                 HTTP layer: endpoints, response schemas, upload size limit
  processing/
    archive.py         Format detection, zip-slip / zip-bomb checks, safe extraction
    readers.py         Reading with GDAL (pyogrio), per-layer CRS, normalization to EPSG:4326
    measure.py         Measurement engine: local LAEA / AEQD + geodesic cross-check
    pipeline.py        process_upload(): read -> measure -> persist (idempotent)
  worker/              Celery app and the processing task
  db/                  SQLAlchemy models (Upload, Feature with PostGIS geometry), sessions
  web/                 Home page, map viewer, shared theme
migrations/            Alembic migrations
scripts/               Sample generator, accuracy benchmark
tests/                 Unit, API, PostGIS cross-check and end-to-end tests
docs/                  Design decisions (ADRs), tickets, accuracy report
```

The processing modules (`archive`, `readers`, `measure`) know nothing about HTTP or the database. They are plain functions and are unit-tested directly. `pipeline.py` is the one place where processing meets persistence, and both the API and the worker call it.

### File-processing flow

```
client ──POST file──▶ API
                        1. Content-Length over the limit ─▶ 413 (body never read)
                        2. extension check ─▶ 415
                        3. save to disk; sniff content; zip-slip, zip-bomb and
                           Shapefile completeness checks ─▶ 400
                        4. INSERT upload (PENDING)
                        5a. ?wait=true and small ─▶ process_upload() in a thread ─▶ 201
                        5b. otherwise ─▶ enqueue Celery task ─▶ 202
                                                  │
                         Redis ◀──────────────────┘
                           │
                        worker: process_upload(upload_id)
                          PROCESSING
                          ├─ extract the archive (re-checked, bytes counted)
                          ├─ for each layer (each .shp, or each KML folder):
                          │    read with pyogrio, resolve the CRS, normalize to EPSG:4326
                          ├─ measure each feature
                          ├─ replace the file's features in one transaction
                          └─ COMPLETED, or FAILED with a readable error
```

- Postgres holds the only copy of each upload's status. Celery's result backend is disabled.
- Tasks are acknowledged only after they finish, so a crashed worker's task is delivered again. Because processing replaces the file's features rather than adding to them, a retry never creates duplicates.
- Transient database errors are retried with backoff. If retries run out, the upload is marked `FAILED`; it never stays stuck in `PROCESSING`.

### Measurement calculation flow

For every feature (`app/processing/measure.py`):

1. **Clean the geometry.** Empty geometries and GeometryCollections become `unsupported` with a reason, and points become `not_applicable`. Z values are dropped, with a warning only when the heights are non-zero.
2. **Find the feature's centre on the sphere.** Average the vertices as 3D unit vectors, then convert back to lon/lat. Averaging raw longitudes would put a Fiji polygon spanning 179.9° and -179.9° at 0°, on the other side of the planet.
3. **Build a local projection there.** Polygons use `+proj=laea`, which is equal-area by construction. Lines and perimeters use `+proj=aeqd`, which keeps distances true near the centre. Centres are snapped to a 0.01° grid so nearby features share cached projections; this makes processing 11x faster and changes results by less than 1e-8.
4. **Validate in the projected plane.** Polygons that are invalid there, such as self-intersecting ones, are repaired with `shapely.make_valid` and flagged `geometry_repaired`.
5. **Measure** the area, perimeter or length of the projected geometry.
6. **Cross-check** the same quantity on the WGS84 ellipsoid with `pyproj.Geod`, and report the `relative_difference`.

### CRS handling

> [!IMPORTANT]
> Measurements never use a file's own CRS directly, even when it is projected. Web Mercator data would be off by 2x or more, and even UTM carries about 4e-4 of scale error.

- **KML and KMZ** are always EPSG:4326, as the KML specification defines.
- **Shapefiles** take their CRS from the `.prj` file. It is reported as an authority code when one matches (for example `EPSG:32643`), and by name otherwise.
- **Normalization:** every geometry is transformed from its source CRS to EPSG:4326, then into its feature's local projection. `always_xy=True` prevents axis-order mix-ups.
- **A missing `.prj`** is handled in one of two ways:
  - If every coordinate is a valid longitude/latitude, the file is treated as EPSG:4326 and marked `crs_assumed: true`, with a warning.
  - Otherwise nothing is guessed. Features are kept with `status: unsupported` and `reason: unknown_crs`.
- **Mixed CRSs** across the layers of one zip are supported. The file reports `crs: MIXED`, and each feature reports its own `crs`.

### Accuracy

[docs/accuracy.md](docs/accuracy.md) is generated by `scripts/benchmark_accuracy.py`. It compares each approach against an exact closed-form ellipsoid area:

![Relative area error by latitude and by feature size for four measurement approaches](docs/accuracy.png)

## Design decisions

Each decision is recorded as an architecture decision record (ADR) in [`docs/adr/`](docs/adr/README.md), with the alternatives that were considered. Domain terms are defined in [`CONTEXT.md`](CONTEXT.md), and the work was planned as tickets in [`docs/tickets/`](docs/tickets/README.md).

| Decision | Alternatives considered | Why |
|---|---|---|
| [FastAPI + SQLAlchemy 2 + Alembic](docs/adr/0001-fastapi-sqlalchemy.md) | Django + DRF + GeoDjango | Typed schemas double as the API contract; small surface; no system GDAL to install |
| [pyogrio + Shapely 2 + pyproj](docs/adr/0002-geo-library-stack.md) | GeoPandas; pyshp + fastkml | pyogrio wheels bundle GDAL, including LIBKML; per-feature transforms don't fit GeoPandas' whole-table `to_crs` |
| [Local LAEA/AEQD per feature + geodesic cross-check](docs/adr/0003-per-feature-local-projection.md) | Web Mercator; UTM zone of the centroid | Exact area at any latitude; no zone edges or polar cases; the error is measured and returned, not hidden |
| [Normalize to EPSG:4326 first; assume WGS84 only when provable](docs/adr/0004-crs-normalization-policy.md) | Reject files without `.prj`; always assume EPSG:4326 | Forgiving for the common case, never silently wrong |
| [Postgres + PostGIS](docs/adr/0005-postgres-postgis.md) | SQLite; Postgres without PostGIS | Native geometry, a spatial index, and an independent geodesic implementation for tests |
| [Celery + Redis, with Postgres as the status record](docs/adr/0006-async-processing-celery.md) | Synchronous; FastAPI BackgroundTasks; a Postgres `SKIP LOCKED` queue | Large files must not hold HTTP requests open; workers scale independently and survive restarts |
| [Upload safety](docs/adr/0007-upload-safety-and-storage.md) | Trusting the archive; object storage | Uploads are untrusted input; a local volume is enough at this scale |
| [Measurements response shape](docs/adr/0008-measurements-response-shape.md) | Bare numbers | Every value carries its method, projection and error estimate |
| [Testing strategy](docs/adr/0009-testing-strategy.md) | Celery eager mode everywhere | Direct function tests plus one real end-to-end run catch queue problems that eager mode would hide |

## Testing

```bash
docker compose up -d db                  # tests use a separate <db>_test database
uv run pytest                            # unit, API and PostGIS cross-check tests
uv run ruff check . && uv run ruff format --check .
uv run mypy app tests scripts            # strict mode

# The full stack, through the real queue and worker:
docker compose up -d --build --wait
E2E_BASE_URL=http://localhost:8000 uv run pytest tests/e2e
```

| Suite | What it checks |
|---|---|
| `test_measure.py` | Areas match a **closed-form WGS84 formula** (no pyproj) at 0° to 89° latitude to within 1e-7; exact equator length; the antimeridian, holes, MultiPolygons, ring orientation, and invalid, 3D, empty and collection inputs |
| `test_readers.py` | Shapefile attributes; the UTM ground-area correction; Web Mercator input; a missing `.prj` (both cases); multi-layer zips; null geometries; nested KML folders; KMZ |
| `test_archive.py` | Zip-slip, absolute paths, zip bombs (declared and actual bytes), entry limits, incomplete Shapefiles, macOS junk files |
| `test_api.py` | Every endpoint and status code; pagination and totals; queueing and queue outages; idempotent reprocessing; the early 413; a regression test that inline processing never blocks other requests |
| `test_postgis_crosscheck.py` | Geodesic values match PostGIS `ST_Area` / `ST_Length` (geography) to within 1e-8 |
| `e2e/test_stack.py` | Every sample file through API, Redis, worker, PostGIS and back |

CI ([`ci.yml`](.github/workflows/ci.yml)) runs all of this on every push, and also checks that the migrations match the models.

## Learnings

- **"Projected" doesn't mean "correct".** Web Mercator is a projected CRS in metres, but its areas are off by `1/cos²(latitude)`. Even UTM, the textbook answer, has a deliberate 0.9996 scale factor, which is about 4e-4 of area error at its central meridian. The [benchmark](docs/accuracy.md) made the size of these errors concrete.
- **Pick a projection per question.** No projection preserves both area and distance. An equal-area projection for areas and an equidistant one for lengths, each centred on the feature, avoids a compromise.
- **Measure your own error.** A geodesic value next to every projected value turns "trust me" into a number, and comparing against PostGIS gives a second, independent opinion. For a 137 km line, AEQD and the geodesic differ by about 1e-6: a real, explainable effect that the API reports instead of hiding.
- **The antimeridian breaks naive code quietly.** Averaging longitudes, checking validity in lon/lat, and drawing on a web map all go wrong for a polygon spanning 179.9° and -179.9°. Doing the work in the local projection fixes most of it in one place.
- **Real files are messy.** KML puts an altitude of 0 on everything, LIBKML adds styling fields to every feature, zips arrive with `__MACOSX` folders, and `.prj` files go missing. Giving each of these a deliberate status, reason or warning made the API predictable.
- **`async def` is a promise not to block.** The first upload endpoint was `async` but did its database work and inline processing synchronously, so a 3 MB `?wait=true` upload froze every other request for 19 seconds. As a plain `def` it runs in FastAPI's thread pool, and a regression test guards it.
- **Profile before optimizing.** The slow part wasn't the geometry maths. Building a pyproj `Transformer` takes about 0.3 ms, and each feature built four of them. Sharing them between nearby features cut 20 s to 1.7 s, with a test proving the results are unchanged.
- **Uploads are untrusted input.** A zip can claim sizes it doesn't have, so extraction counts the bytes it actually writes as well as checking the declared sizes.

## Future scope

- **Object storage** (S3 or MinIO) for uploads, so workers can run on separate hosts.
- **Antimeridian-split GeoJSON output** (RFC 7946 §3.1.9), alongside the current unsplit geometry.
- **Geodesic edge densification** for continent-scale features, so projected values follow geodesic edges exactly. Today the difference, up to about 1e-5 for features hundreds of kilometres across, is reported rather than corrected.
- **More formats:** GeoJSON, GeoPackage, GPX and DXF all come almost free with GDAL.
- **Spatial queries** on stored features, such as bounding-box filters, intersections and overlap between plots. PostGIS is already in place.
- **Unit options** (`?units=ha|acre|km2`) and CSV or GeoJSON export.
- **Operations:** authentication, rate limiting, upload expiry, and metrics such as processing time and queue depth.
- **Large files:** process features in batches instead of reading a whole layer into memory, and report progress as a percentage.
- **Terrain-aware area:** surface area from a digital elevation model, for hilly land where horizontal area understates the real area.
