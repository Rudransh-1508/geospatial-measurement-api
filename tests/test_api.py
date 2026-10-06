import uuid
import zipfile
from pathlib import Path
from typing import Any

import pytest
import shapely
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Upload, UploadStatus
from app.processing.pipeline import process_upload
from tests.factories import folder, placemark, shapefile_zip, write_kml, write_kmz


def upload(client: TestClient, path: Path, wait: bool = True, name: str | None = None) -> dict[str, Any]:
    with path.open("rb") as fh:
        response = client.post(
            "/api/files/", params={"wait": str(wait).lower()}, files={"file": (name or path.name, fh)}
        )
    return {"status_code": response.status_code, "json": response.json(), "headers": response.headers}


@pytest.fixture
def survey_kml(tmp_path: Path) -> Path:
    return write_kml(
        tmp_path / "survey.kml",
        folder(
            "Plots",
            placemark("Plot A", shapely.box(77.2, 28.6, 77.21, 28.61), {"owner": "Ravi"}),
            placemark("Plot B", shapely.box(77.22, 28.6, 77.23, 28.61)),
        ),
        folder("Roads", placemark("Main road", shapely.LineString([(77.2, 28.6), (77.3, 28.7)]))),
        placemark("Well", shapely.Point(77.25, 28.65)),
    )


def test_health(client: TestClient) -> None:
    assert client.get("/api/health/").json() == {"status": "ok"}


def test_upload_kml_inline_and_read_back(client: TestClient, survey_kml: Path) -> None:
    result = upload(client, survey_kml)

    assert result["status_code"] == 201
    body = result["json"]
    assert body["status"] == "COMPLETED"
    assert body["filename"] == "survey.kml"
    assert body["file_format"] == "kml"
    assert body["feature_count"] == 4
    assert body["crs"] == "EPSG:4326"
    assert result["headers"]["location"] == f"/api/files/{body['id']}/"

    info = client.get(f"/api/files/{body['id']}/").json()
    assert info["status"] == "COMPLETED"
    assert info["links"]["measurements"] == f"/api/files/{body['id']}/measurements/"


def test_measurements_shape_and_totals(client: TestClient, survey_kml: Path) -> None:
    file_id = upload(client, survey_kml)["json"]["id"]

    data = client.get(f"/api/files/{file_id}/measurements/").json()

    assert data["status"] == "COMPLETED"
    assert data["crs"] == "EPSG:4326"
    totals = data["totals"]
    assert totals["feature_count"] == 4
    assert totals["by_geometry_type"] == {"Polygon": 2, "LineString": 1, "Point": 1}
    assert totals["by_status"] == {"measured": 3, "not_applicable": 1}
    assert data["pagination"] == {"limit": 100, "offset": 0, "total": 4}

    features = {f["properties"]["Name"]: f for f in data["features"]}
    plot = features["Plot A"]
    assert plot["geometry_type"] == "Polygon"
    assert plot["crs"] == "EPSG:4326"
    assert plot["geometry"]["type"] == "Polygon"
    assert plot["status"] == "measured"
    m = plot["measurement"]
    assert m["kind"] == "area" and m["unit"] == "m2" and m["method"] == "local_laea"
    assert m["value"] == pytest.approx(1_083_988, rel=1e-5)
    assert m["perimeter_unit"] == "m"
    assert m["projection"].startswith("+proj=laea")
    assert m["relative_difference"] < 1e-6

    road = features["Main road"]["measurement"]
    assert road["kind"] == "length" and road["unit"] == "m" and road["method"] == "local_aeqd"
    assert road["value"] == pytest.approx(14_779, rel=1e-3)

    well = features["Well"]
    assert well["status"] == "not_applicable" and well["measurement"] is None

    area_sum = sum(f["measurement"]["value"] for f in data["features"] if f["geometry_type"] == "Polygon")
    assert totals["area_m2"] == pytest.approx(area_sum)
    assert totals["length_m"] == pytest.approx(road["value"])


def test_measurements_pagination_and_without_geometry(client: TestClient, survey_kml: Path) -> None:
    file_id = upload(client, survey_kml)["json"]["id"]

    page = client.get(
        f"/api/files/{file_id}/measurements/", params={"limit": 2, "offset": 2, "include_geometry": "false"}
    ).json()

    assert [f["id"] for f in page["features"]] == [2, 3]
    assert all(f["geometry"] is None for f in page["features"])
    assert page["totals"]["feature_count"] == 4


def test_upload_shapefile_zip(client: TestClient, tmp_path: Path) -> None:
    path = shapefile_zip(
        tmp_path,
        [shapely.box(73.85, 18.52, 73.86, 18.53)],
        properties=[{"plot_no": "S-101", "village": "Kothrud"}],
        crs="EPSG:4326",
        name="parcels",
    )
    body = upload(client, path)["json"]
    assert body["status"] == "COMPLETED" and body["layers"] == ["parcels"]

    feature = client.get(f"/api/files/{body['id']}/measurements/").json()["features"][0]
    assert feature["properties"] == {"plot_no": "S-101", "village": "Kothrud"}
    assert feature["layer"] == "parcels"


def test_upload_kmz(client: TestClient, tmp_path: Path) -> None:
    path = write_kmz(tmp_path / "plots.kmz", placemark("Plot", shapely.box(77.2, 28.6, 77.21, 28.61)))
    body = upload(client, path)["json"]
    assert body["status"] == "COMPLETED" and body["file_format"] == "kmz" and body["feature_count"] == 1


def test_crs_assumed_is_reported(client: TestClient, tmp_path: Path) -> None:
    path = shapefile_zip(tmp_path, [shapely.box(77.2, 28.6, 77.21, 28.61)], drop=(".prj",))
    body = upload(client, path)["json"]
    assert body["crs_assumed"] is True
    assert body["crs"] == "EPSG:4326"
    assert any(w.startswith("crs_assumed") for w in body["warnings"])


def test_unsupported_features_do_not_fail_the_file(client: TestClient, tmp_path: Path) -> None:
    path = shapefile_zip(tmp_path, [shapely.box(500_000, 2_000_000, 500_100, 2_000_100)], drop=(".prj",))
    body = upload(client, path)["json"]
    assert body["status"] == "COMPLETED"

    feature = client.get(f"/api/files/{body['id']}/measurements/").json()["features"][0]
    assert feature["status"] == "unsupported"
    assert feature["reason"] == "unknown_crs"
    assert feature["geometry"] is None


def test_async_upload_is_queued(
    client: TestClient, survey_kml: Path, enqueued: list[str], session: Session
) -> None:
    result = upload(client, survey_kml, wait=False)

    assert result["status_code"] == 202
    body = result["json"]
    assert body["status"] == "PENDING"
    assert enqueued == [body["id"]]
    assert client.get(f"/api/files/{body['id']}/measurements/").status_code == 409

    # What the worker does:
    process_upload(session, uuid.UUID(body["id"]))
    assert client.get(f"/api/files/{body['id']}/").json()["status"] == "COMPLETED"
    assert client.get(f"/api/files/{body['id']}/measurements/").status_code == 200


def test_wait_is_ignored_for_large_files(
    client: TestClient, survey_kml: Path, enqueued: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "inline_max_bytes", 10)
    result = upload(client, survey_kml, wait=True)
    assert result["status_code"] == 202 and len(enqueued) == 1


def test_queue_unavailable_returns_503_and_marks_failed(
    client: TestClient, survey_kml: Path, monkeypatch: pytest.MonkeyPatch, session: Session
) -> None:
    from app.worker import tasks

    def boom(_: str) -> None:
        raise ConnectionError("redis down")

    monkeypatch.setattr(tasks.process_upload_task, "delay", boom)
    result = upload(client, survey_kml, wait=False)

    assert result["status_code"] == 503
    upload_row = session.query(Upload).one()
    assert upload_row.status is UploadStatus.FAILED


def test_processing_is_idempotent(client: TestClient, survey_kml: Path, session: Session) -> None:
    file_id = upload(client, survey_kml)["json"]["id"]

    process_upload(session, uuid.UUID(file_id))
    process_upload(session, uuid.UUID(file_id))

    data = client.get(f"/api/files/{file_id}/measurements/").json()
    assert data["totals"]["feature_count"] == 4


def test_unreadable_file_fails_with_reason(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "broken.kml"
    path.write_text("<kml><Document><Placemark>")
    body = upload(client, path)["json"]

    assert body["status"] == "FAILED"
    assert "Could not read" in body["error"]
    response = client.get(f"/api/files/{body['id']}/measurements/")
    assert response.status_code == 409
    assert "FAILED" in response.json()["detail"]


@pytest.mark.parametrize("name", ["data.geojson", "notes.txt"])
def test_unsupported_type_is_415(client: TestClient, tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    path.write_text("{}")
    assert upload(client, path)["status_code"] == 415


def test_wrong_content_is_400(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "fake.zip"
    path.write_text("not a zip")
    result = upload(client, path)
    assert result["status_code"] == 400
    assert "not a valid zip" in result["json"]["detail"]


def test_zip_slip_is_400(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "evil.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("../evil.shp", b"x")
    result = upload(client, path)
    assert result["status_code"] == 400
    assert "unsafe path" in result["json"]["detail"]


def test_incomplete_shapefile_is_400(client: TestClient, tmp_path: Path) -> None:
    path = shapefile_zip(tmp_path, [shapely.Point(0, 0)], drop=(".dbf",))
    result = upload(client, path)
    assert result["status_code"] == 400
    assert "missing .dbf" in result["json"]["detail"]


def test_empty_file_is_400(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "empty.kml"
    path.write_text("")
    assert upload(client, path)["status_code"] == 400


def test_oversize_file_is_413(client: TestClient, survey_kml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_bytes", 100)
    assert upload(client, survey_kml)["status_code"] == 413


def test_rejected_uploads_leave_nothing_behind(client: TestClient, tmp_path: Path, session: Session) -> None:
    from app.core.config import get_settings

    path = tmp_path / "fake.zip"
    path.write_text("not a zip")
    before = set(get_settings().upload_dir.glob("*")) if get_settings().upload_dir.exists() else set()
    upload(client, path)
    after = set(get_settings().upload_dir.glob("*"))
    assert after == before
    assert session.query(Upload).count() == 0


def test_filename_is_sanitized(client: TestClient, survey_kml: Path) -> None:
    body = upload(client, survey_kml, name="../../etc/pass wd?.kml")["json"]
    assert body["filename"] == "pass wd_.kml"


def test_unknown_and_malformed_ids(client: TestClient) -> None:
    assert client.get(f"/api/files/{uuid.uuid4()}/").status_code == 404
    assert client.get(f"/api/files/{uuid.uuid4()}/measurements/").status_code == 404
    assert client.get("/api/files/not-a-uuid/").status_code == 422


def test_list_files(client: TestClient, survey_kml: Path) -> None:
    upload(client, survey_kml)
    upload(client, survey_kml)
    data = client.get("/api/files/", params={"limit": 1}).json()
    assert data["total"] == 2 and len(data["items"]) == 1


def test_viewer_page(client: TestClient) -> None:
    response = client.get(f"/viewer/{uuid.uuid4()}")
    assert response.status_code == 200
    assert "leaflet" in response.text.lower()
