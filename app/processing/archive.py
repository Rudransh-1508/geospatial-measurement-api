"""Upload format detection and archive safety checks (ADR 0007).

Everything here runs on the file as stored on disk, before any GDAL code touches it.
"""

import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.db.models import FileFormat

ZIP_MAGIC = b"PK\x03\x04"
EXTENSIONS = {".zip": FileFormat.SHAPEFILE, ".kml": FileFormat.KML, ".kmz": FileFormat.KMZ}
SHAPEFILE_SIDECARS = (".shx", ".dbf")


class InvalidUploadError(Exception):
    """The upload is not an acceptable geospatial file. Message is safe to show to clients."""


class UnsupportedFormatError(InvalidUploadError):
    pass


@dataclass(frozen=True)
class ArchiveLimits:
    max_uncompressed_bytes: int
    max_compression_ratio: int
    max_entries: int


def is_ignored_member(name: str) -> bool:
    """macOS resource forks and hidden files that zip tools add."""
    parts = PurePosixPath(name).parts
    return any(part == "__MACOSX" or part.startswith(".") for part in parts)


def format_from_filename(filename: str) -> FileFormat:
    suffix = Path(filename).suffix.lower()
    file_format = EXTENSIONS.get(suffix)
    if file_format is None:
        raise UnsupportedFormatError(
            f"Unsupported file type '{suffix or filename}'. Upload a .zip Shapefile, .kml or .kmz."
        )
    return file_format


def check_content(file_format: FileFormat, filename: str, head: bytes) -> None:
    """Verify the first bytes match the format the extension claims."""
    if file_format in (FileFormat.SHAPEFILE, FileFormat.KMZ):
        if not head.startswith(ZIP_MAGIC):
            raise InvalidUploadError(f"'{filename}' is not a valid zip archive.")
    elif b"<kml" not in head.lower():
        raise InvalidUploadError(f"'{filename}' does not look like a KML document.")


def check_archive(path: Path, limits: ArchiveLimits) -> list[zipfile.ZipInfo]:
    """Reject zip-slip paths and zip bombs. Returns the members worth extracting."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise InvalidUploadError("The archive is corrupt or not a zip file.") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_entries:
            raise InvalidUploadError(f"The archive has too many entries ({len(infos)}).")

        members: list[zipfile.ZipInfo] = []
        total_uncompressed = 0
        total_compressed = 0
        for info in infos:
            name = info.filename
            posix = PurePosixPath(name.replace("\\", "/"))
            if posix.is_absolute() or ".." in posix.parts or (len(name) > 1 and name[1] == ":"):
                raise InvalidUploadError(f"The archive contains an unsafe path: '{name}'.")
            if info.is_dir() or is_ignored_member(name):
                continue
            total_uncompressed += info.file_size
            total_compressed += info.compress_size
            members.append(info)

        if total_uncompressed > limits.max_uncompressed_bytes:
            raise InvalidUploadError("The archive expands to more data than allowed.")
        if total_compressed and total_uncompressed / total_compressed > limits.max_compression_ratio:
            raise InvalidUploadError("The archive's compression ratio is suspiciously high.")
        return members


def shapefile_stems(members: list[zipfile.ZipInfo]) -> list[str]:
    """Return the path stems of complete Shapefiles (.shp with .shx and .dbf) in the archive."""
    names = {m.filename.lower(): m.filename for m in members}
    stems: list[str] = []
    incomplete: list[str] = []
    for lower, original in sorted(names.items()):
        if not lower.endswith(".shp"):
            continue
        stem_lower = lower[: -len(".shp")]
        missing = [ext for ext in SHAPEFILE_SIDECARS if stem_lower + ext not in names]
        if missing:
            incomplete.append(f"{original} (missing {', '.join(missing)})")
        else:
            stems.append(original[: -len(".shp")])
    if incomplete:
        raise InvalidUploadError("Incomplete Shapefile in archive: " + "; ".join(incomplete) + ".")
    if not stems:
        raise InvalidUploadError("The zip archive does not contain a Shapefile (.shp).")
    return stems


def validate_upload(path: Path, file_format: FileFormat, limits: ArchiveLimits) -> None:
    """Full upload-time validation. Raises InvalidUploadError with a client-safe message."""
    if file_format is FileFormat.SHAPEFILE:
        shapefile_stems(check_archive(path, limits))
    elif file_format is FileFormat.KMZ:
        members = check_archive(path, limits)
        if not any(m.filename.lower().endswith(".kml") for m in members):
            raise InvalidUploadError("The KMZ archive does not contain a .kml document.")


def extract_members(path: Path, members: list[zipfile.ZipInfo], dest: Path, max_bytes: int) -> None:
    """Extract already-checked members.

    Re-verifies that each resolved path stays inside dest, and counts the bytes actually
    written because a crafted archive can understate its declared sizes.
    """
    dest = dest.resolve()
    written = 0
    with zipfile.ZipFile(path) as archive:
        for info in members:
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(dest):
                raise InvalidUploadError(f"The archive contains an unsafe path: '{info.filename}'.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open("wb") as out:
                while chunk := src.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise InvalidUploadError("The archive expands to more data than allowed.")
                    out.write(chunk)
