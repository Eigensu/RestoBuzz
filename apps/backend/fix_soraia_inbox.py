"""
Fix Soraia (r1) inbox visibility.

Root cause:
  The webhook task resolves a restaurant by querying:
    db.restaurants.find_one({"wa_phone_ids": phone_number_id})

  r1's document has wa_phones.0.phone_id = "1069035316301067" (set by fix_soraia_id.py)
  but wa_phone_ids (the flat array used for routing) was never populated.

  Result: every inbound message on Soraia's number is stored with restaurant_id=None,
  so the inbox query (which filters restaurant_id="r1") returns nothing.

This script:
  1. Stamps wa_phone_ids on r1 so future messages route correctly.
  2. Backfills all historical inbound_messages with restaurant_id=None for that phone_id.
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

SORAIA_PHONE_ID = "1069035316301067"
SORAIA_RESTAURANT_ID = "r1"


async def fix():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]

    # ── Step 1: Ensure wa_phone_ids is set on r1 ─────────────────────────────
    # We only add to wa_phone_ids — we don't touch wa_phones (already correct).
    result = await db.restaurants.update_one(
        {"id": SORAIA_RESTAURANT_ID},
        {"$addToSet": {"wa_phone_ids": SORAIA_PHONE_ID}},
    )
    print(
        f"[1] Restaurant r1 wa_phone_ids update — "
        f"matched: {result.matched_count}, modified: {result.modified_count}"
    )

    # Verify
    doc = await db.restaurants.find_one(
        {"id": SORAIA_RESTAURANT_ID}, {"wa_phone_ids": 1, "wa_phones": 1}
    )
    print(f"    wa_phone_ids now: {doc.get('wa_phone_ids')}")
    print(f"    wa_phones now:    {doc.get('wa_phones')}")

    # ── Step 2: Backfill inbound_messages with restaurant_id=None ────────────
    inbound_result = await db.inbound_messages.update_many(
        {"wa_phone_id": SORAIA_PHONE_ID, "restaurant_id": None},
        {"$set": {"restaurant_id": SORAIA_RESTAURANT_ID}},
    )
    print(
        f"\n[2] Backfilled inbound_messages — "
        f"matched: {inbound_result.matched_count}, modified: {inbound_result.modified_count}"
    )

    # ── Step 3: Backfill outbound_messages with restaurant_id=None ───────────
    # outbound_messages don't have wa_phone_id, but they do have restaurant_id.
    # The inbox thread query already has a fallback for unscoped outbound rows,
    # so this is optional — but clean it up anyway if any exist.
    outbound_result = await db.outbound_messages.update_many(
        {"restaurant_id": None},
        {"$set": {"restaurant_id": SORAIA_RESTAURANT_ID}},
    )
    print(
        f"[3] Backfilled outbound_messages (unscoped) — "
        f"matched: {outbound_result.matched_count}, modified: {outbound_result.modified_count}"
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    total_inbound = await db.inbound_messages.count_documents(
        {"restaurant_id": SORAIA_RESTAURANT_ID}
    )
    print(f"\nTotal inbound messages now visible for r1: {total_inbound}")

    client.close()


if __name__ == "__main__":
    asyncio.run(fix())
