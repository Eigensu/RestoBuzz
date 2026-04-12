import asyncio
from datetime import timedelta
from app.config import settings
from motor.motor_asyncio import AsyncIOMotorClient


async def analyze():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name)

    # Total inbound messages
    total_inbound = await db.inbound_messages.count_documents({})
    print(f"Total inbound messages: {total_inbound}")

    # Inbound messages with context.id
    with_context = await db.inbound_messages.count_documents(
        {"raw_payload.context.id": {"$exists": True}}
    )
    print(f"Inbound messages with context.id: {with_context}")

    # Check messages without context.id and see if they belong to a user who received a campaign recently
    # Limit to latest 100 for speed
    cursor = (
        db.inbound_messages.find({"raw_payload.context.id": {"$exists": False}})
        .sort("received_at", -1)
        .limit(100)
    )

    found_campaign = 0
    async for msg in cursor:
        phone = msg.get("from_phone")
        dt = msg.get("received_at")
        if phone and dt:
            # find last outbound message sent to this phone within 48 hrs before this message
            last_out = await db.message_logs.find_one(
                {
                    "recipient_phone": phone,
                    "created_at": {"$lte": dt, "$gte": dt - timedelta(hours=48)},
                },
                sort=[("created_at", -1)],
            )

            if last_out:
                found_campaign += 1

    print(
        f"Out of 100 recent inbound messages without context.id, {found_campaign} had a recent outbound campaign message to that phone."
    )

    client.close()


if __name__ == "__main__":
    asyncio.run(analyze())
