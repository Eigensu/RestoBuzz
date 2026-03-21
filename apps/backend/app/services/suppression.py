from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase


async def is_suppressed(db: AsyncIOMotorDatabase, phone: str) -> bool:
    doc = await db.suppression_list.find_one({"phone": phone})
    return doc is not None


async def add_suppression(
    db: AsyncIOMotorDatabase,
    phone: str,
    reason: str = "opt_out",
    added_by: str | None = None,
) -> None:
    await db.suppression_list.update_one(
        {"phone": phone},
        {"$setOnInsert": {
            "phone": phone,
            "reason": reason,
            "added_by": added_by,
            "added_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
