import asyncio
from datetime import datetime, timezone
from app.workers.celery_app import celery_app
from app.database import get_fresh_db
from app.services.meta_api import fetch_templates
from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="app.workers.template_sync.sync_templates_task")
def sync_templates_task() -> None:
    asyncio.run(_sync())


async def _sync() -> None:
    db = get_fresh_db()
    try:
        templates = await fetch_templates(
            settings.meta_waba_id,
            settings.meta_primary_access_token,
        )
        for t in templates:
            await db.templates.update_one(
                {"name": t["name"], "language": t.get("language")},
                {"$set": {**t, "synced_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
        logger.info("templates_synced", count=len(templates))
    except Exception as e:
        logger.error("template_sync_failed", error=str(e))
