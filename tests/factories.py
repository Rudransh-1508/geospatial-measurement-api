"""Build real Shapefile / KML / KMZ files in tests, so fixtures are readable code, not binaries."""

import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import numpy as np
import pyogrio.raw
import shapely
from shapely.geometry.base import BaseGeometry


def write_shapefile(
    directory: Path,
    name: str,
    geometries: Sequence[BaseGeometry | None],
    *,
    properties: Sequence[dict[str, Any]] | None = None,
    crs: str | None = "EPSG:4326",
    geometry_type: str | None = None,
) -> list[Path]:
    """Write a Shapefile and return the paths of all its parts."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.shp"
    properties = properties or [{} for _ in geometries]
    field_names = sorted({k for p in properties for k in p})
    field_data = [np.array([p.get(f) for p in properties], dtype=object) for f in field_names]
    wkb = np.array([shapely.to_wkb(g) if g is not None else None for g in geometries], dtype=object)
    if geometry_type is None:
        first = next(g for g in geometries if g is not None)
        geometry_type = first.geom_type
    pyogrio.raw.write(
        path,
        geometry=wkb,
        field_data=field_data,
        fields=field_names,
        driver="ESRI Shapefile",
        geometry_type=geometry_type,
        crs=crs,
    )
    return sorted(directory.glob(f"{name}.*"))


def zip_files(
    zip_path: Path, files: Sequence[Path], base: Path, extra: dict[str, bytes] | None = None
) -> Path:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.relative_to(base).as_posix())
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return zip_path


def shapefile_zip(
    tmp: Path,
    geometries: Sequence[BaseGeometry | None],
    *,
    properties: Sequence[dict[str, Any]] | None = None,
    crs: str | None = "EPSG:4326",
    name: str = "layer",
    drop: Sequence[str] = (),
) -> Path:
    """One-layer Shapefile zip. ``drop`` removes parts, e.g. ('.prj',)."""
    src = tmp / f"src-{name}"
    parts = write_shapefile(src, name, geometries, properties=properties, crs=crs)
    parts = [p for p in parts if p.suffix not in drop]
    return zip_files(tmp / f"{name}.zip", parts, src)


def _coords(geom: BaseGeometry) -> str:
    return " ".join(f"{x},{y}" for x, y in shapely.get_coordinates(geom))


def _kml_geometry(geom: BaseGeometry) -> str:
    if isinstance(geom, shapely.Point):
        return f"<Point><coordinates>{_coords(geom)}</coordinates></Point>"
    if isinstance(geom, shapely.LineString):
        return f"<LineString><coordinates>{_coords(geom)}</coordinates></LineString>"
    if isinstance(geom, shapely.Polygon):
        inner = "".join(
            f"<innerBoundaryIs><LinearRing><coordinates>{_coords(shapely.LinearRing(r))}"
            "</coordinates></LinearRing></innerBoundaryIs>"
            for r in geom.interiors
        )
        return (
            "<Polygon><outerBoundaryIs><LinearRing><coordinates>"
            f"{_coords(shapely.LinearRing(geom.exterior))}</coordinates></LinearRing></outerBoundaryIs>"
            f"{inner}</Polygon>"
        )
    parts = "".join(_kml_geometry(g) for g in geom.geoms)
    return f"<MultiGeometry>{parts}</MultiGeometry>"


def placemark(name: str, geom: BaseGeometry, data: dict[str, str] | None = None) -> str:
    extended = ""
    if data:
        extended = (
            "<ExtendedData>"
            + "".join(f'<Data name="{escape(k)}"><value>{escape(v)}</value></Data>' for k, v in data.items())
            + "</ExtendedData>"
        )
    return f"<Placemark><name>{escape(name)}</name>{extended}{_kml_geometry(geom)}</Placemark>"


def folder(name: str, *children: str) -> str:
    return f"<Folder><name>{escape(name)}</name>{''.join(children)}</Folder>"


def kml_document(*children: str, name: str = "Test") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<name>{escape(name)}</name>{''.join(children)}</Document></kml>"
    )


def write_kml(path: Path, *children: str) -> Path:
    path.write_text(kml_document(*children), encoding="utf-8")
    return path


def write_kmz(path: Path, *children: str) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml_document(*children))
    return path
