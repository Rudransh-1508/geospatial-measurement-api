import zipfile
from pathlib import Path

import pytest
import shapely

from app.db.models import FileFormat
from app.processing.archive import (
    ArchiveLimits,
    InvalidUploadError,
    UnsupportedFormatError,
    check_archive,
    check_content,
    extract_members,
    format_from_filename,
    validate_upload,
)
from tests.factories import shapefile_zip

LIMITS = ArchiveLimits(max_uncompressed_bytes=10 * 1024 * 1024, max_compression_ratio=200, max_entries=100)


@pytest.mark.parametrize(
    ("name", "expected"),
    [("a.zip", FileFormat.SHAPEFILE), ("A.KML", FileFormat.KML), ("x.kmz", FileFormat.KMZ)],
)
def test_format_from_extension(name: str, expected: FileFormat) -> None:
    assert format_from_filename(name) is expected


@pytest.mark.parametrize("name", ["a.geojson", "a.shp", "noext", "a.zip.exe"])
def test_unsupported_extensions(name: str) -> None:
    with pytest.raises(UnsupportedFormatError):
        format_from_filename(name)


def test_content_must_match_extension() -> None:
    check_content(FileFormat.KML, "a.kml", b'<?xml version="1.0"?><kml xmlns="...">')
    check_content(FileFormat.SHAPEFILE, "a.zip", b"PK\x03\x04rest")
    with pytest.raises(InvalidUploadError):
        check_content(FileFormat.SHAPEFILE, "a.zip", b"<kml>")
    with pytest.raises(InvalidUploadError):
        check_content(FileFormat.KML, "a.kml", b"PK\x03\x04")


def test_valid_shapefile_zip(tmp_path: Path) -> None:
    path = shapefile_zip(tmp_path, [shapely.Point(0, 0)])
    validate_upload(path, FileFormat.SHAPEFILE, LIMITS)


def test_zip_slip_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "evil.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("../../etc/evil.shp", b"x")
    with pytest.raises(InvalidUploadError, match="unsafe path"):
        check_archive(path, LIMITS)


def test_absolute_path_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "evil.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("/tmp/evil.shp", b"x")
    with pytest.raises(InvalidUploadError, match="unsafe path"):
        check_archive(path, LIMITS)


def test_zip_bomb_by_size_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.shp", b"\0" * (11 * 1024 * 1024))
    with pytest.raises(InvalidUploadError):
        check_archive(path, LIMITS)


def test_zip_bomb_by_ratio_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.shp", b"\0" * (5 * 1024 * 1024))
    with pytest.raises(InvalidUploadError, match="compression ratio"):
        check_archive(path, LIMITS)


def test_extraction_counts_real_bytes(tmp_path: Path) -> None:
    path = tmp_path / "a.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("a.bin", b"x" * 2000)
    members = check_archive(path, LIMITS)
    with pytest.raises(InvalidUploadError):
        extract_members(path, members, tmp_path / "out", max_bytes=1000)


def test_too_many_entries(tmp_path: Path) -> None:
    path = tmp_path / "many.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for i in range(101):
            zf.writestr(f"f{i}.txt", b"x")
    with pytest.raises(InvalidUploadError, match="too many"):
        check_archive(path, LIMITS)


def test_macos_junk_is_ignored(tmp_path: Path) -> None:
    path = shapefile_zip(tmp_path, [shapely.Point(0, 0)])
    with zipfile.ZipFile(path, "a") as zf:
        zf.writestr("__MACOSX/._layer.shp", b"junk")
        zf.writestr(".DS_Store", b"junk")
    names = [m.filename for m in check_archive(path, LIMITS)]
    assert not any("MACOSX" in n or "DS_Store" in n for n in names)


@pytest.mark.parametrize("missing", [".shx", ".dbf"])
def test_incomplete_shapefile(tmp_path: Path, missing: str) -> None:
    path = shapefile_zip(tmp_path, [shapely.Point(0, 0)], drop=(missing,))
    with pytest.raises(InvalidUploadError, match=f"missing {missing}"):
        validate_upload(path, FileFormat.SHAPEFILE, LIMITS)


def test_zip_without_shapefile(tmp_path: Path) -> None:
    path = tmp_path / "docs.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("readme.txt", b"hello")
    with pytest.raises(InvalidUploadError, match="does not contain a Shapefile"):
        validate_upload(path, FileFormat.SHAPEFILE, LIMITS)


def test_kmz_without_kml(tmp_path: Path) -> None:
    path = tmp_path / "a.kmz"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("image.png", b"png")
    with pytest.raises(InvalidUploadError, match=r"does not contain a \.kml"):
        validate_upload(path, FileFormat.KMZ, LIMITS)


def test_corrupt_zip(tmp_path: Path) -> None:
    path = tmp_path / "a.zip"
    path.write_bytes(b"PK\x03\x04garbage")
    with pytest.raises(InvalidUploadError, match="corrupt"):
        validate_upload(path, FileFormat.SHAPEFILE, LIMITS)
