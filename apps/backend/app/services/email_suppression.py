"""Email suppression list management with bounce-type expiry logic."""
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase


# Soft bounces retry after 7 days; hard bounces & complaints are permanent
SOFT_BOUNCE_EXPIRY_DAYS = 7


async def is_email_suppressed(db: AsyncIOMotorDatabase, email: str) -> bool:
    """Check if an email address is currently suppressed."""
    doc = await db.email_suppression_list.find_one({"email": email.lower()})
    if doc is None:
        return False
    # Check expiry for soft bounces
    expires_at = doc.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        # Expired soft bounce — remove and allow
        await db.email_suppression_list.delete_one({"_id": doc["_id"]})
        return False
    return True


async def add_email_suppression(
    db: AsyncIOMotorDatabase,
    email: str,
    reason: str = "hard_bounce",
) -> None:
    """Add an email to the suppression list.
    reason: 'hard_bounce' | 'soft_bounce' | 'complaint'
    """
    now = datetime.now(timezone.utc)
    expires_at = None
    if reason == "soft_bounce":
        expires_at = now + timedelta(days=SOFT_BOUNCE_EXPIRY_DAYS)

    await db.email_suppression_list.update_one(
        {"email": email.lower()},
        {
            "$setOnInsert": {
                "email": email.lower(),
                "reason": reason,
                "added_at": now,
                "expires_at": expires_at,
            }
        },
        upsert=True,
    )
