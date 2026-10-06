# T04 - Shapefile and KML/KMZ readers with CRS normalization

**ADRs:** 0002, 0004

## Scope
- Safe extraction to a temp dir; read each layer with pyogrio.
- Produce `RawFeature(index, layer, geometry, properties, source_crs)`; JSON-safe properties (dates, decimals, bytes).
- Normalize to EPSG:4326 with `always_xy=True`.
- Missing `.prj` policy: assume 4326 if all coordinates in range, else mark `unknown_crs`.
- KML nested folders and KMZ.

## Acceptance
- Tests for multi-layer zip, projected Shapefile (UTM) round-trip, missing `.prj` both branches, KML with folders, KMZ.
