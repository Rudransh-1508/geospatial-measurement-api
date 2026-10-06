# 0004 - CRS normalization and missing-CRS policy

## Context
Files arrive in many CRSs: geographic (EPSG:4326), national grids, UTM, Web Mercator, or none at all (Shapefile without `.prj`). KML is always EPSG:4326 by specification.

## Decision
- Every feature is transformed from its source CRS to EPSG:4326 (the **normalized geometry**), then into its own local projection (ADR 0003). We never measure in the source CRS, even if it is projected, because projected source CRSs can carry large scale distortion (Web Mercator).
- Transforms use `always_xy=True` to avoid axis-order bugs.
- Missing CRS (no `.prj`):
  - If every coordinate fits lon ∈ [-180, 180] and lat ∈ [-90, 90], assume EPSG:4326, set `crs_assumed: true`, add warning `crs_assumed`.
  - Otherwise, do not guess: features get `status: unsupported`, reason `unknown_crs`. The upload still completes with feature extraction.
- The upload's reported `crs` is the source CRS as an authority code when one matches (e.g. `EPSG:32643`), otherwise its WKT name.

## Options considered
- Reject files without `.prj` - strict, but unhelpful for the very common lon/lat case.
- Always assume EPSG:4326 - silently wrong for projected data. Rejected.

## Consequences
- Forgiving for the common case, transparent about assumptions, never silently wrong.
