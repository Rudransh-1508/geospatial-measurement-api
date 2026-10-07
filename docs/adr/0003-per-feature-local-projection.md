# 0003 - Per-feature local projection with geodesic cross-check

## Context
Areas and lengths must not be computed in degrees. The assignment requires transforming to a projected CRS first and leaves the strategy to us. Input can be anywhere on Earth, including near the poles and across the antimeridian.

## Options considered
- **(a) One global projection (e.g. Web Mercator EPSG:3857)** - simple, but area error grows with latitude (about 2x at 45°, unbounded toward the poles). Rejected.
- **(b) UTM zone of the feature centroid** - common and accurate inside a zone. Degrades for features spanning zones, undefined beyond 84°N/80°S (needs UPS), awkward at the antimeridian.
- **(c) Local projection centred on each feature** - LAEA for area (equal-area by construction, so area is exact regardless of location), AEQD for length (true distances from the centre, low distortion nearby). No zones, no polar special cases.
- **(d) (c) plus a geodesic cross-check** - also compute the measurement directly on the WGS84 ellipsoid with `pyproj.Geod` and report the relative difference.

## Decision
(d).
- Polygon area and perimeter: `+proj=laea +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m`.
- Line length: `+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m`.
- Centre: spherical centroid of the vertices (mean of 3D unit vectors, converted back to lon/lat), so a feature crossing ±180° gets a centre near ±180°, not near 0°. The centre is snapped to a 0.01° grid (about 1 km) so nearby features share cached transformers. This has no cost in accuracy: LAEA is equal-area for any centre, and moving the AEQD centre by up to about 1 km changes lengths by about 1e-9 (covered by a test).
- Geodesic reference: `Geod(ellps="WGS84").geometry_area_perimeter` / `geometry_length`.
- Returned per feature: projected `value`, `geodesic_value`, `relative_difference`, `method`, and the exact proj string.

## Consequences
- Every number is reproducible: the response says exactly which projection produced it.
- Projection error is visible per feature instead of hidden.
- Edge interpretation: a projection connects vertices with straight lines in projected space, `Geod` with geodesics. For small features this is negligible; for continent-scale features the difference shows up in `relative_difference`. Documented, not hidden.
- Building a pyproj Transformer costs about 0.3 ms, which dominated processing time before centres were snapped to a grid. With snapping, 12,000 nearby features are measured in about 1.7 s instead of 20 s.
