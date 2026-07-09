from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "kubera",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={},  # Backup job will be added in Phase 1
)
