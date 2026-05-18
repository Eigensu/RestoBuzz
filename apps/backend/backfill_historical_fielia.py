"""
Backfill 575 historical inbound messages to Fielia (r2).

These messages came in on phone 936956752843517 (Fielia's number) between
March 23 - April 18, 2026, before wa_phone_ids was configured. They have
restaurant_id=None and no wa_phone_id field.
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

FIELIA_PHONE_ID = "936956752843517"
FIELIA_RESTAURANT_ID = "r2"


async def backfill():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]

    # Stamp restaurant_id AND wa_phone_id on all None-rid messages
    # (they all came from Fielia's number based on the date range)
    result = await db.inbound_messages.update_many(
        {"restaurant_id": None},
        {
            "$set": {
                "restaurant_id": FIELIA_RESTAURANT_ID,
                "wa_phone_id": FIELIA_PHONE_ID,
            }
        },
    )
    print(f"Backfilled {result.modified_count} historical messages to r2 (Fielia)")

    # Verify
    total_r2 = await db.inbound_messages.count_documents(
        {"restaurant_id": FIELIA_RESTAURANT_ID}
    )
    print(f"Total inbound messages for r2 now: {total_r2}")

    client.close()


if __name__ == "__main__":
    asyncio.run(backfill())
