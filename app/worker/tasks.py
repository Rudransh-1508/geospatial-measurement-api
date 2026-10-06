import logging
import uuid
from typing import Any

from celery import Task
from sqlalchemy.exc import OperationalError

from app.db.session import get_sessionmaker
from app.processing.pipeline import mark_failed, process_upload
from app.worker.celery_app import celery_app

log = logging.getLogger(__name__)


class ProcessUploadTask(Task):  # type: ignore[type-arg]
    def on_failure(
        self, exc: Exception, task_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], einfo: Any
    ) -> None:
        # Retries are exhausted (or the error was not retryable): never leave an upload stuck.
        upload_id = uuid.UUID(args[0] if args else kwargs["upload_id"])
        with get_sessionmaker()() as session:
            mark_failed(session, upload_id, "Processing failed after retries.")


@celery_app.task(
    base=ProcessUploadTask,
    name="geomeasure.process_upload",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def process_upload_task(upload_id: str) -> None:
    with get_sessionmaker()() as session:
        process_upload(session, uuid.UUID(upload_id))
