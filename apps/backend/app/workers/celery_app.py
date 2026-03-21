from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "whatsapp_bulk",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.send_task",
        "app.workers.webhook_task",
        "app.workers.template_sync",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_queues={
        "utility": {"exchange": "utility", "routing_key": "utility"},
        "marketing": {"exchange": "marketing", "routing_key": "marketing"},
    },
    task_default_queue="marketing",
    task_routes={
        "app.workers.send_task.send_message_task": {
            # Queue set dynamically per task
        },
    },
    beat_schedule={
        "sync-templates-every-6h": {
            "task": "app.workers.template_sync.sync_templates_task",
            "schedule": crontab(minute=0, hour="*/6"),
        },
    },
)
