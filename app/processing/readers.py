"""Read features from uploaded files and normalize them to EPSG:4326 (ADR 0002, 0004)."""

import math
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pyogrio
import pyogrio.raw
import shapely
from pyogrio.errors import DataLayerError, DataSourceError
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError
from shapely.geometry.base import BaseGeometry

from app.db.models import FileFormat
from app.processing.archive import (
    ArchiveLimits,
    InvalidUploadError,
    check_archive,
    extract_members,
    shapefile_stems,
)

WGS84 = CRS.from_epsg(4326)

# Presentation fields LIBKML adds to every KML layer. They describe rendering, not the feature.
KML_STYLE_FIELDS = frozenset(
    {
        "id",
        "timestamp",
        "begin",
        "end",
        "altitudeMode",
        "tessellate",
        "extrude",
        "visibility",
        "drawOrder",
        "icon",
    }
)


class UnreadableFileError(InvalidUploadError):
    """The file passed upload validation but GDAL could not read it."""


@dataclass
class RawFeature:
    index: int
    layer: str
    properties: dict[str, Any]
    source_crs: str | None
    # Normalized to EPSG:4326. None when the source had no geometry or its CRS is unknown.
    geometry: BaseGeometry | None
    source_geometry_type: str | None
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ReadResult:
    features: list[RawFeature]
    layers: list[str]
    source_crs: str | None
    crs_assumed: bool
    warnings: list[str]


@dataclass
class _Layer:
    name: str
    path: Path
    layer: str | int
    is_kml: bool


def crs_label(crs: CRS) -> str:
    """Short, human-friendly CRS identifier: authority code when there is one."""
    authority = crs.to_authority(min_confidence=70)
    if authority:
        return f"{authority[0]}:{authority[1]}"
    return crs.name


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _properties(names: list[str], columns: list[Any], row: int, is_kml: bool) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for name, column in zip(names, columns, strict=True):
        value = _json_safe(column[row])
        if is_kml and (name in KML_STYLE_FIELDS or value is None):
            continue
        props[name] = value
    return props


def _lonlat_in_range(geoms: list[BaseGeometry]) -> bool:
    present = [g for g in geoms if g is not None and not g.is_empty]
    if not present:
        return True
    minx, miny, maxx, maxy = shapely.total_bounds(present)
    return bool(minx >= -180 and maxx <= 180 and miny >= -90 and maxy <= 90)


def _iter_layers(
    path: Path, file_format: FileFormat, workdir: Path, limits: ArchiveLimits
) -> Iterator[_Layer]:
    if file_format is FileFormat.KML:
        for name, _ in pyogrio.list_layers(path):
            yield _Layer(name=str(name), path=path, layer=str(name), is_kml=True)
        return

    members = check_archive(path, limits)
    extract_members(path, members, workdir, limits.max_uncompressed_bytes)

    if file_format is FileFormat.KMZ:
        kml_files = sorted(m.filename for m in members if m.filename.lower().endswith(".kml"))
        # By convention the first .kml in a KMZ is the document; others are usually overlays.
        doc = next((n for n in kml_files if Path(n).name.lower() == "doc.kml"), kml_files[0])
        kml_path = workdir / doc
        for name, _ in pyogrio.list_layers(kml_path):
            yield _Layer(name=str(name), path=kml_path, layer=str(name), is_kml=True)
        return

    for stem in shapefile_stems(members):
        shp = workdir / f"{stem}.shp"
        yield _Layer(name=Path(stem).name, path=shp, layer=0, is_kml=False)


def read_upload(path: Path, file_format: FileFormat, limits: ArchiveLimits) -> ReadResult:
    """Read every feature of every layer, normalized to EPSG:4326."""
    features: list[RawFeature] = []
    layer_names: list[str] = []
    layer_crs: list[str | None] = []
    warnings: list[str] = []
    crs_assumed = False

    with tempfile.TemporaryDirectory(prefix="geomeasure-") as tmp:
        try:
            layers = list(_iter_layers(path, file_format, Path(tmp), limits))
        except (DataSourceError, DataLayerError) as exc:
            raise UnreadableFileError(f"Could not read the file: {exc}") from exc

        for layer in layers:
            try:
                meta, _fids, wkb, columns = pyogrio.raw.read(
                    layer.path, layer=layer.layer, return_fids=True, datetime_as_string=True
                )
            except (DataSourceError, DataLayerError) as exc:
                raise UnreadableFileError(f"Could not read layer '{layer.name}': {exc}") from exc

            layer_names.append(layer.name)
            geoms: list[BaseGeometry | None] = [shapely.from_wkb(g) if g is not None else None for g in wkb]
            names = [str(n) for n in meta["fields"]]

            source_crs: CRS | None
            unknown_crs = False
            if layer.is_kml:
                source_crs = WGS84  # KML is always WGS84 lon/lat by specification.
            elif meta["crs"] is None:
                if _lonlat_in_range([g for g in geoms if g is not None]):
                    source_crs = WGS84
                    crs_assumed = True
                    warnings.append(f"crs_assumed: layer '{layer.name}' has no .prj; assumed EPSG:4326")
                else:
                    source_crs = None
                    unknown_crs = True
                    warnings.append(
                        f"unknown_crs: layer '{layer.name}' has no .prj and its coordinates are not lon/lat"
                    )
            else:
                try:
                    source_crs = CRS.from_user_input(meta["crs"])
                except CRSError:
                    source_crs = None
                    unknown_crs = True
                    warnings.append(f"unknown_crs: layer '{layer.name}' has an unparseable CRS")

            label = crs_label(source_crs) if source_crs is not None else None
            layer_crs.append(label)
            transformer = (
                Transformer.from_crs(source_crs, WGS84, always_xy=True)
                if source_crs is not None and not source_crs.equals(WGS84)
                else None
            )

            for row, geom in enumerate(geoms):
                feature = RawFeature(
                    index=len(features),
                    layer=layer.name,
                    properties=_properties(names, columns, row, layer.is_kml),
                    source_crs=label,
                    geometry=None,
                    source_geometry_type=geom.geom_type if geom is not None else None,
                )
                if geom is None:
                    feature.reason = "missing_geometry"
                elif unknown_crs:
                    feature.reason = "unknown_crs"
                else:
                    feature.geometry, feature.reason = _normalize(geom, transformer)
                features.append(feature)

    distinct_crs = {c for c in layer_crs if c is not None}
    if len(distinct_crs) == 1:
        file_crs: str | None = distinct_crs.pop()
    elif distinct_crs:
        file_crs = "MIXED"
        warnings.append("mixed_crs: layers use different CRSs; see each feature's crs")
    else:
        file_crs = None

    return ReadResult(
        features=features,
        layers=layer_names,
        source_crs=file_crs,
        crs_assumed=crs_assumed,
        warnings=warnings,
    )


def _normalize(geom: BaseGeometry, transformer: Transformer | None) -> tuple[BaseGeometry | None, str | None]:
    if transformer is None:
        return geom, None
    z = shapely.has_z(geom)

    def fn(coords: np.ndarray) -> np.ndarray:
        if coords.shape[1] == 3:
            x, y, zz = transformer.transform(coords[:, 0], coords[:, 1], coords[:, 2])
            return np.column_stack([x, y, zz])
        x, y = transformer.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    out = shapely.transform(geom, fn, include_z=z)
    if not np.isfinite(shapely.get_coordinates(out)).all():
        return None, "transform_failed"
    return out, None
