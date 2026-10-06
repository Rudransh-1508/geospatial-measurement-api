"""Cross-check our measurements against PostGIS, an independent geodesic implementation."""

import uuid
from pathlib import Path

import pytest
import shapely
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Feature
from tests.factories import placemark, write_kml

FEATURES = {
    "delhi plot": shapely.box(77.2, 28.6, 77.21, 28.61),
    "oslo plot": shapely.box(10.7, 59.9, 10.72, 59.91),
    "antimeridian plot": shapely.Polygon(
        [(179.99, -17.0), (-179.99, -17.0), (-179.99, -16.99), (179.99, -16.99)]
    ),
    "holed plot": shapely.Polygon(
        shapely.box(73.8, 18.5, 73.82, 18.52).exterior.coords,
        [shapely.box(73.805, 18.505, 73.81, 18.51).exterior.coords],
    ),
    "highway": shapely.LineString([(72.87, 19.07), (73.0, 19.2), (73.85, 18.52)]),
    "arctic track": shapely.LineString([(20.0, 78.0), (21.0, 78.2)]),
}


@pytest.fixture
def file_id(client: TestClient, tmp_path: Path) -> uuid.UUID:
    path = write_kml(tmp_path / "crosscheck.kml", *(placemark(n, g) for n, g in FEATURES.items()))
    with path.open("rb") as fh:
        body = client.post("/api/files/?wait=true", files={"file": (path.name, fh)}).json()
    assert body["status"] == "COMPLETED"
    return uuid.UUID(body["id"])


def test_areas_and_lengths_agree_with_postgis_geography(file_id: uuid.UUID, session: Session) -> None:
    rows = session.execute(
        select(
            Feature.properties["Name"].astext,
            Feature.measurement_kind,
            Feature.value,
            Feature.geodesic_value,
            func.ST_Area(func.geography(Feature.geometry)),
            func.ST_Length(func.geography(Feature.geometry)),
        ).where(Feature.upload_id == file_id)
    ).all()

    assert {r[0] for r in rows} == set(FEATURES)
    for name, kind, value, geodesic, pg_area, pg_length in rows:
        reference = pg_area if kind == "area" else pg_length
        # Our ellipsoidal reference and PostGIS's are independent implementations of the
        # same maths: they must agree almost exactly.
        assert geodesic == pytest.approx(reference, rel=1e-8), name
        # The projected value carries real (small) projection distortion, largest for the
        # 137 km highway where AEQD is about 1e-6 off; still sub-millimetre per metre.
        assert value == pytest.approx(reference, rel=1e-5), name
