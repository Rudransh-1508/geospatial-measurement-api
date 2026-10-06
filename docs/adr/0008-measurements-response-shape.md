# 0008 - Measurements response shape

## Decision
`GET /api/files/{id}/measurements/?limit=100&offset=0`

```json
{
  "file_id": "…",
  "status": "COMPLETED",
  "crs": "EPSG:4326",
  "crs_assumed": false,
  "totals": {
    "feature_count": 120,
    "by_geometry_type": {"Polygon": 80, "LineString": 30, "Point": 10},
    "by_status": {"measured": 110, "not_applicable": 10},
    "area_m2": 1234567.8,
    "length_m": 45678.9
  },
  "pagination": {"limit": 100, "offset": 0, "total": 120},
  "features": [
    {
      "id": 0,
      "layer": "plots",
      "geometry_type": "Polygon",
      "crs": "EPSG:4326",
      "properties": {"name": "Plot A"},
      "geometry": {"type": "Polygon", "coordinates": [[…]]},
      "status": "measured",
      "reason": null,
      "warnings": [],
      "measurement": {
        "kind": "area",
        "value": 10000.12,
        "unit": "m2",
        "perimeter": 400.01,
        "perimeter_unit": "m",
        "method": "local_laea",
        "projection": "+proj=laea +lat_0=28.61 +lon_0=77.20 +datum=WGS84 +units=m",
        "geodesic_value": 10000.10,
        "geodesic_perimeter": 400.01,
        "relative_difference": 2e-6
      }
    }
  ]
}
```

- `geometry` is GeoJSON in EPSG:4326 (RFC 7946 mandates WGS84). The source CRS is reported at file level and per feature.
- Units are SI base units only (`m2`, `m`). Conversions are the client's concern.
- `status` per feature: `measured`, `not_applicable` (points), `unsupported` (with `reason`).
- Each feature reports the `crs` of its source layer, as the assignment asks for per-feature CRS.
- Perimeters include hole boundaries; the geodesic perimeter is measured the same way.
- `?include_geometry=false` drops geometries for lightweight listing.
- Totals are computed over all features, not the current page.
- If the upload is not `COMPLETED`, the endpoint returns `409` with the current status.

## Consequences
- Every measured value carries its provenance (method + projection) and its error estimate.
