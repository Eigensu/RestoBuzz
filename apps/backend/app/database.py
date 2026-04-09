from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel
from app.config import settings
from urllib.parse import urlparse

_client: AsyncIOMotorClient | None = None


def _resolve_db_name() -> str:
    configured = (settings.mongodb_db_name or "").strip()
    if configured:
        return configured

    parsed = urlparse(settings.mongodb_url)
    uri_db = parsed.path.lstrip("/").strip()
    if uri_db:
        return uri_db

    raise ValueError(
        "MongoDB database name is missing. Set mongodb_db_name or include /<db> in mongodb_url."
    )


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_url)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client().get_database(_resolve_db_name())


def get_fresh_db() -> AsyncIOMotorDatabase:
    """Create a brand-new Motor client for use inside Celery worker tasks.
    Celery forks processes and the parent's event loop is closed in the child,
    so we must never reuse the global _client across fork boundaries."""
    client = AsyncIOMotorClient(settings.mongodb_url)
    return client.get_database(_resolve_db_name())


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
            IndexModel([("restaurant_id", ASCENDING)]),  # tenant scoping
            IndexModel(
                [("restaurant_id", ASCENDING), ("created_at", DESCENDING)]
            ),  # dashboard list sorting
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

    # restaurants
    await db.restaurants.create_index("id", unique=True)

    # user_restaurant_roles (per-restaurant access control)
    await db.user_restaurant_roles.create_indexes(
        [
            IndexModel(
                [("user_id", ASCENDING), ("restaurant_id", ASCENDING)], unique=True
            ),
            IndexModel([("restaurant_id", ASCENDING)]),
            IndexModel([("user_id", ASCENDING)]),
        ]
    )

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

    # ── Email campaign collections ────────────────────────────────────────────

    # email_campaign_jobs
    await db.email_campaign_jobs.create_indexes(
        [
            IndexModel([("status", ASCENDING)]),
            IndexModel([("restaurant_id", ASCENDING)]),
            IndexModel([("restaurant_id", ASCENDING), ("created_at", DESCENDING)]),
        ]
    )

    # email_logs — compound unique prevents duplicate sends
    await db.email_logs.create_indexes(
        [
            IndexModel([("campaign_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel(
                [("campaign_id", ASCENDING), ("recipient_email", ASCENDING)],
                unique=True,
            ),
            IndexModel(
                [("resend_email_id", ASCENDING)],
                unique=True,
                partialFilterExpression={"resend_email_id": {"$type": "string"}},
            ),
            IndexModel([("campaign_id", ASCENDING), ("created_at", DESCENDING)]),
        ]
    )

    # email_templates
    await db.email_templates.create_indexes(
        [
            IndexModel(
                [("restaurant_id", ASCENDING), ("name", ASCENDING)], unique=True
            ),
            IndexModel([("restaurant_id", ASCENDING), ("updated_at", DESCENDING)]),
        ]
    )

    # email_suppression_list — with bounce type and expiry
    await db.email_suppression_list.create_indexes(
        [
            IndexModel([("email", ASCENDING)], unique=True),
            IndexModel([("expires_at", ASCENDING)], sparse=True),
        ]
    )

    # webhook event dedup
    await db.resend_webhook_events.create_indexes(
        [
            IndexModel([("svix_id", ASCENDING)], unique=True),
            IndexModel([("received_at", ASCENDING)]),
        ]
    )

    # ── ReserveGo collections ─────────────────────────────────────────────────

    # reservego_uploads (guest profiles)
    await db.reservego_uploads.create_indexes(
        [
            IndexModel([("phone", ASCENDING), ("restaurant_id", ASCENDING)]),
            IndexModel(
                [
                    ("guest_name", ASCENDING),
                    ("email", ASCENDING),
                    ("sheet", ASCENDING),
                    ("restaurant_id", ASCENDING),
                ]
            ),
            IndexModel([("restaurant_id", ASCENDING), ("uploaded_at", DESCENDING)]),
        ]
    )

    # reservego_bill_data (booking/billing records)
    await db.reservego_bill_data.create_indexes(
        [
            IndexModel([("bill_number", ASCENDING), ("restaurant_id", ASCENDING)]),
            IndexModel(
                [
                    ("guest_name", ASCENDING),
                    ("booking_time", ASCENDING),
                    ("restaurant_id", ASCENDING),
                ]
            ),
            IndexModel([("restaurant_id", ASCENDING), ("uploaded_at", DESCENDING)]),
        ]
    )


async def close_db() -> None:
    global _client
    if _client:
        _client.close()
        _client = None
