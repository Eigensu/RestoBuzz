import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import os
import sys
import argparse

# Add the app directory to sys.path if needed
sys.path.append(os.getcwd())

from app.config import settings

async def _backfill_via_phone_ids(db, restaurants, dry_run, stats):
    for rest in restaurants:
        rid = rest.get("id") or str(rest["_id"])
        phone_ids = rest.get("wa_phone_ids", [])
        print(f"Processing {rest.get('name')} (ID: {rid}) with Phone IDs: {phone_ids}")

        # Inbound
        inbound_q = {"wa_phone_id": {"$in": phone_ids}, "restaurant_id": None}
        inbound_count = await db.inbound_messages.count_documents(inbound_q)
        stats["inbound"]["scanned"] += inbound_count
        if not dry_run and inbound_count > 0:
            res_in = await db.inbound_messages.update_many(inbound_q, {"$set": {"restaurant_id": rid}})
            stats["inbound"]["matched"] += res_in.modified_count
            stats["inbound"]["updated"] += res_in.modified_count
        else:
            stats["inbound"]["matched"] += inbound_count

        # Outbound
        outbound_q = {"restaurant_id": None, "to_phone": {"$exists": True}}
        outbound_count = await db.outbound_messages.count_documents(outbound_q)
        if not dry_run and outbound_count > 0:
            res_out = await db.outbound_messages.update_many(outbound_q, {"$set": {"restaurant_id": rid}})
            stats["outbound"]["matched"] += res_out.modified_count
            stats["outbound"]["updated"] += res_out.modified_count


async def _backfill_via_members(db, orphaned_phones, dry_run, stats):
    for phone in orphaned_phones:
        member = await db.members.find_one({"phone": phone})
        if member:
            m_rid = member.get("restaurant_id")
            if m_rid:
                q = {"from_phone": phone, "restaurant_id": None}
                count = await db.inbound_messages.count_documents(q)
                stats["inbound"]["scanned"] += count
                if not dry_run:
                    res = await db.inbound_messages.update_many(q, {"$set": {"restaurant_id": m_rid}})
                    stats["inbound"]["matched"] += res.modified_count
                    stats["inbound"]["updated"] += res.modified_count
                else:
                    stats["inbound"]["matched"] += count


async def backfill(dry_run: bool = False):
    print(f"Starting background tenant attribution (DRY_RUN={dry_run})...")
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]

    stats = {
        "inbound": {"scanned": 0, "matched": 0, "updated": 0},
        "outbound": {"scanned": 0, "matched": 0, "updated": 0}
    }

    # 1. Map WhatsApp Phone IDs
    restaurants = await db.restaurants.find({"wa_phone_ids": {"$exists": True, "$not": {"$size": 0}}}).to_list(100)
    await _backfill_via_phone_ids(db, restaurants, dry_run, stats)

    # 2. Map via Member Lookup
    orphaned_phones = await db.inbound_messages.distinct("from_phone", {"restaurant_id": None})
    print(f"Found {len(orphaned_phones)} unique phones. Resolving via members...")
    await _backfill_via_members(db, orphaned_phones, dry_run, stats)

    print("\n--- Summary ---")
    print(f"Inbound: Scanned={stats['inbound']['scanned']}, Matched={stats['inbound']['matched']}, Updated={stats['inbound']['updated']}")
    print(f"Outbound: Matched={stats['outbound']['matched']}, Updated={stats['outbound']['updated']}")
    print("\nBackfill complete.")
    client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill missing restaurant_id in messages.")
    parser.add_argument("--dry-run", action="store_true", help="Count matches without updating the database.")
    args = parser.parse_args()
    
    asyncio.run(backfill(dry_run=args.dry_run))

