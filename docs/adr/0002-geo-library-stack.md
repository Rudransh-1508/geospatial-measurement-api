# 0002 - pyogrio + Shapely 2 + pyproj, no GeoPandas

## Context
We must read zipped Shapefiles and KML/KMZ, then transform and measure each feature with its own projection (see ADR 0003).

## Options considered
- **GeoPandas** - convenient, but heavy and dataframe-wide; `to_crs` applies one CRS to the whole frame, which fights per-feature projections.
- **pyogrio + Shapely 2 + pyproj** - pyogrio wheels bundle GDAL (Shapefile and KML drivers) so `pip install` is enough; Shapely 2 for geometry ops; pyproj for CRS, transforms and ellipsoidal (geodesic) maths.
- **Hand-rolled parsers (pyshp + fastkml)** - no GDAL, but we would reimplement CRS parsing, encodings and many format edge cases.

## Decision
pyogrio for reading, Shapely 2 for geometry, pyproj for CRS/transform/geodesic.

## Consequences
- No system dependencies; works the same in Docker and on a laptop.
- Per-feature transforms are explicit code we own and can test.
- KML support depends on the GDAL KML driver bundled in the pyogrio wheel; covered by fixture tests.
