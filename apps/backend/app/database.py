from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel
from app.config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_url)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client().get_default_database(settings.mongodb_db_name)


def get_fresh_db() -> AsyncIOMotorDatabase:
    """Create a brand-new Motor client for use inside Celery worker tasks.
    Celery forks processes and the parent's event loop is closed in the child,
    so we must never reuse the global _client across fork boundaries."""
    client = AsyncIOMotorClient(settings.mongodb_url)
    return client.get_default_database(settings.mongodb_db_name)


async def init_indexes() -> None:
    db = get_db()

    # users
    await db.users.create_index("email", unique=True)

    # campaign_jobs
    await db.campaign_jobs.create_indexes(
        [
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_by", ASCENDING)]),
            IndexModel([("scheduled_at", ASCENDING)]),
        ]
    )

    # message_logs
    await db.message_logs.create_indexes(
        [
            IndexModel([("job_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel(
                [("wa_message_id", ASCENDING)],
                unique=True,
                partialFilterExpression={"wa_message_id": {"$type": "string"}},
            ),
            IndexModel([("locked_until", ASCENDING)]),
            IndexModel([("job_id", ASCENDING), ("created_at", DESCENDING)]),
        ]
    )

    # inbound_messages
    await db.inbound_messages.create_indexes(
        [
            IndexModel([("wa_message_id", ASCENDING)], unique=True),
            IndexModel([("from_phone", ASCENDING), ("received_at", DESCENDING)]),
            IndexModel([("is_read", ASCENDING)]),
        ]
    )

    # members
    await db.members.create_indexes(
        [
            IndexModel(
                [("restaurant_id", ASCENDING), ("phone", ASCENDING)], unique=True
            ),
            IndexModel([("restaurant_id", ASCENDING), ("type", ASCENDING)]),
            IndexModel([("restaurant_id", ASCENDING), ("joined_at", DESCENDING)]),
            IndexModel([("card_uid", ASCENDING)], sparse=True),
            IndexModel([("ecard_code", ASCENDING)], sparse=True),
        ]
    )

    # suppression_list
    await db.suppression_list.create_index("phone", unique=True)

    # contact_files
    await db.contact_files.create_indexes(
        [
            IndexModel([("filename", ASCENDING), ("hash", ASCENDING)], unique=True),
            IndexModel([("uploaded_at", DESCENDING)]),
        ]
    )

    # audit_logs
    await db.audit_logs.create_indexes(
        [
            IndexModel([("user_id", ASCENDING), ("timestamp", DESCENDING)]),
            IndexModel([("resource_type", ASCENDING)]),
        ]
    )


async def close_db() -> None:
    global _client
    if _client:
        _client.close()
        _client = None
