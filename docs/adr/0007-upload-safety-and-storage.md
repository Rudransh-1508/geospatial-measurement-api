# 0007 - Upload validation, zip safety, and file storage

## Decision
- Accepted: `.zip` (Shapefile), `.kml`, `.kmz`. Detected by extension and verified by content (zip magic bytes, KML root element).
- Max upload size 50 MB (setting `MAX_UPLOAD_BYTES`). Starlette parses the whole multipart body before an endpoint runs, so the limit is enforced in two places: a small ASGI middleware rejects requests whose `Content-Length` exceeds it before any body is read, and the endpoint re-checks the bytes actually received for bodies sent without a `Content-Length`.
- Zip safety on `.zip` and `.kmz`:
  - Reject entries with absolute paths or `..` (zip-slip).
  - Reject archives whose total uncompressed size exceeds 500 MB or whose compression ratio is extreme (zip bomb).
  - Ignore `__MACOSX/` and dotfiles.
- Shapefile zip must contain at least one `.shp` with matching `.shx` and `.dbf`. Multiple `.shp` files become multiple layers; each feature records its `layer`.
- Original upload stored on a local volume at `{UPLOAD_DIR}/{upload_id}/{original_filename}`; path saved on the upload row.
- Validation failures that are detectable at upload time return `400`/`413`/`415` immediately. Failures only detectable while reading (corrupt DBF, unreadable KML) mark the upload `FAILED` with a reason.

## Options considered
- Object storage (S3/MinIO) - right for multi-host production, unnecessary here. Listed as future scope.

## Consequences
- Hostile archives cannot write outside the extraction directory or exhaust disk.
- Storage is local; scaling workers across hosts would require shared storage (future scope).
