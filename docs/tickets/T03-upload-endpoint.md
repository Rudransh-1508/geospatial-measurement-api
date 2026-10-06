# T03 - Upload endpoint with validation and zip safety

**ADRs:** 0006, 0007

## Scope
- `POST /api/files/` multipart `file`, optional `?wait=true`.
- Extension + content sniffing; 415 for unsupported types.
- Streamed write with 413 above `MAX_UPLOAD_BYTES`.
- Zip safety checks (zip-slip, zip bomb), Shapefile completeness (.shp/.shx/.dbf), 400 with clear messages.
- Creates upload row `PENDING`, enqueues the task, returns 202 with upload info.

## Acceptance
- Tests: valid zip/kml/kmz accepted; wrong type 415; oversize 413; zip-slip, zip bomb, incomplete shapefile 400.
