"""Storage and retrieval of an uploaded contact list between wizard steps.

A list is written twice: to Redis for the hour the campaign wizard is likely to
stay open, and to the `contact_files` collection so it can be picked from the
saved-files list on a later visit. Member-sourced lists (members.as_contacts)
live in Redis alone — they are derived from data already in the database, so
there is nothing worth saving.

Both stores are keyed by the uploader as well as the reference. The reference on
its own is a UUID4: unguessable, but not an access control. It travels in API
responses, browser network logs and support threads, and a caller holding one
could otherwise send a real campaign to another account's guest list and then
read those recipients back out of their own message logs.
"""

import json

from motor.motor_asyncio import AsyncIOMotorDatabase
from redis.asyncio import from_url

from app.config import settings
from app.core.errors import ContactFileExpiredError
from app.core.logging import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 3600
RESULT_FILE_REF_KEY = "result.file_ref"


def cache_key(file_ref: str, owner_id: str) -> str:
    """Redis key for one owner's copy of a contact list.

    Scoping the key rather than checking the value means a reference presented
    by the wrong caller simply misses, and falls through to the Mongo lookup,
    which is scoped the same way.
    """
    return f"file_ref:{owner_id}:{file_ref}"


async def cache_contacts(file_ref: str, rows: list, owner_id: str) -> None:
    """Cache a parsed contact list. Failure is logged, never raised — the
    Mongo copy backs this up for uploads, so a Redis outage must not fail
    the request."""
    try:
        redis = from_url(settings.redis_url, decode_responses=True)
        await redis.ping()  # Minimal connection check
        await redis.set(
            cache_key(file_ref, owner_id),
            json.dumps([r.model_dump() for r in rows]),
            ex=CACHE_TTL_SECONDS,
        )
        await redis.aclose()
    except Exception as e:
        logger.warning(
            "contact_file_cache_failed",
            file_ref=file_ref,
            error=str(e),
            detail=(
                "Contact file caching skipped. Uploads fall back to MongoDB on "
                "campaign creation; member lists must be reselected."
            ),
        )


async def load_contacts(
    db: AsyncIOMotorDatabase, file_ref: str, owner_id: str
) -> list[dict]:
    """Return the contact rows behind `file_ref` for `owner_id`.

    Redis first, then the saved copy in Mongo. Both are scoped to the owner, so
    a reference belonging to somebody else reads as expired rather than
    resolving. Raises ContactFileExpiredError when neither store has it.
    """
    raw = None
    redis = None
    try:
        redis = from_url(settings.redis_url, decode_responses=True)
        raw = await redis.get(cache_key(file_ref, owner_id))
    except Exception as e:
        # A cache outage is not fatal for an upload; Mongo still has it.
        logger.warning(
            "contact_file_cache_unavailable", file_ref=file_ref, error=str(e)
        )
    finally:
        if redis is not None:
            await redis.aclose()

    if raw:
        return json.loads(raw)

    doc = await db.contact_files.find_one(
        {RESULT_FILE_REF_KEY: file_ref, "uploaded_by": owner_id}
    )
    if not doc:
        raise ContactFileExpiredError(
            "Contact file reference expired or not found. Please re-upload your contacts."
        )
    return doc["result"]["valid_rows"]
