"""End-to-end test against the real docker compose stack (api + worker + redis + postgis).

Run: docker compose up -d --build --wait && E2E_BASE_URL=http://localhost:8000 uv run pytest tests/e2e
"""

import os
import time
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL")
SAMPLES = Path(__file__).resolve().parents[2] / "samples"

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not BASE_URL, reason="set E2E_BASE_URL to run against a live stack"),
]


def wait_for_completion(client: httpx.Client, file_id: str, timeout: float = 60) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = client.get(f"/api/files/{file_id}/").json()
        if info["status"] in ("COMPLETED", "FAILED"):
            return info  # type: ignore[no-any-return]
        time.sleep(0.3)
    raise AssertionError(f"upload {file_id} did not finish within {timeout}s")


@pytest.mark.parametrize(
    ("sample", "features", "crs"),
    [
        ("pune_survey.kml", 8, "EPSG:4326"),
        ("edge_cases.kml", 6, "EPSG:4326"),
        ("parcels_utm43n.zip", 4, "EPSG:32643"),
        ("village_layers.zip", 8, "EPSG:4326"),
        ("plots_no_prj.zip", 4, "EPSG:4326"),
        ("pune_plots.kmz", 4, "EPSG:4326"),
    ],
)
def test_upload_is_processed_by_the_worker(sample: str, features: int, crs: str) -> None:
    with httpx.Client(base_url=BASE_URL or "", timeout=30) as client:
        with (SAMPLES / sample).open("rb") as fh:
            response = client.post("/api/files/", files={"file": (sample, fh)})
        assert response.status_code == 202
        assert response.json()["status"] == "PENDING"

        info = wait_for_completion(client, response.json()["id"])
        assert info["status"] == "COMPLETED", info
        assert info["feature_count"] == features
        assert info["crs"] == crs

        data = client.get(f"/api/files/{info['id']}/measurements/").json()
        assert data["totals"]["feature_count"] == features
        for feature in data["features"]:
            m = feature["measurement"]
            if m is not None:
                assert m["value"] > 0
                assert m["relative_difference"] is None or m["relative_difference"] < 1e-5

        assert client.get(f"/viewer/{info['id']}").status_code == 200
