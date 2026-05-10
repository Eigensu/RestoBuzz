import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings
from app.utils.phone import normalize_phone

async def _normalize_members(db, rid):
    m_cursor = db.members.find({"restaurant_id": rid, "normalized_phone": {"$exists": False}})
    m_ops = []
    async for m in m_cursor:
        norm = normalize_phone(m.get("phone"))
        if norm:
            m_ops.append(UpdateOne({"_id": m["_id"]}, {"$set": {"normalized_phone": norm}}))
    if m_ops:
        print(f"Normalizing {len(m_ops)} members...")
        await db.members.bulk_write(m_ops)

async def _normalize_uploads(db, rid):
    u_cursor = db.reservego_uploads.find({"restaurant_id": rid, "normalized_phone": {"$exists": False}})
    u_ops = []
    async for u in u_cursor:
        norm = normalize_phone(u.get("phone") or u.get("guest_number"))
        if norm:
            u_ops.append(UpdateOne({"_id": u["_id"]}, {"$set": {"normalized_phone": norm}}))
    if u_ops:
        print(f"Normalizing {len(u_ops)} uploads...")
        for i in range(0, len(u_ops), 500):
            await db.reservego_uploads.bulk_write(u_ops[i:i+500])
            print(f"   Processed {i+len(u_ops[i:i+500])}/{len(u_ops)}...")

async def _sync_visits(db, rid):
    print("Syncing visits...")
    visits = db.reservego_uploads.find({"restaurant_id": rid, "last_visited_date": {"$ne": None}})
    v_ops = []
    async for v in visits:
        norm = v.get("normalized_phone")
        visit_date = v.get("last_visited_date")
        if norm and visit_date:
            v_ops.append(UpdateOne(
                {"restaurant_id": rid, "normalized_phone": norm},
                {"$max": {"last_visit": visit_date}}
            ))
    if v_ops:
        print(f"Updating {len(v_ops)} member visit dates...")
        for i in range(0, len(v_ops), 500):
            await db.members.bulk_write(v_ops[i:i+500])
            print(f"   Processed {i+len(v_ops[i:i+500])}/{len(v_ops)}...")

async def mini_sync():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "restobuzz")
    
    rid = "r6"
    print(f"--- Running MINI SYNC for {rid} ---")
    
    await _normalize_members(db, rid)
    await _normalize_uploads(db, rid)
    await _sync_visits(db, rid)

    print("\n--- Mini Sync Complete ---")

if __name__ == "__main__":
    asyncio.run(mini_sync())
