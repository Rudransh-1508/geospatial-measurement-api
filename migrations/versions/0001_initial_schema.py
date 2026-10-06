"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-07 01:04:14.636438

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "uploads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "file_format",
            sa.Enum("shapefile", "kml", "kmz", name="fileformat", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PROCESSING",
                "COMPLETED",
                "FAILED",
                name="uploadstatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("source_crs", sa.Text(), nullable=True),
        sa.Column("crs_assumed", sa.Boolean(), nullable=False),
        sa.Column("feature_count", sa.Integer(), nullable=True),
        sa.Column("layers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_uploads_status"), "uploads", ["status"], unique=False)
    op.create_table(
        "features",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("layer", sa.Text(), nullable=False),
        sa.Column("geometry_type", sa.String(length=32), nullable=True),
        sa.Column("crs", sa.Text(), nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.types.Geometry(srid=4326, dimension=2, from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=True,
        ),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "measured",
                "not_applicable",
                "unsupported",
                name="featurestatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("measurement_kind", sa.String(length=16), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=8), nullable=True),
        sa.Column("perimeter", sa.Float(), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=True),
        sa.Column("projection", sa.Text(), nullable=True),
        sa.Column("geodesic_value", sa.Float(), nullable=True),
        sa.Column("geodesic_perimeter", sa.Float(), nullable=True),
        sa.Column("relative_difference", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upload_id", "index", name="uq_features_upload_index"),
    )
    op.create_index(op.f("ix_features_upload_id"), "features", ["upload_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_features_upload_id"), table_name="features")
    op.drop_table("features")
    op.drop_index(op.f("ix_uploads_status"), table_name="uploads")
    op.drop_table("uploads")
