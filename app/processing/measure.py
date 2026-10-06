"""Measurement engine.

Every measurable feature is projected into its own local projection centred on the
feature (ADR 0003):

- areas use Lambert Azimuthal Equal-Area (LAEA), which preserves area exactly;
- lengths and perimeters use Azimuthal Equidistant (AEQD), which keeps distortion
  negligible near the centre.

The same quantity is also computed on the WGS84 ellipsoid with ``pyproj.Geod`` and the
relative difference is reported, so projection error is visible per feature.

Input geometries must already be normalized to EPSG:4326 (lon/lat, x = longitude).
"""

from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache

import numpy as np
import shapely
from numpy.typing import NDArray
from pyproj import Geod, Transformer
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient

GEOD = Geod(ellps="WGS84")

AREA_TYPES = frozenset({"Polygon", "MultiPolygon"})
LENGTH_TYPES = frozenset({"LineString", "MultiLineString", "LinearRing"})
POINT_TYPES = frozenset({"Point", "MultiPoint"})


class Kind(StrEnum):
    AREA = "area"
    LENGTH = "length"


class Method(StrEnum):
    LOCAL_LAEA = "local_laea"
    LOCAL_AEQD = "local_aeqd"


class FeatureWarning(StrEnum):
    Z_DROPPED = "z_dropped"
    GEOMETRY_REPAIRED = "geometry_repaired"


class Reason(StrEnum):
    EMPTY_GEOMETRY = "empty_geometry"
    GEOMETRY_COLLECTION = "geometry_collection_not_supported"
    INVALID_GEOMETRY = "invalid_geometry_unrepairable"
    UNKNOWN_GEOMETRY_TYPE = "unknown_geometry_type"


@dataclass(frozen=True)
class Measurement:
    kind: Kind
    value: float
    unit: str
    method: Method
    projection: str
    geodesic_value: float
    relative_difference: float | None
    perimeter: float | None = None
    geodesic_perimeter: float | None = None


@dataclass(frozen=True)
class MeasureResult:
    """Outcome of measuring one feature.

    ``geometry`` is the cleaned lon/lat geometry (2D, repaired if it was invalid) and is
    what should be stored and displayed.
    """

    status: str  # "measured" | "not_applicable" | "unsupported"
    geometry: BaseGeometry | None
    measurement: Measurement | None = None
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


def feature_centre(geom: BaseGeometry) -> tuple[float, float]:
    """Return (lon, lat) of the spherical mean of the geometry's vertices.

    Averaging unit vectors on the sphere instead of raw longitudes keeps the centre
    correct for features that cross the antimeridian (e.g. 179.9 and -179.9 average to
    180, not 0).
    """
    coords = shapely.get_coordinates(geom)
    lon = np.radians(coords[:, 0])
    lat = np.radians(coords[:, 1])
    x = np.cos(lat) * np.cos(lon)
    y = np.cos(lat) * np.sin(lon)
    z = np.sin(lat)
    mx, my, mz = x.mean(), y.mean(), z.mean()
    norm = float(np.sqrt(mx * mx + my * my + mz * mz))
    if norm < 1e-12:
        # Vertices spread evenly around the globe; any centre is as good as another.
        return 0.0, 0.0
    centre_lon = float(np.degrees(np.arctan2(my, mx)))
    centre_lat = float(np.degrees(np.arcsin(mz / norm)))
    return centre_lon, centre_lat


def local_projection(method: Method, lon: float, lat: float) -> str:
    proj = "laea" if method is Method.LOCAL_LAEA else "aeqd"
    return f"+proj={proj} +lat_0={lat:.6f} +lon_0={lon:.6f} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"


@lru_cache(maxsize=4096)
def _transformers(projection: str) -> tuple[Transformer, Transformer]:
    forward = Transformer.from_crs("EPSG:4326", projection, always_xy=True)
    inverse = Transformer.from_crs(projection, "EPSG:4326", always_xy=True)
    return forward, inverse


def _apply(transformer: Transformer, geom: BaseGeometry) -> BaseGeometry:
    def fn(coords: NDArray[np.float64]) -> NDArray[np.float64]:
        x, y = transformer.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    return shapely.transform(geom, fn)


# Below this (metres or square metres) a reference value is floating-point noise.
_NEGLIGIBLE = 1e-6


def _relative_difference(projected: float, geodesic: float) -> float | None:
    if abs(geodesic) < _NEGLIGIBLE:
        return None
    return abs(projected - geodesic) / abs(geodesic)


def _oriented(geom: BaseGeometry) -> BaseGeometry:
    """Counter-clockwise exteriors, clockwise holes: what pyproj.Geod expects for a positive area."""
    if isinstance(geom, shapely.Polygon):
        return orient(geom, sign=1.0)
    if isinstance(geom, shapely.MultiPolygon):
        return shapely.MultiPolygon([orient(p, sign=1.0) for p in geom.geoms])
    return geom


def _polygonal_part(geom: BaseGeometry) -> BaseGeometry:
    """Keep only polygons from the output of make_valid (which may yield a collection)."""
    if geom.geom_type in AREA_TYPES:
        return geom
    if isinstance(geom, shapely.GeometryCollection):
        polys: list[shapely.Polygon] = []
        for part in geom.geoms:
            if isinstance(part, shapely.Polygon):
                polys.append(part)
            elif isinstance(part, shapely.MultiPolygon):
                polys.extend(part.geoms)
        if polys:
            return shapely.MultiPolygon(polys) if len(polys) > 1 else polys[0]
    return shapely.Polygon()


def _measure_area(geom: BaseGeometry, warnings: list[str]) -> MeasureResult:
    lon, lat = feature_centre(geom)
    area_proj = local_projection(Method.LOCAL_LAEA, lon, lat)
    length_proj = local_projection(Method.LOCAL_AEQD, lon, lat)
    to_laea, from_laea = _transformers(area_proj)

    projected = _apply(to_laea, geom)
    # Validity is checked in the projected plane: that is the plane where edges are
    # straight lines, and it stays continuous across the antimeridian.
    if not projected.is_valid:
        repaired = _polygonal_part(shapely.make_valid(projected, method="structure"))
        if repaired.is_empty:
            return MeasureResult(
                status="unsupported", geometry=geom, reason=Reason.INVALID_GEOMETRY, warnings=warnings
            )
        projected = repaired
        geom = _apply(from_laea, projected)
        warnings = [*warnings, FeatureWarning.GEOMETRY_REPAIRED]

    to_aeqd, _ = _transformers(length_proj)
    perimeter = float(_apply(to_aeqd, geom).boundary.length)
    area = float(projected.area)

    geodesic_area = abs(GEOD.geometry_area_perimeter(_oriented(geom))[0])
    # Geod's own perimeter covers exterior rings only; measure every ring so holes count
    # the same way as in the projected perimeter.
    geodesic_perimeter = GEOD.geometry_length(geom.boundary)

    return MeasureResult(
        status="measured",
        geometry=geom,
        warnings=warnings,
        measurement=Measurement(
            kind=Kind.AREA,
            value=area,
            unit="m2",
            method=Method.LOCAL_LAEA,
            projection=area_proj,
            geodesic_value=geodesic_area,
            relative_difference=_relative_difference(area, geodesic_area),
            perimeter=perimeter,
            geodesic_perimeter=float(geodesic_perimeter),
        ),
    )


def _measure_length(geom: BaseGeometry, warnings: list[str]) -> MeasureResult:
    lon, lat = feature_centre(geom)
    projection = local_projection(Method.LOCAL_AEQD, lon, lat)
    to_aeqd, _ = _transformers(projection)
    length = float(_apply(to_aeqd, geom).length)
    geodesic_length = float(GEOD.geometry_length(geom))
    return MeasureResult(
        status="measured",
        geometry=geom,
        warnings=warnings,
        measurement=Measurement(
            kind=Kind.LENGTH,
            value=length,
            unit="m",
            method=Method.LOCAL_AEQD,
            projection=projection,
            geodesic_value=geodesic_length,
            relative_difference=_relative_difference(length, geodesic_length),
        ),
    )


def measure(geom: BaseGeometry) -> MeasureResult:
    """Measure one lon/lat geometry. Never raises for unsupported input."""
    warnings: list[str] = []

    if geom.is_empty:
        return MeasureResult(status="unsupported", geometry=None, reason=Reason.EMPTY_GEOMETRY)

    if shapely.has_z(geom):
        z = shapely.get_coordinates(geom, include_z=True)[:, 2]
        # Flat KML files carry altitude 0 everywhere; only real heights are worth a warning.
        if np.any(np.nan_to_num(z) != 0):
            warnings.append(FeatureWarning.Z_DROPPED)
        geom = shapely.force_2d(geom)

    geom_type = geom.geom_type
    if geom_type in AREA_TYPES:
        return _measure_area(geom, warnings)
    if geom_type in LENGTH_TYPES:
        if geom_type == "LinearRing":
            geom = shapely.LineString(geom.coords)
        return _measure_length(geom, warnings)
    if geom_type in POINT_TYPES:
        return MeasureResult(status="not_applicable", geometry=geom, warnings=warnings)
    if geom_type == "GeometryCollection":
        return MeasureResult(
            status="unsupported", geometry=geom, reason=Reason.GEOMETRY_COLLECTION, warnings=warnings
        )
    return MeasureResult(
        status="unsupported", geometry=geom, reason=Reason.UNKNOWN_GEOMETRY_TYPE, warnings=warnings
    )
