"""Campaign service logic including WABA resolution and retry handling."""

from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.constants.meta_errors import RETRYABLE_FAILED_MATCH
from app.core.errors import ServerError
from app.core.logging import get_logger

from app.config import settings
from app.models.campaign import CampaignCreateInternal

logger = get_logger(__name__)


async def resolve_waba_credentials(
    db: AsyncIOMotorDatabase, restaurant_id: str
) -> tuple[str | None, str | None, str | None]:
    """Return (phone_id, access_token, env_key) for the restaurant's primary WABA.

    phone_id is read from MongoDB.
    access_token is resolved from the env var named by access_token_env_key.
    """
    rest_doc = await db.restaurants.find_one({"id": restaurant_id}, {"wa_phones": 1})
    wa_phones = (rest_doc or {}).get("wa_phones", [])
    if not wa_phones:
        return None, None, None
    primary = wa_phones[0]
    phone_id = primary.get("phone_id") or None
    env_key = primary.get("access_token_env_key") or ""
    access_token = settings.resolve_waba_token(env_key) if env_key else None
    return phone_id, access_token, env_key or None


async def create_child_retry_campaign(
    original: dict,
    failed_count: int,
    db: AsyncIOMotorDatabase,
    current_user_id: str,
) -> str:
    """Create a child retry campaign for failed messages in the given campaign."""
    now = datetime.now(timezone.utc)
    retry_restaurant_id = original.get("restaurant_id")
    campaign_oid = original["_id"]

    # Walk up to find the root campaign so all retries share the same root
    root_id = original.get("parent_campaign_id") or campaign_oid

    # Naming logic: strip existing " (retry)" if present to prevent "(retry) (retry)" accumulation
    base_name = original["name"]
    if base_name.endswith(" (retry)"):
        base_name = base_name[:-8]
    new_name = f"{base_name} (retry)"

    internal_data = {
        "restaurant_id": retry_restaurant_id,
        "name": new_name,
        "template_id": original.get("template_id", ""),
        "template_name": original["template_name"],
        "template_variables": original.get("template_variables", {}),
        "priority": original.get("priority", "MARKETING"),
        "contact_file_ref": original.get("contact_file_ref"),  # None for old campaigns
        "include_unsubscribe": original.get("include_unsubscribe", False),
        "media_url": original.get("media_url"),
        "media_type": original.get("media_type"),
        "smart_retries": original.get("smart_retries", False),
        "retry_until": original.get("retry_until"),
        "parent_campaign_id": str(root_id),  # Convert ObjectId to str
        "has_been_retried": False,
        "completed_at": None,
        "scheduled_at": None,
    }

    validated_job = CampaignCreateInternal(**internal_data)

    job_doc = validated_job.dict()
    # Add fields not in CampaignCreateInternal that the system manages directly
    job_doc.update(
        {
            "status": "queued",
            "total_count": failed_count,
            "sent_count": 0,
            "delivered_count": 0,
            "read_count": 0,
            "failed_count": 0,
            "replies_count": 0,
            "started_at": None,
            "created_by": current_user_id,
            "created_at": now,
        }
    )

    result = await db.campaign_jobs.insert_one(job_doc)
    job_id = result.inserted_id

    failed_query = {"job_id": campaign_oid, **RETRYABLE_FAILED_MATCH}
    cursor = db.message_logs.find(failed_query)
    batch_size = 1000
    new_logs_batch = []

    wa_phone_id, _token, wa_access_token_env_key = await resolve_waba_credentials(
        db, retry_restaurant_id
    )

    try:
        async for log in cursor:
            new_logs_batch.append(
                {
                    "job_id": job_id,
                    "restaurant_id": retry_restaurant_id,
                    "recipient_phone": log["recipient_phone"],
                    "recipient_name": log.get("recipient_name", ""),
                    "template_name": log["template_name"],
                    "template_variables": log.get("template_variables", {}),
                    "media_url": log.get("media_url"),
                    "media_type": log.get("media_type"),
                    "status": "queued",
                    "retry_count": 0,
                    "endpoint_used": None,
                    "fallback_used": False,
                    "error_code": None,
                    "error_message": None,
                    "status_history": [],
                    "wa_phone_id": wa_phone_id,
                    "wa_access_token_env_key": wa_access_token_env_key,
                    "created_at": now,
                    "updated_at": now,
                    "locked_until": None,
                }
            )

            if len(new_logs_batch) >= batch_size:
                await db.message_logs.insert_many(new_logs_batch)
                new_logs_batch = []

        if new_logs_batch:
            await db.message_logs.insert_many(new_logs_batch)

    except Exception as exc:
        # Roll back the claim flag so the user can attempt a retry again.
        await db.campaign_jobs.update_one(
            {"_id": campaign_oid},
            {"$unset": {"has_been_retried": "", "retry_claimed_at": ""}},
        )
        await db.campaign_jobs.delete_one({"_id": job_id})
        await db.message_logs.delete_many({"job_id": job_id})
        logger.error(
            "retry_failed_message_log_insert_error",
            campaign_id=str(campaign_oid),
            error=str(exc),
        )
        raise ServerError("Failed to create retry message logs") from exc

    return str(job_id)
