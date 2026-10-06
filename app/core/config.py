from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://geomeasure:geomeasure@localhost:5433/geomeasure"
    redis_url: str = "redis://localhost:6380/0"
    upload_dir: Path = Path("./data/uploads")

    # Hard cap on the uploaded file itself.
    max_upload_bytes: int = 50 * 1024 * 1024
    # Uploads at or below this size may be processed inside the request with ?wait=true.
    inline_max_bytes: int = 5 * 1024 * 1024
    # Zip bomb protection for .zip and .kmz archives.
    max_uncompressed_bytes: int = 500 * 1024 * 1024
    max_compression_ratio: int = 200
    max_archive_entries: int = 10_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
