import logging
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import text

from app.api.files import router as files_router
from app.db.session import get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

VIEWER_HTML = Path(__file__).parent / "viewer" / "index.html"

app = FastAPI(
    title="Geospatial File Measurement API",
    version="1.0.0",
    description=(
        "Upload a zipped Shapefile, KML or KMZ and get accurate areas and lengths for every "
        "feature. Each feature is measured in its own local equal-area / equidistant projection "
        "and cross-checked against the WGS84 ellipsoid."
    ),
)
app.include_router(files_router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/api/health/", tags=["health"], summary="Liveness and database connectivity")
def health() -> dict[str, str]:
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/viewer/{file_id}", include_in_schema=False)
def viewer(file_id: uuid.UUID) -> FileResponse:
    return FileResponse(VIEWER_HTML, media_type="text/html")
