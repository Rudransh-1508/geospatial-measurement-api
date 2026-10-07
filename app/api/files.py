import json
import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ErrorResponse,
    FeatureOut,
    FileInfo,
    FileLinks,
    FileList,
    MeasurementOut,
    MeasurementsResponse,
    Pagination,
    Totals,
)
from app.core.config import get_settings
from app.db.models import Feature, FeatureStatus, Upload, UploadStatus
from app.db.session import get_session
from app.processing.archive import (
    InvalidUploadError,
    UnsupportedFormatError,
    check_content,
    format_from_filename,
    validate_upload,
)
from app.processing.pipeline import archive_limits, mark_failed, process_upload
from app.worker.tasks import process_upload_task

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])

SessionDep = Annotated[Session, Depends(get_session)]
CHUNK = 1024 * 1024
SNIFF_BYTES = 4096


def _links(upload_id: uuid.UUID) -> FileLinks:
    return FileLinks(
        self=f"/api/files/{upload_id}/",
        measurements=f"/api/files/{upload_id}/measurements/",
        viewer=f"/viewer/{upload_id}",
    )


def _file_info(upload: Upload) -> FileInfo:
    return FileInfo(
        id=upload.id,
        filename=upload.filename,
        file_format=upload.file_format,
        size_bytes=upload.size_bytes,
        status=upload.status,
        feature_count=upload.feature_count,
        layers=upload.layers or [],
        crs=upload.source_crs,
        crs_assumed=upload.crs_assumed,
        warnings=upload.warnings or [],
        error=upload.error,
        created_at=upload.created_at,
        processed_at=upload.processed_at,
        links=_links(upload.id),
    )


def _safe_filename(name: str) -> str:
    base = Path(name.replace("\\", "/")).name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
    return cleaned[:200] or "upload"


def _store(file: UploadFile, dest: Path, max_bytes: int) -> tuple[int, bytes]:
    """Copy the upload to its permanent location, keeping the first bytes for sniffing.

    Requests that declare an oversized Content-Length are rejected by middleware before
    the body is read; this check covers bodies sent without one.
    """
    size = 0
    head = b""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        while chunk := file.file.read(CHUNK):
            if len(head) < SNIFF_BYTES:
                head += chunk[: SNIFF_BYTES - len(head)]
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    f"File exceeds the {max_bytes // (1024 * 1024)} MB limit.",
                )
            out.write(chunk)
    if size == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty.")
    return size, head


def _get_upload(session: Session, file_id: uuid.UUID) -> Upload:
    upload = session.get(Upload, file_id)
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    return upload


@router.post(
    "/",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=FileInfo,
    responses={
        201: {"model": FileInfo, "description": "Processed inline (?wait=true)."},
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="Upload a .zip Shapefile, .kml or .kmz",
)
def upload_file(
    file: UploadFile,
    session: SessionDep,
    response: Response,
    wait: Annotated[
        bool, Query(description="Process inline and return the final status (small files only).")
    ] = False,
) -> FileInfo:
    settings = get_settings()
    upload_id = uuid.uuid4()
    filename = _safe_filename(file.filename or "upload")
    upload_dir = settings.upload_dir / str(upload_id)
    stored_path = upload_dir / filename

    try:
        file_format = format_from_filename(filename)
    except UnsupportedFormatError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    try:
        size, head = _store(file, stored_path, settings.max_upload_bytes)
        try:
            check_content(file_format, filename, head)
            validate_upload(stored_path, file_format, archive_limits())
        except InvalidUploadError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except HTTPException:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise

    upload = Upload(
        id=upload_id,
        filename=filename,
        stored_path=str(stored_path),
        size_bytes=size,
        file_format=file_format,
        status=UploadStatus.PENDING,
    )
    session.add(upload)
    session.commit()
    response.headers["Location"] = f"/api/files/{upload_id}/"

    if wait and size <= settings.inline_max_bytes:
        try:
            process_upload(session, upload_id)
        except Exception:
            log.exception("inline processing failed for %s", upload_id)
            session.rollback()
            mark_failed(session, upload_id, "Internal error while processing the file.")
        session.refresh(upload)
        response.status_code = status.HTTP_201_CREATED
        return _file_info(upload)

    try:
        process_upload_task.delay(str(upload_id))
    except Exception as exc:
        log.exception("could not enqueue upload %s", upload_id)
        mark_failed(session, upload_id, "Processing queue unavailable.")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Processing queue unavailable, try again later."
        ) from exc
    return _file_info(upload)


@router.get("/", response_model=FileList, summary="List uploaded files")
def list_files(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FileList:
    total = session.scalar(select(func.count()).select_from(Upload)) or 0
    uploads = session.scalars(
        select(Upload).order_by(Upload.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return FileList(items=[_file_info(u) for u in uploads], limit=limit, offset=offset, total=total)


@router.get(
    "/{file_id}/",
    response_model=FileInfo,
    responses={404: {"model": ErrorResponse}},
    summary="File information and processing status",
)
def get_file(file_id: uuid.UUID, session: SessionDep) -> FileInfo:
    return _file_info(_get_upload(session, file_id))


def _measurement(feature: Feature) -> MeasurementOut | None:
    if feature.measurement_kind is None or feature.value is None:
        return None
    return MeasurementOut(
        kind=feature.measurement_kind,
        value=feature.value,
        unit=feature.unit or "",
        perimeter=feature.perimeter,
        perimeter_unit="m" if feature.perimeter is not None else None,
        method=feature.method or "",
        projection=feature.projection or "",
        geodesic_value=feature.geodesic_value or 0.0,
        geodesic_perimeter=feature.geodesic_perimeter,
        relative_difference=feature.relative_difference,
    )


@router.get(
    "/{file_id}/measurements/",
    response_model=MeasurementsResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="Per-feature measurements with totals",
)
def get_measurements(
    file_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_geometry: Annotated[bool, Query(description="Include GeoJSON geometries.")] = True,
) -> MeasurementsResponse:
    upload = _get_upload(session, file_id)
    if upload.status is not UploadStatus.COMPLETED:
        detail = f"File is {upload.status.value}; measurements are available once it is COMPLETED."
        if upload.error:
            detail += f" Error: {upload.error}"
        raise HTTPException(status.HTTP_409_CONFLICT, detail)

    where = Feature.upload_id == upload.id
    total, area, length = session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(case((Feature.measurement_kind == "area", Feature.value))), 0.0),
            func.coalesce(func.sum(case((Feature.measurement_kind == "length", Feature.value))), 0.0),
        ).where(where)
    ).one()
    by_type = dict(
        session.execute(
            select(func.coalesce(Feature.geometry_type, "None"), func.count())
            .where(where)
            .group_by(Feature.geometry_type)
        ).all()
    )
    by_status = dict(
        session.execute(select(Feature.status, func.count()).where(where).group_by(Feature.status)).all()
    )

    geojson = func.ST_AsGeoJSON(Feature.geometry, 9) if include_geometry else None
    columns: list[Any] = [Feature] + ([geojson] if geojson is not None else [])
    rows = session.execute(
        select(*columns).where(where).order_by(Feature.index).limit(limit).offset(offset)
    ).all()

    features: list[FeatureOut] = []
    for row in rows:
        feature: Feature = row[0]
        geometry = json.loads(row[1]) if include_geometry and row[1] is not None else None
        features.append(
            FeatureOut(
                id=feature.index,
                layer=feature.layer,
                geometry_type=feature.geometry_type,
                crs=feature.crs,
                properties=feature.properties or {},
                geometry=geometry,
                status=feature.status,
                reason=feature.reason,
                warnings=feature.warnings or [],
                measurement=_measurement(feature),
            )
        )

    return MeasurementsResponse(
        file_id=upload.id,
        status=upload.status,
        crs=upload.source_crs,
        crs_assumed=upload.crs_assumed,
        totals=Totals(
            feature_count=total,
            by_geometry_type={str(k): v for k, v in by_type.items()},
            by_status={FeatureStatus(k).value: v for k, v in by_status.items()},
            area_m2=float(area),
            length_m=float(length),
        ),
        pagination=Pagination(limit=limit, offset=offset, total=total),
        features=features,
    )
