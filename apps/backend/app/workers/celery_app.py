from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "dishpatch",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.send_task",
        "app.workers.webhook_task",
        "app.workers.template_sync",
        "app.workers.send_email_task",
        "app.workers.email_reconciliation_task",
        "app.workers.scheduled_poller",
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
        "email": {"exchange": "email", "routing_key": "email"},
    },
    task_default_queue="marketing",
    task_routes={
        "app.workers.send_task.send_message_task": {
            # Queue set dynamically per task
        },
        "app.workers.send_email_task.send_single_email_task": {
            "queue": "email",
        },
    },
    beat_schedule={
        "sync-templates-every-6h": {
            "task": "app.workers.template_sync.sync_templates_task",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "reconcile-email-statuses-every-30m": {
            "task": "app.workers.email_reconciliation_task.reconcile_email_statuses",
            "schedule": crontab(minute="*/30"),
        },
        "poll-scheduled-campaigns-every-minute": {
            "task": "app.workers.scheduled_poller.poll_scheduled_campaigns",
            "schedule": crontab(minute="*"),
        },
    },
)
