"""Process one upload: read, normalize, measure, persist (ADR 0006).

The same function runs from the Celery task and inline for ``?wait=true``. It is
idempotent: re-running replaces the upload's features instead of adding to them.
"""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from geoalchemy2.shape import from_shape
from sqlalchemy import delete, insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Feature, FeatureStatus, Upload, UploadStatus
from app.processing.archive import ArchiveLimits, InvalidUploadError
from app.processing.measure import measure
from app.processing.readers import RawFeature, read_upload

log = logging.getLogger(__name__)

INSERT_BATCH = 1000


def archive_limits() -> ArchiveLimits:
    settings = get_settings()
    return ArchiveLimits(
        max_uncompressed_bytes=settings.max_uncompressed_bytes,
        max_compression_ratio=settings.max_compression_ratio,
        max_entries=settings.max_archive_entries,
    )


def _feature_row(upload_id: uuid.UUID, raw: RawFeature) -> dict[str, Any]:
    row: dict[str, Any] = {
        "upload_id": upload_id,
        "index": raw.index,
        "layer": raw.layer,
        "geometry_type": raw.source_geometry_type,
        "crs": raw.source_crs,
        "properties": raw.properties,
        "geometry": None,
        "status": FeatureStatus.UNSUPPORTED,
        "reason": raw.reason,
        "warnings": list(raw.warnings),
    }
    if raw.geometry is None:
        return row

    result = measure(raw.geometry)
    row["status"] = FeatureStatus(result.status)
    row["reason"] = result.reason
    row["warnings"] = [*raw.warnings, *result.warnings]
    if result.geometry is not None:
        row["geometry"] = from_shape(result.geometry, srid=4326)
    m = result.measurement
    if m is not None:
        row.update(
            measurement_kind=m.kind.value,
            value=m.value,
            unit=m.unit,
            perimeter=m.perimeter,
            method=m.method.value,
            projection=m.projection,
            geodesic_value=m.geodesic_value,
            geodesic_perimeter=m.geodesic_perimeter,
            relative_difference=m.relative_difference,
        )
    return row


def process_upload(session: Session, upload_id: uuid.UUID) -> UploadStatus | None:
    """Process an upload and return its final status (None if the upload does not exist).

    Invalid or unreadable files end as FAILED with a client-safe error. Transient database
    errors propagate so the caller (the Celery task) can retry.
    """
    upload = session.get(Upload, upload_id)
    if upload is None:
        log.warning("upload %s not found", upload_id)
        return None

    upload.status = UploadStatus.PROCESSING
    upload.error = None
    session.commit()

    try:
        result = read_upload(Path(upload.stored_path), upload.file_format, archive_limits())
    except InvalidUploadError as exc:
        return _fail(session, upload, str(exc))
    except OperationalError:
        raise
    except Exception:
        log.exception("unexpected error reading upload %s", upload_id)
        return _fail(session, upload, "Internal error while reading the file.")

    try:
        rows = [_feature_row(upload.id, raw) for raw in result.features]
    except Exception:
        log.exception("unexpected error measuring upload %s", upload_id)
        return _fail(session, upload, "Internal error while measuring features.")

    session.execute(delete(Feature).where(Feature.upload_id == upload.id))
    for start in range(0, len(rows), INSERT_BATCH):
        session.execute(insert(Feature), rows[start : start + INSERT_BATCH])

    upload.feature_count = len(rows)
    upload.layers = result.layers
    upload.source_crs = result.source_crs
    upload.crs_assumed = result.crs_assumed
    upload.warnings = result.warnings
    upload.status = UploadStatus.COMPLETED
    upload.processed_at = datetime.now(UTC)
    session.commit()
    log.info("upload %s completed with %d features", upload_id, len(rows))
    return upload.status


def _fail(session: Session, upload: Upload, message: str) -> UploadStatus:
    session.rollback()
    upload.status = UploadStatus.FAILED
    upload.error = message
    upload.processed_at = datetime.now(UTC)
    session.commit()
    return upload.status


def mark_failed(session: Session, upload_id: uuid.UUID, message: str) -> None:
    upload = session.get(Upload, upload_id)
    if upload is not None and upload.status is not UploadStatus.COMPLETED:
        _fail(session, upload, message)
