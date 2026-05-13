"""One-time migration: stamp restaurant_id on outbound_messages that lack it.

Strategy:
  1. For each unscoped outbound_message, look up the restaurant by matching
     wa_phone_id against restaurants.wa_phone_ids (the same field the webhook
     router uses for inbound routing).
  2. If a match is found, set restaurant_id on the document.
  3. If no match is found (wa_phone_id missing or unknown), leave the document
     unscoped — it will still appear in thread views via the $exists fallback
     until manually resolved.

Run once after deploying the per-restaurant inbox scoping changes:

    cd apps/backend
    python scripts/backfill_outbound_restaurant_id.py

Safe to re-run: uses $set so already-stamped docs are idempotent.
"""

import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


async def main() -> None:
    from motor.motor_asyncio import AsyncIOMotorClient
    from app.config import settings

    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_default_database(settings.mongodb_db_name)

    # Build a lookup map: wa_phone_id → restaurant_id
    phone_to_restaurant: dict[str, str] = {}
    async for rest in db.restaurants.find(
        {"wa_phone_ids": {"$exists": True, "$not": {"$size": 0}}},
        {"id": 1, "wa_phone_ids": 1},
    ):
        rid = rest.get("id") or str(rest["_id"])
        for pid in rest.get("wa_phone_ids", []):
            if pid:
                phone_to_restaurant[str(pid)] = rid

    print(f"Built phone→restaurant map: {len(phone_to_restaurant)} entries")

    # Find all outbound_messages without restaurant_id
    query = {"restaurant_id": {"$exists": False}}
    total = await db.outbound_messages.count_documents(query)
    print(f"Unscoped outbound_messages to process: {total}")

    stamped = 0
    skipped = 0

    async for doc in db.outbound_messages.find(query, {"_id": 1, "wa_phone_id": 1}):
        wa_phone_id = str(doc.get("wa_phone_id") or "")
        rid = phone_to_restaurant.get(wa_phone_id)

        if rid:
            await db.outbound_messages.update_one(
                {"_id": doc["_id"]},
                {"$set": {"restaurant_id": rid}},
            )
            stamped += 1
        else:
            skipped += 1

    print(f"Done. Stamped: {stamped} | Skipped (no match): {skipped}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
