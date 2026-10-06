# T07 - File info and measurements endpoints

**ADRs:** 0008

## Scope
- `GET /api/files/{id}/` upload info (404 unknown, 422 malformed id).
- `GET /api/files/{id}/measurements/` with pagination, totals, per-feature provenance; 409 if not COMPLETED.
- `GET /api/files/` list (small extra).

## Acceptance
- API tests cover all status codes and the response shape in ADR 0008.
