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
    """Sync templates for every restaurant that has wa_phones configured.

    Each restaurant has its own WABA, so we fetch templates separately per
    restaurant and scope all upserts/prunes by restaurant_id.

    Restaurants without wa_phones configured are skipped — they have no
    independent WABA to sync from.
    """
    db = get_fresh_db()
    total_synced = 0

    try:
        # Only process restaurants that have at least one wa_phone configured
        cursor = db.restaurants.find(
            {"wa_phones.0": {"$exists": True}},
            {"id": 1, "name": 1, "wa_phones": 1},
        )

        async for rest in cursor:
            rid = rest.get("id") or str(rest["_id"])
            primary = rest["wa_phones"][0]
            waba_id = primary.get("waba_id") or ""
            env_key = primary.get("access_token_env_key") or ""
            token = settings.resolve_waba_token(env_key) if env_key else ""

            if not waba_id or not token:
                logger.warning(
                    "template_sync_skipped_missing_credentials",
                    restaurant_id=rid,
                    has_waba_id=bool(waba_id),
                    has_token=bool(token),
                )
                continue

            try:
                templates = await fetch_templates(waba_id, token)
            except Exception as e:
                logger.error(
                    "template_sync_fetch_failed",
                    restaurant_id=rid,
                    error=str(e),
                )
                continue

            synced_keys: list[dict] = []
            for t in templates:
                lang = t.get("language")
                key: dict = {"name": t["name"], "restaurant_id": rid}
                if lang:
                    key["language"] = lang

                update_fields = {
                    **t,
                    "restaurant_id": rid,
                    "synced_at": datetime.now(timezone.utc),
                }
                # Meta returns the template id as "id"; store it as "meta_id"
                # so PATCH /templates/{name} can push edits back to Meta.
                meta_id = update_fields.pop("id", None)
                if meta_id:
                    update_fields["meta_id"] = str(meta_id)

                await db.templates.update_one(
                    key,
                    {"$set": update_fields},
                    upsert=True,
                )
                synced_keys.append(key)

            # Prune templates removed from Meta for this restaurant
            if synced_keys:
                await db.templates.delete_many(
                    {"restaurant_id": rid, "$nor": synced_keys}
                )
            else:
                await db.templates.delete_many({"restaurant_id": rid})

            total_synced += len(templates)
            logger.info(
                "templates_synced_for_restaurant",
                restaurant_id=rid,
                count=len(templates),
            )

        logger.info("template_sync_complete", total=total_synced)

    except Exception as e:
        logger.error("template_sync_failed", error=str(e))
