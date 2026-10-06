import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class UploadStatus(enum.StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FileFormat(enum.StrEnum):
    SHAPEFILE = "shapefile"
    KML = "kml"
    KMZ = "kmz"


class FeatureStatus(enum.StrEnum):
    MEASURED = "measured"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    file_format: Mapped[FileFormat] = mapped_column(
        Enum(FileFormat, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e])
    )
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, native_enum=False, length=16), default=UploadStatus.PENDING, index=True
    )
    source_crs: Mapped[str | None] = mapped_column(Text)
    crs_assumed: Mapped[bool] = mapped_column(default=False)
    feature_count: Mapped[int | None] = mapped_column(Integer)
    layers: Mapped[list[str]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    features: Mapped[list["Feature"]] = relationship(
        back_populates="upload", cascade="all, delete-orphan", passive_deletes=True
    )


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("upload_id", "index", name="uq_features_upload_index"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    layer: Mapped[str] = mapped_column(Text)
    geometry_type: Mapped[str | None] = mapped_column(String(32))
    crs: Mapped[str | None] = mapped_column(Text)
    # Normalized geometry in EPSG:4326 (null when the source had no geometry or no usable CRS).
    geometry: Mapped[WKBElement | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True), nullable=True
    )
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[FeatureStatus] = mapped_column(
        Enum(FeatureStatus, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e])
    )
    reason: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)

    measurement_kind: Mapped[str | None] = mapped_column(String(16))
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(8))
    perimeter: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str | None] = mapped_column(String(32))
    projection: Mapped[str | None] = mapped_column(Text)
    geodesic_value: Mapped[float | None] = mapped_column(Float)
    geodesic_perimeter: Mapped[float | None] = mapped_column(Float)
    relative_difference: Mapped[float | None] = mapped_column(Float)

    upload: Mapped[Upload] = relationship(back_populates="features")
