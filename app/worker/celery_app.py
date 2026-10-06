from celery import Celery

from app.core.config import get_settings

celery_app = Celery("geomeasure", broker=get_settings().redis_url, include=["app.worker.tasks"])
celery_app.conf.update(
    # Postgres is the single source of truth for upload status (ADR 0006).
    task_ignore_result=True,
    result_backend=None,
    # Acknowledge only after the task finishes so a crashed worker's task is redelivered.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
)
