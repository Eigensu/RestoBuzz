import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings
from app.services.dormancy_sync_service import dormancy_sync_service
from app.utils.phone import normalize_phone
from pymongo import UpdateOne

async def run():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "restobuzz")
    
    print("--- 1. Normalizing Existing Members ---")
    await dormancy_sync_service.normalize_existing_members(db)
    
    print("--- 2. Normalizing ReserveGo Uploads (Bulk) ---")
    # This might take a while for 230k records, we do it in chunks
    cursor = db.reservego_uploads.find({"normalized_phone": {"$exists": False}})
    ops = []
    total = 0
    async for upload in cursor:
        raw = upload.get("phone") or upload.get("guest_number")
        if raw:
            norm = normalize_phone(raw)
            if norm:
                ops.append(UpdateOne({"_id": upload["_id"]}, {"$set": {"normalized_phone": norm}}))
        
        if len(ops) >= 1000:
            await db.reservego_uploads.bulk_write(ops, ordered=False)
            total += len(ops)
            if total % 10000 == 0:
                print(f"   Progress: Normalized {total} uploads...")
            ops = []
    
    if ops:
        await db.reservego_uploads.bulk_write(ops, ordered=False)
        total += len(ops)
    print(f"Total uploads normalized: {total}")

    print("--- 3. Running Incremental Sync ---")
    # We set checkpoint back to 2000-01-01 to ensure full re-sync for this first run
    await db.sync_metadata.delete_one({"sync_name": dormancy_sync_service.SYNC_NAME})
    await dormancy_sync_service.sync_incremental(db)

    print("\n--- All Stages Complete! ---")

if __name__ == "__main__":
    asyncio.run(run())
