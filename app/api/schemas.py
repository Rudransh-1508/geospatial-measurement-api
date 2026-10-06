import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import FeatureStatus, FileFormat, UploadStatus


class FileLinks(BaseModel):
    self: str
    measurements: str
    viewer: str


class FileInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    file_format: FileFormat
    size_bytes: int
    status: UploadStatus
    feature_count: int | None
    layers: list[str]
    crs: str | None = Field(description="Source CRS of the file, e.g. EPSG:4326; MIXED if layers differ.")
    crs_assumed: bool
    warnings: list[str]
    error: str | None
    created_at: datetime
    processed_at: datetime | None
    links: FileLinks


class FileList(BaseModel):
    items: list[FileInfo]
    limit: int
    offset: int
    total: int


class MeasurementOut(BaseModel):
    kind: str = Field(description="area or length")
    value: float = Field(description="Measured in the feature's local projection.")
    unit: str
    perimeter: float | None = None
    perimeter_unit: str | None = None
    method: str
    projection: str = Field(description="PROJ string of the local projection used.")
    geodesic_value: float = Field(description="Same quantity computed on the WGS84 ellipsoid.")
    geodesic_perimeter: float | None = None
    relative_difference: float | None = Field(description="|value - geodesic_value| / geodesic_value")


class FeatureOut(BaseModel):
    id: int = Field(description="Feature index within the file.")
    layer: str
    geometry_type: str | None
    crs: str | None = Field(description="Source CRS of the feature's layer.")
    properties: dict[str, Any]
    geometry: dict[str, Any] | None = Field(description="GeoJSON in EPSG:4326 (RFC 7946).")
    status: FeatureStatus
    reason: str | None
    warnings: list[str]
    measurement: MeasurementOut | None


class Totals(BaseModel):
    feature_count: int
    by_geometry_type: dict[str, int]
    by_status: dict[str, int]
    area_m2: float
    length_m: float


class Pagination(BaseModel):
    limit: int
    offset: int
    total: int


class MeasurementsResponse(BaseModel):
    file_id: uuid.UUID
    status: UploadStatus
    crs: str | None
    crs_assumed: bool
    totals: Totals
    pagination: Pagination
    features: list[FeatureOut]


class ErrorResponse(BaseModel):
    detail: str
