"""Background alert tasks executed via Celery.

These tasks move blocking email fan-out work entirely off the HTTP request path
so endpoints return immediately and retries are handled by the broker.
"""

import asyncio
from app.workers.celery_app import celery_app
from app.database import get_fresh_db
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(
    name="app.workers.alert_tasks.send_template_approval_alert_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="utility",
)
def send_template_approval_alert_task(
    self, template_name: str, language: str, category: str
) -> None:
    """Fan out template-approved emails to all restaurant admins."""
    asyncio.run(
        _run_template_approval_alert(self, template_name, language, category)
    )


async def _run_template_approval_alert(
    task, template_name: str, language: str, category: str
) -> None:
    db = get_fresh_db()
    try:
        from app.services.alert_service import handle_template_approval_alert

        await handle_template_approval_alert(db, template_name, language, category)
    except Exception as exc:
        logger.exception(
            "template_approval_alert_task_failed",
            template_name=template_name,
            language=language,
        )
        raise task.retry(exc=exc)


@celery_app.task(
    name="app.workers.alert_tasks.send_unread_threshold_alert_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="utility",
)
def send_unread_threshold_alert_task(self, restaurant_id: str) -> None:
    """Check and send unread-message threshold alert for a single restaurant."""
    asyncio.run(_run_unread_threshold_alert(self, restaurant_id))


async def _run_unread_threshold_alert(task, restaurant_id: str) -> None:
    db = get_fresh_db()
    try:
        from app.services.alert_service import check_unread_threshold_alert

        await check_unread_threshold_alert(db, restaurant_id)
    except Exception as exc:
        logger.exception(
            "unread_threshold_alert_task_failed",
            restaurant_id=restaurant_id,
        )
        raise task.retry(exc=exc)
