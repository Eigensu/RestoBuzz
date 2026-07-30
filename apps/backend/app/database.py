"""Database connection and index management."""
# pylint: disable=global-statement
import logging
import time
from urllib.parse import urlparse

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import OperationFailure

from app.config import settings

logger = logging.getLogger(__name__)
MONGO_TYPE_STRING = "$type"

# Retention window for message_logs (delivery audit rows). Tune here; the TTL
# index below deletes rows whose created_at is older than this. Changing the
# value re-reconciles the index on next startup via safe_create_indexes.
MESSAGE_LOG_TTL_DAYS = 30

_client: AsyncIOMotorClient | None = None
_fielia_client: AsyncIOMotorClient | None = None


async def close_db() -> None:
    """Gracefully close all global database connections."""
    global _client, _fielia_client
    if _client:
        _client.close()
        _client = None
    if _fielia_client:
        _fielia_client.close()
        _fielia_client = None
    logger.info("Database connections closed.")


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
    """Get the global MongoDB client instance."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_url)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    """Get the global MongoDB database instance."""
    return get_client().get_database(_resolve_db_name())


def get_fresh_db() -> AsyncIOMotorDatabase:
    """Create a brand-new Motor client for use inside Celery worker tasks.
    Celery forks processes and the parent's event loop is closed in the child,
    so we must never reuse the global _client across fork boundaries."""
    client = AsyncIOMotorClient(settings.mongodb_url)
    return client.get_database(_resolve_db_name())


def get_fielia_db() -> AsyncIOMotorDatabase | None:
    """Connect to the external Fielia database if configured (singleton)."""
    global _fielia_client
    if not settings.fielia_mongo_uri:
        return None

    if _fielia_client is None:
        _fielia_client = AsyncIOMotorClient(settings.fielia_mongo_uri)

    parsed = urlparse(settings.fielia_mongo_uri)
    db_name = parsed.path.lstrip("/").strip() or "fielia"
    return _fielia_client.get_database(db_name)


def _get_conflict_name(
    idx_name: str, index: IndexModel, existing_indexes: dict
) -> str | None:
    if idx_name in existing_indexes:
        return idx_name

    # Match by key signature if names differ but keys overlap
    req_keys = list(index.document["key"].items())
    for ext_name, ext_info in existing_indexes.items():
        if ext_info.get("key") == req_keys:
            return ext_name
    return None


async def _validate_unique_constraint(
    collection, index: IndexModel, idx_name: str
) -> bool:
    if not index.document.get("unique"):
        return True

    # Map index keys to field paths for grouping (e.g. {"email": 1} -> {"email": "$email"})
    group_id = {k: f"${k}" for k in index.document["key"].keys()}
    partial_filter = index.document.get("partialFilterExpression", {})

    pipeline = [
        {"$match": partial_filter},
        {"$group": {"_id": group_id, "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 1},
    ]
    cursor = collection.aggregate(pipeline)
    violation = await cursor.to_list(length=1)
    if violation:
        logger.error(
            "VALIDATION FAILED for '%s': Data violates unique constraint. "
            "Conflict: %s. Migration skipped to prevent data loss.",
            idx_name,
            violation[0]["_id"],
        )
        return False
    return True


async def _migrate_index_additive(
    collection, index: IndexModel, idx_name: str, conflict_name: str
) -> None:
    v_suffix = f"v{int(time.time())}"
    v_name = f"{idx_name}_{v_suffix}"
    logger.info("Migration: Building versioned index '%s'...", v_name)

    # Clone parameters for the versioned build
    v_params = {k: v for k, v in index.document.items() if k not in ["key", "name"]}
    v_model = IndexModel(list(index.document["key"].items()), name=v_name, **v_params)

    try:
        # Build versioned index
        await collection.create_indexes([v_model])
        logger.info("Migration: Versioned index '%s' built successfully.", v_name)

        # Swap and Revert to Canonical
        logger.info("Migration: Dropping legacy index '%s'", conflict_name)
        await collection.drop_index(conflict_name)

        logger.info("Migration: Restoring canonical name '%s'", idx_name)
        await collection.create_indexes([index])

        logger.info("Migration: Cleaning up versioned index '%s'", v_name)
        await collection.drop_index(v_name)
        logger.info("Migration: '%s' successfully reconciled.", idx_name)

    except OperationFailure as rebuild_e:
        logger.warning(
            "Migration: Additive build failed for '%s' due to: %s. "
            "Attempting destructive swap fallback (dropping '%s' first)...",
            idx_name,
            rebuild_e.details,
            conflict_name,
        )
        try:
            logger.info("Migration: Dropping conflicting index '%s'", conflict_name)
            await collection.drop_index(conflict_name)
            logger.info("Migration: Rebuilding canonical index '%s'", idx_name)
            await collection.create_indexes([index])
            logger.info(
                "Migration: '%s' successfully reconciled via destructive swap.",
                idx_name,
            )
        except OperationFailure as destructive_e:
            logger.error(
                "Migration CRASHED during destructive rebuild of '%s': %s. "
                "Startup proceeding in degraded state.",
                idx_name,
                destructive_e.details,
            )


async def _reconcile_conflicts(
    collection, indexes: list[IndexModel], existing_indexes: dict
) -> None:
    """Internal helper to iterate and resolve conflicting indexes one-by-one."""
    for index in indexes:
        idx_name = index.document.get("name") or "_".join(
            [f"{k}_{v}" for k, v in index.document["key"].items()]
        )
        try:
            await collection.create_indexes([index])
        except OperationFailure as inner_e:
            if inner_e.code not in (85, 86):
                raise inner_e

            conflict_name = _get_conflict_name(idx_name, index, existing_indexes)
            if not conflict_name or conflict_name == "_id_":
                continue

            if await _validate_unique_constraint(collection, index, idx_name):
                await _migrate_index_additive(
                    collection, index, idx_name, conflict_name
                )


async def safe_create_indexes(collection, indexes: list[IndexModel]) -> None:
    """Enterprise-safe index reconciliation for Motor/PyMongo."""
    start_time = time.perf_counter()
    logger.info("Indexing startup: reconciliation began for '%s'", collection.name)

    try:
        await collection.create_indexes(indexes)
    except OperationFailure as e:
        if e.code not in (85, 86):
            raise e

        logger.warning(
            "Index conflict in '%s'. Initiating reconciliation...", collection.name
        )
        existing_indexes = await collection.index_information()
        await _reconcile_conflicts(collection, indexes, existing_indexes)

    duration = time.perf_counter() - start_time
    logger.info("Indexing complete: '%s' in %.3fs", collection.name, duration)


async def init_indexes() -> None:
    """Initialize all MongoDB indexes."""
    db = get_db()

    # users
    await safe_create_indexes(
        db.users, [IndexModel([("email", ASCENDING)], unique=True)]
    )

    # campaign_jobs
    await safe_create_indexes(
        db.campaign_jobs,
        [
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_by", ASCENDING)]),
            IndexModel([("scheduled_at", ASCENDING)]),
            IndexModel([("restaurant_id", ASCENDING)]),  # tenant scoping
            IndexModel(
                [("restaurant_id", ASCENDING), ("created_at", DESCENDING)]
            ),  # dashboard list sorting
            IndexModel(
                [
                    ("smart_retries", ASCENDING),
                    ("status", ASCENDING),
                    ("retry_until", ASCENDING),
                    ("parent_campaign_id", ASCENDING),
                    ("last_auto_retry_at", ASCENDING),
                ]
            ),  # smart retries poller
        ],
    )

    # message_logs
    await safe_create_indexes(
        db.message_logs,
        [
            IndexModel([("job_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel(
                [("wa_message_id", ASCENDING)],
                unique=True,
                partialFilterExpression={
                    "wa_message_id": {MONGO_TYPE_STRING: "string"}
                },
            ),
            IndexModel([("locked_until", ASCENDING)]),
            IndexModel([("job_id", ASCENDING), ("created_at", DESCENDING)]),
            # For reports delivery log filtering
            IndexModel(
                [
                    ("job_id", ASCENDING),
                    ("status", ASCENDING),
                    ("created_at", DESCENDING),
                ]
            ),
            # Retention cap: delivery logs auto-expire after MESSAGE_LOG_TTL_DAYS.
            # message_logs are operational send records — the delivered WhatsApp
            # messages and inbox conversations are unaffected. Keeps the
            # collection from growing unbounded (see prune_status_history.py for
            # the lighter-touch status_history-only cleanup).
            IndexModel(
                [("created_at", ASCENDING)],
                expireAfterSeconds=60 * 60 * 24 * MESSAGE_LOG_TTL_DAYS,
            ),
        ],
    )

    # inbound_messages
    await safe_create_indexes(
        db.inbound_messages,
        [
            IndexModel([("wa_message_id", ASCENDING)], unique=True),
            # Covering index for the conversation-list pipeline:
            # $match (is_resolved ≠ true, received_at ≥ since)
            # → $sort (from_phone ASC, received_at DESC)
            # → $group $first (most-recent message per phone)
            # Having is_resolved + received_at + from_phone in a single index lets
            # MongoDB satisfy the match, sort, and group without a collection scan.
            IndexModel(
                [
                    ("is_resolved", ASCENDING),
                    ("received_at", DESCENDING),
                    ("from_phone", ASCENDING),
                ]
            ),
            # Per-restaurant conversation list (new scoped queries)
            IndexModel(
                [
                    ("restaurant_id", ASCENDING),
                    ("is_resolved", ASCENDING),
                    ("received_at", DESCENDING),
                ]
            ),
            # Per-restaurant per-phone thread queries
            IndexModel(
                [
                    ("restaurant_id", ASCENDING),
                    ("from_phone", ASCENDING),
                    ("received_at", DESCENDING),
                ]
            ),
            # Retained for backwards-compat with per-phone thread queries.
            IndexModel([("from_phone", ASCENDING), ("received_at", DESCENDING)]),
            # Partial index for the unread-count query (is_read=False, is_resolved≠true).
            IndexModel(
                [("is_read", ASCENDING), ("is_resolved", ASCENDING)],
                partialFilterExpression={"is_read": False},
            ),
            # Per-restaurant unread count
            IndexModel(
                [("restaurant_id", ASCENDING), ("is_read", ASCENDING)],
                partialFilterExpression={"is_read": False},
            ),
        ],
    )

    # outbound_messages
    await safe_create_indexes(
        db.outbound_messages,
        [
            IndexModel([("wa_message_id", ASCENDING)], unique=True, sparse=True),
            # Per-restaurant thread queries (new scoped path)
            IndexModel(
                [
                    ("restaurant_id", ASCENDING),
                    ("to_phone", ASCENDING),
                    ("sent_at", DESCENDING),
                ]
            ),
            # Legacy unscoped path (migration fallback — can be dropped after backfill)
            IndexModel([("to_phone", ASCENDING), ("sent_at", DESCENDING)]),
        ],
    )

    # members
    await safe_create_indexes(
        db.members,
        [
            IndexModel(
                [("restaurant_id", ASCENDING), ("phone", ASCENDING)], unique=True
            ),
            IndexModel(
                [("restaurant_id", ASCENDING), ("normalized_phone", ASCENDING)],
                unique=True,
                partialFilterExpression={"normalized_phone": {"$type": "string"}},
            ),
            IndexModel([("restaurant_id", ASCENDING), ("type", ASCENDING)]),
            IndexModel([("restaurant_id", ASCENDING), ("last_visit", DESCENDING)]),
            IndexModel([("restaurant_id", ASCENDING), ("joined_at", DESCENDING)]),
            IndexModel([("card_uid", ASCENDING)], sparse=True),
            IndexModel([("ecard_code", ASCENDING)], sparse=True),
            # For dormant member report query
            IndexModel(
                [
                    ("restaurant_id", ASCENDING),
                    ("is_active", ASCENDING),
                    ("last_visit", ASCENDING),
                ]
            ),
        ],
    )

    # suppression_list
    await safe_create_indexes(
        db.suppression_list, [IndexModel([("phone", ASCENDING)], unique=True)]
    )

    # restaurants
    await safe_create_indexes(
        db.restaurants, [IndexModel([("id", ASCENDING)], unique=True)]
    )

    # user_restaurant_roles (per-restaurant access control)
    await safe_create_indexes(
        db.user_restaurant_roles,
        [
            IndexModel(
                [("user_id", ASCENDING), ("restaurant_id", ASCENDING)], unique=True
            ),
            IndexModel([("restaurant_id", ASCENDING)]),
            IndexModel([("user_id", ASCENDING)]),
        ],
    )

    # contact_files
    await safe_create_indexes(
        db.contact_files,
        [
            IndexModel([("filename", ASCENDING), ("hash", ASCENDING)], unique=True),
            IndexModel([("uploaded_at", DESCENDING)]),
        ],
    )

    # audit_logs
    await safe_create_indexes(
        db.audit_logs,
        [
            IndexModel([("user_id", ASCENDING), ("timestamp", DESCENDING)]),
            IndexModel([("resource_type", ASCENDING)]),
        ],
    )

    # ── Email campaign collections ────────────────────────────────────────────

    # email_campaign_jobs
    await safe_create_indexes(
        db.email_campaign_jobs,
        [
            IndexModel([("status", ASCENDING)]),
            IndexModel([("restaurant_id", ASCENDING)]),
            IndexModel([("restaurant_id", ASCENDING), ("created_at", DESCENDING)]),
        ],
    )

    # email_logs — compound unique prevents duplicate sends
    await safe_create_indexes(
        db.email_logs,
        [
            IndexModel([("campaign_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel(
                [("campaign_id", ASCENDING), ("recipient_email", ASCENDING)],
                unique=True,
            ),
            IndexModel(
                [("resend_email_id", ASCENDING)],
                unique=True,
                partialFilterExpression={
                    "resend_email_id": {MONGO_TYPE_STRING: "string"}
                },
            ),
            IndexModel([("campaign_id", ASCENDING), ("created_at", DESCENDING)]),
        ],
    )

    # email_alert_logs — Operational/System alerts
    await safe_create_indexes(
        db.email_alert_logs,
        [
            # Redundant created_at descending index removed (handled by TTL index reverse traversal)
            IndexModel([("restaurant_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel(
                [
                    ("alert_type", ASCENDING),
                    ("context.template_name", ASCENDING),
                    ("created_at", DESCENDING),
                ]
            ),
            IndexModel([("status", ASCENDING)]),
            # 90-day retention for operational logs
            IndexModel(
                [("created_at", ASCENDING)], expireAfterSeconds=60 * 60 * 24 * 90
            ),
        ],
    )

    # email_templates
    await safe_create_indexes(
        db.email_templates,
        [
            IndexModel(
                [("restaurant_id", ASCENDING), ("name", ASCENDING)], unique=True
            ),
            IndexModel([("restaurant_id", ASCENDING), ("updated_at", DESCENDING)]),
        ],
    )

    # email_suppression_list — with bounce type and expiry
    await safe_create_indexes(
        db.email_suppression_list,
        [
            IndexModel([("email", ASCENDING)], unique=True),
            IndexModel([("expires_at", ASCENDING)], sparse=True),
        ],
    )

    # webhook event dedup
    await safe_create_indexes(
        db.resend_webhook_events,
        [
            IndexModel([("svix_id", ASCENDING)], unique=True),
            IndexModel([("received_at", ASCENDING)]),
        ],
    )

    # ── ReserveGo collections ─────────────────────────────────────────────────

    # reservego_uploads (guest profiles)
    await safe_create_indexes(
        db.reservego_uploads,
        [
            IndexModel([("phone", ASCENDING), ("restaurant_id", ASCENDING)]),
            IndexModel([("normalized_phone", ASCENDING), ("restaurant_id", ASCENDING)]),
            IndexModel([("uploaded_at", ASCENDING)]),
            IndexModel([("uuid", ASCENDING)], sparse=True),
            IndexModel(
                [
                    ("guest_name", ASCENDING),
                    ("email", ASCENDING),
                    ("sheet", ASCENDING),
                    ("restaurant_id", ASCENDING),
                ]
            ),
            IndexModel([("restaurant_id", ASCENDING), ("uploaded_at", DESCENDING)]),
        ],
    )

    # reservego_bill_data (booking/billing records)
    await safe_create_indexes(
        db.reservego_bill_data,
        [
            IndexModel([("bill_number", ASCENDING), ("restaurant_id", ASCENDING)]),
            IndexModel([("phone", ASCENDING), ("restaurant_id", ASCENDING)]),
            IndexModel([("uuid", ASCENDING)], sparse=True),
            IndexModel(
                [
                    ("guest_name", ASCENDING),
                    ("booking_time", ASCENDING),
                    ("restaurant_id", ASCENDING),
                ]
            ),
            IndexModel([("restaurant_id", ASCENDING), ("uploaded_at", DESCENDING)]),
        ],
    )

    # meta_billing_events (WhatsApp conversation pricing from webhooks)
    await safe_create_indexes(
        db.meta_billing_events,
        [
            IndexModel([("wa_message_id", ASCENDING)], unique=True),
            IndexModel([("restaurant_id", ASCENDING), ("recorded_at", DESCENDING)]),
            IndexModel([("restaurant_id", ASCENDING), ("category", ASCENDING)]),
        ],
    )

    # sync_metadata (tracking synchronization checkpoints)
    await safe_create_indexes(
        db.sync_metadata,
        [
            IndexModel([("sync_name", ASCENDING)], unique=True),
        ],
    )

    # templates — scoped per restaurant
    await safe_create_indexes(
        db.templates,
        [
            # Unique per (restaurant, name, language) — prevents two restaurants
            # clobbering each other's templates with the same name.
            # partialFilterExpression ensures legacy docs without restaurant_id
            # are excluded from the unique constraint.
            IndexModel(
                [
                    ("restaurant_id", ASCENDING),
                    ("name", ASCENDING),
                    ("language", ASCENDING),
                ],
                unique=True,
                partialFilterExpression={"restaurant_id": {"$type": "string"}},
            ),
            IndexModel([("restaurant_id", ASCENDING), ("status", ASCENDING)]),
        ],
    )
