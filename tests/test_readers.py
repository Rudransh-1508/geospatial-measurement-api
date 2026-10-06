from pathlib import Path

import pytest
import shapely
from pyproj import CRS, Proj, Transformer

from app.db.models import FileFormat
from app.processing.archive import ArchiveLimits
from app.processing.measure import measure
from app.processing.readers import UnreadableFileError, read_upload
from tests.factories import (
    folder,
    placemark,
    shapefile_zip,
    write_kml,
    write_kmz,
    write_shapefile,
    zip_files,
)

LIMITS = ArchiveLimits(max_uncompressed_bytes=50 * 1024 * 1024, max_compression_ratio=200, max_entries=100)


def test_shapefile_attributes_crs_and_types(tmp_path: Path) -> None:
    path = shapefile_zip(
        tmp_path,
        [shapely.box(77.2, 28.6, 77.21, 28.61), shapely.box(77.3, 28.6, 77.31, 28.61)],
        properties=[{"name": "Plot A", "owner": "Ravi"}, {"name": "Plot B", "owner": None}],
        name="plots",
    )
    result = read_upload(path, FileFormat.SHAPEFILE, LIMITS)

    assert result.layers == ["plots"]
    assert result.source_crs == "EPSG:4326"
    assert result.crs_assumed is False
    assert [f.index for f in result.features] == [0, 1]
    first = result.features[0]
    assert first.layer == "plots"
    assert first.source_crs == "EPSG:4326"
    assert first.source_geometry_type == "Polygon"
    assert first.properties == {"name": "Plot A", "owner": "Ravi"}
    assert result.features[1].properties == {"name": "Plot B", "owner": None}


def test_projected_shapefile_is_normalized_and_measured_on_the_ground(tmp_path: Path) -> None:
    """A 100 m x 100 m square in UTM grid units is not 10,000 m2 on the ground.

    UTM scales distances by up to 0.9996 at the central meridian and more elsewhere. The
    true ground area is the grid area divided by the projection's areal scale factor.
    """
    utm = CRS.from_epsg(32643)  # UTM 43N, covers much of western India
    to_utm = Transformer.from_crs("EPSG:4326", utm, always_xy=True)
    x0, y0 = to_utm.transform(73.8567, 18.5204)  # Pune
    square = shapely.box(x0, y0, x0 + 100, y0 + 100)

    path = shapefile_zip(tmp_path, [square], properties=[{"id": 1}], crs="EPSG:32643", name="utm")
    result = read_upload(path, FileFormat.SHAPEFILE, LIMITS)

    assert result.source_crs == "EPSG:32643"
    geom = result.features[0].geometry
    assert geom is not None
    minx, miny, _, _ = geom.bounds
    assert 73.8 < minx < 73.9 and 18.5 < miny < 18.6

    areal_scale = Proj(utm).get_factors(73.8572, 18.5208).areal_scale
    m = measure(geom).measurement
    assert m is not None
    assert m.value == pytest.approx(10_000 / areal_scale, rel=1e-5)
    assert m.value != pytest.approx(10_000, rel=1e-5)


def test_web_mercator_shapefile_is_measured_correctly(tmp_path: Path) -> None:
    to_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    box = shapely.segmentize(shapely.box(10.0, 45.0, 10.01, 45.01), 0.0005)
    projected = shapely.Polygon(zip(*to_3857.transform(*box.exterior.xy), strict=True))

    path = shapefile_zip(tmp_path, [projected], crs="EPSG:3857", name="merc")
    result = read_upload(path, FileFormat.SHAPEFILE, LIMITS)
    m = measure(result.features[0].geometry).measurement

    assert result.source_crs == "EPSG:3857"
    assert m is not None
    # Naive Web Mercator area is about 2x too large at 45 degrees; ours is not.
    assert projected.area / m.value == pytest.approx(2.0, rel=0.01)


def test_missing_prj_with_lonlat_coordinates_is_assumed_wgs84(tmp_path: Path) -> None:
    path = shapefile_zip(tmp_path, [shapely.box(77.2, 28.6, 77.21, 28.61)], drop=(".prj",))
    result = read_upload(path, FileFormat.SHAPEFILE, LIMITS)

    assert result.crs_assumed is True
    assert result.source_crs == "EPSG:4326"
    assert any(w.startswith("crs_assumed") for w in result.warnings)
    assert result.features[0].geometry is not None


def test_missing_prj_with_projected_coordinates_is_not_guessed(tmp_path: Path) -> None:
    path = shapefile_zip(tmp_path, [shapely.box(500_000, 2_000_000, 500_100, 2_000_100)], drop=(".prj",))
    result = read_upload(path, FileFormat.SHAPEFILE, LIMITS)

    assert result.crs_assumed is False
    assert result.source_crs is None
    feature = result.features[0]
    assert feature.geometry is None
    assert feature.reason == "unknown_crs"


def test_multi_layer_zip_with_subfolder(tmp_path: Path) -> None:
    src = tmp_path / "src"
    plots = write_shapefile(src, "plots", [shapely.box(77.2, 28.6, 77.21, 28.61)])
    roads = write_shapefile(src / "network", "roads", [shapely.LineString([(77.2, 28.6), (77.3, 28.7)])])
    path = zip_files(tmp_path / "multi.zip", [*plots, *roads], src)

    result = read_upload(path, FileFormat.SHAPEFILE, LIMITS)

    assert sorted(result.layers) == ["plots", "roads"]
    assert {f.layer for f in result.features} == {"plots", "roads"}
    assert sorted(f.index for f in result.features) == [0, 1]


def test_null_geometry_is_kept_with_reason(tmp_path: Path) -> None:
    path = shapefile_zip(tmp_path, [shapely.Point(77, 28), None], properties=[{"n": 1}, {"n": 2}], name="pts")
    result = read_upload(path, FileFormat.SHAPEFILE, LIMITS)
    assert len(result.features) == 2
    assert result.features[1].geometry is None
    assert result.features[1].reason == "missing_geometry"


def test_kml_nested_folders_and_extended_data(tmp_path: Path) -> None:
    path = write_kml(
        tmp_path / "survey.kml",
        folder(
            "Plots",
            placemark("Plot A", shapely.box(77.2, 28.6, 77.21, 28.61), {"owner": "Ravi"}),
            folder("Roads", placemark("Main road", shapely.LineString([(77.2, 28.6), (77.3, 28.7)]))),
        ),
        placemark("Well", shapely.Point(77.25, 28.65)),
    )
    result = read_upload(path, FileFormat.KML, LIMITS)

    assert result.source_crs == "EPSG:4326"
    assert set(result.layers) >= {"Plots", "Roads"}
    by_name = {f.properties.get("Name"): f for f in result.features}
    assert set(by_name) == {"Plot A", "Main road", "Well"}
    assert by_name["Plot A"].properties == {"Name": "Plot A", "owner": "Ravi"}
    assert by_name["Plot A"].layer == "Plots"
    assert by_name["Main road"].layer == "Roads"
    assert by_name["Main road"].source_geometry_type == "LineString"


def test_kml_polygon_with_hole(tmp_path: Path) -> None:
    polygon = shapely.Polygon(
        shapely.box(77.2, 28.6, 77.22, 28.62).exterior.coords,
        [shapely.box(77.205, 28.605, 77.21, 28.61).exterior.coords],
    )
    path = write_kml(tmp_path / "hole.kml", placemark("Holed", polygon))
    result = read_upload(path, FileFormat.KML, LIMITS)
    geom = result.features[0].geometry
    assert geom is not None and len(geom.interiors) == 1


def test_kmz(tmp_path: Path) -> None:
    path = write_kmz(tmp_path / "survey.kmz", placemark("Plot", shapely.box(77.2, 28.6, 77.21, 28.61)))
    result = read_upload(path, FileFormat.KMZ, LIMITS)
    assert len(result.features) == 1
    assert result.features[0].properties["Name"] == "Plot"


def test_unreadable_kml(tmp_path: Path) -> None:
    path = tmp_path / "broken.kml"
    path.write_text("<kml><Document><Placemark>")
    with pytest.raises(UnreadableFileError):
        read_upload(path, FileFormat.KML, LIMITS)
