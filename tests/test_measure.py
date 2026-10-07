"""Known-answer tests for the measurement engine.

Reference values come from closed-form ellipsoid formulas, independent of pyproj, so
these tests check our numbers rather than re-running the same library.
"""

import math

import numpy as np
import pytest
import shapely
from pyproj import Transformer

from app.processing.measure import CENTRE_GRID_DEG, feature_centre, measure

# WGS84
A = 6378137.0
F = 1 / 298.257223563
E2 = F * (2 - F)
E = math.sqrt(E2)


def _q(lat_deg: float) -> float:
    s = math.sin(math.radians(lat_deg))
    return (1 - E2) * (s / (1 - E2 * s * s) - (1 / (2 * E)) * math.log((1 - E * s) / (1 + E * s)))


def ellipsoid_cell_area(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Exact area of the region bounded by two meridians and two parallels on WGS84."""
    return (A * A * math.radians(lon2 - lon1) / 2) * (_q(lat2) - _q(lat1))


def cell(lon1: float, lat1: float, lon2: float, lat2: float) -> shapely.Polygon:
    """A lon/lat box densified so its edges follow parallels and meridians closely."""
    return shapely.segmentize(shapely.box(lon1, lat1, lon2, lat2), 0.0001)


@pytest.mark.parametrize("lat", [0.0, 28.6, 45.0, 70.0, 85.0, 89.0])
def test_area_matches_closed_form_at_every_latitude(lat: float) -> None:
    lon1, lon2, lat1, lat2 = 77.2, 77.21, lat, lat + 0.01
    expected = ellipsoid_cell_area(lon1, lat1, lon2, lat2)

    result = measure(cell(lon1, lat1, lon2, lat2))

    assert result.status == "measured"
    m = result.measurement
    assert m is not None
    assert m.kind == "area" and m.unit == "m2"
    assert m.value == pytest.approx(expected, rel=1e-7)
    assert m.geodesic_value == pytest.approx(expected, rel=1e-7)
    assert m.relative_difference is not None and m.relative_difference < 1e-7


def test_web_mercator_would_double_the_area_at_45_degrees() -> None:
    """Regression guard for the naive approach this service exists to avoid."""
    polygon = cell(10.0, 45.0, 10.01, 45.01)
    to_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x, y = to_3857.transform(*polygon.exterior.xy)
    mercator_area = shapely.Polygon(zip(x, y, strict=True)).area

    true_area = ellipsoid_cell_area(10.0, 45.0, 10.01, 45.01)
    ours = measure(polygon).measurement

    assert mercator_area / true_area == pytest.approx(2.0, rel=0.01)
    assert ours is not None and ours.value == pytest.approx(true_area, rel=1e-7)


def test_equator_length_is_exact() -> None:
    result = measure(shapely.LineString([(0, 0), (1, 0)]))
    m = result.measurement
    assert m is not None and m.kind == "length" and m.unit == "m"
    assert m.value == pytest.approx(A * math.pi / 180, rel=1e-9)
    assert m.geodesic_value == pytest.approx(A * math.pi / 180, rel=1e-9)


def test_meridian_length_matches_geodesic() -> None:
    m = measure(shapely.LineString([(77.0, 28.0), (77.0, 28.1)])).measurement
    assert m is not None
    # Meridian arc of 0.1 degree near 28N is about 11,088 m.
    assert m.value == pytest.approx(11088, rel=1e-3)
    assert m.relative_difference is not None and m.relative_difference < 1e-6


def test_multilinestring_sums_parts() -> None:
    a = shapely.LineString([(0, 0), (0.5, 0)])
    b = shapely.LineString([(0.5, 0), (1, 0)])
    m = measure(shapely.MultiLineString([a, b])).measurement
    assert m is not None and m.value == pytest.approx(A * math.pi / 180, rel=1e-9)


def test_feature_crossing_the_antimeridian() -> None:
    east = shapely.Polygon([(179.995, 10), (180, 10), (180, 10.01), (179.995, 10.01)])
    crossing = shapely.Polygon([(179.995, 10), (-179.995, 10), (-179.995, 10.01), (179.995, 10.01)])
    expected = 2 * ellipsoid_cell_area(179.995, 10, 180, 10.01)

    centre_lon, _ = feature_centre(crossing)
    m = measure(crossing).measurement

    assert abs(abs(centre_lon) - 180) < 0.01
    assert m is not None
    assert m.value == pytest.approx(expected, rel=1e-6)
    assert m.geodesic_value == pytest.approx(expected, rel=1e-6)
    assert measure(east).measurement is not None


def test_polygon_with_hole_subtracts_hole_and_counts_its_perimeter() -> None:
    outer = cell(77.2, 28.6, 77.22, 28.62)
    hole = cell(77.205, 28.605, 77.21, 28.61)
    polygon = shapely.Polygon(outer.exterior.coords, [hole.exterior.coords])

    m = measure(polygon).measurement
    plain = measure(outer).measurement
    hole_m = measure(hole).measurement

    assert m is not None and plain is not None and hole_m is not None
    assert m.value == pytest.approx(plain.value - hole_m.value, rel=1e-9)
    assert m.perimeter == pytest.approx((plain.perimeter or 0) + (hole_m.perimeter or 0), rel=1e-9)
    assert m.geodesic_perimeter == pytest.approx(m.perimeter, rel=1e-6)


def test_multipolygon_sums_parts() -> None:
    a = cell(77.2, 28.6, 77.21, 28.61)
    b = cell(77.3, 28.7, 77.31, 28.71)
    m = measure(shapely.MultiPolygon([a, b])).measurement
    expected = ellipsoid_cell_area(77.2, 28.6, 77.21, 28.61) + ellipsoid_cell_area(77.3, 28.7, 77.31, 28.71)
    assert m is not None and m.value == pytest.approx(expected, rel=1e-6)


def test_irregular_survey_plot_agrees_with_geodesic() -> None:
    # A 7-vertex agricultural plot near Pune, India (about 2.4 ha).
    plot = shapely.Polygon(
        [
            (73.85612, 18.52043),
            (73.85771, 18.52051),
            (73.85802, 18.51968),
            (73.85745, 18.51902),
            (73.85651, 18.51911),
            (73.85598, 18.51960),
            (73.85612, 18.52043),
        ]
    )
    m = measure(plot).measurement
    assert m is not None
    assert 20_000 < m.value < 30_000
    assert m.relative_difference is not None and m.relative_difference < 1e-7
    assert m.perimeter == pytest.approx(m.geodesic_perimeter, rel=1e-6)


def test_clockwise_and_counter_clockwise_give_the_same_area() -> None:
    polygon = cell(77.2, 28.6, 77.21, 28.61)
    reversed_polygon = shapely.Polygon(list(polygon.exterior.coords)[::-1])
    a = measure(polygon).measurement
    b = measure(reversed_polygon).measurement
    assert a is not None and b is not None
    assert a.value == pytest.approx(b.value) and a.geodesic_value == pytest.approx(b.geodesic_value)


def test_self_intersecting_polygon_is_repaired_with_warning() -> None:
    bowtie = shapely.Polygon([(77.2, 28.6), (77.21, 28.61), (77.21, 28.6), (77.2, 28.61)])
    result = measure(bowtie)
    assert result.status == "measured"
    assert "geometry_repaired" in result.warnings
    assert result.geometry is not None and result.geometry.is_valid
    m = result.measurement
    # Two triangles, each a quarter of the 0.01 degree cell.
    expected = ellipsoid_cell_area(77.2, 28.6, 77.21, 28.61) / 2
    assert m is not None and m.value == pytest.approx(expected, rel=1e-3)


def test_real_heights_are_dropped_with_warning() -> None:
    result = measure(shapely.LineString([(0, 0, 120), (1, 0, 130)]))
    assert result.status == "measured"
    assert result.warnings == ["z_dropped"]
    assert result.geometry is not None and not result.geometry.has_z


def test_zero_heights_are_dropped_silently() -> None:
    result = measure(shapely.Polygon([(0, 0, 0), (0.01, 0, 0), (0.01, 0.01, 0), (0, 0, 0)]))
    assert result.status == "measured"
    assert result.warnings == []


def test_points_are_not_applicable() -> None:
    for geom in (shapely.Point(77, 28), shapely.MultiPoint([(77, 28), (78, 29)])):
        result = measure(geom)
        assert result.status == "not_applicable"
        assert result.measurement is None


def test_empty_geometry_is_unsupported() -> None:
    result = measure(shapely.Polygon())
    assert result.status == "unsupported"
    assert result.reason == "empty_geometry"


def test_geometry_collection_is_unsupported_not_an_error() -> None:
    gc = shapely.GeometryCollection([shapely.Point(0, 0), shapely.LineString([(0, 0), (1, 1)])])
    result = measure(gc)
    assert result.status == "unsupported"
    assert result.reason == "geometry_collection_not_supported"


def test_zero_length_line_has_no_relative_difference() -> None:
    m = measure(shapely.LineString([(1, 1), (1, 1)])).measurement
    assert m is not None and m.value == 0 and m.relative_difference is None


def test_large_feature_reports_its_projection_error() -> None:
    m = measure(cell(0, 0, 20, 20)).measurement
    assert m is not None
    # Straight edges in LAEA vs geodesic edges differ for a 2,000 km box; the difference is
    # reported, not hidden, and stays small.
    assert m.relative_difference is not None and 0 < m.relative_difference < 1e-2


def test_projection_string_is_centred_on_the_feature() -> None:
    m = measure(cell(77.2, 28.6, 77.21, 28.61)).measurement
    assert m is not None
    assert "+proj=laea" in m.projection
    params = dict(part.lstrip("+").split("=") for part in m.projection.split() if "=" in part)
    # Centres snap to a 0.01 degree grid so nearby features share transformers.
    assert float(params["lat_0"]) == pytest.approx(28.605, abs=CENTRE_GRID_DEG / 2 + 1e-9)
    assert float(params["lon_0"]) == pytest.approx(77.205, abs=CENTRE_GRID_DEG / 2 + 1e-9)


def test_snapping_the_centre_does_not_change_the_result() -> None:
    """Measure with the exact centre and with the snapped one; results must agree."""
    plot = cell(77.2031, 28.6047, 77.2112, 28.6118)
    route = shapely.LineString([(77.2031, 28.6047), (77.2389, 28.6342), (77.2601, 28.6503)])

    for geom, area in ((plot, True), (route, False)):
        snapped = measure(geom).measurement
        assert snapped is not None
        lon, lat = feature_centre(geom)
        exact_proj = f"+proj={'laea' if area else 'aeqd'} +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m"
        t = Transformer.from_crs("EPSG:4326", exact_proj, always_xy=True)
        projected = shapely.transform(geom, lambda c, t=t: np.column_stack(t.transform(c[:, 0], c[:, 1])))
        exact = projected.area if area else projected.length
        assert snapped.value == pytest.approx(exact, rel=1e-8)
