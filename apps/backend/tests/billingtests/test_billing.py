import asyncio
import os
import sys

# Add the app directory to sys.path so we can import config
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))

from config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def run_diagnostics():
    print(f"Connecting to MongoDB at {settings.mongodb_url}...")
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.split("/")[-1].split("?")[0]
    if not db_name:
        db_name = "dishpatch"
    db = client[db_name]
    
    # 1. Check total count
    total_count = await db.meta_billing_events.count_documents({})
    print(f"\n1. Total records in meta_billing_events: {total_count}")
    
    if total_count == 0:
        print("-> The table is empty! Webhooks are not saving billing events.")
        return

    # 2. Check unique restaurant IDs
    restaurant_ids = await db.meta_billing_events.distinct("restaurant_id")
    print(f"\n2. Unique restaurant_ids in collection: {restaurant_ids}")

    # 3. Check unique categories
    categories = await db.meta_billing_events.distinct("category")
    print(f"\n3. Unique categories: {categories}")

    # 4. Check date range
    oldest = await db.meta_billing_events.find_one({}, sort=[("recorded_at", 1)])
    newest = await db.meta_billing_events.find_one({}, sort=[("recorded_at", -1)])
    if oldest and newest:
        print(f"\n4. Date range: {oldest.get('recorded_at')} to {newest.get('recorded_at')}")
    else:
        print("\n4. Date range: Could not determine (missing recorded_at?)")

    # 5. Check sample records
    print("\n5. Sample of 5 recent records:")
    cursor = db.meta_billing_events.find({}).sort("recorded_at", -1).limit(5)
    async for doc in cursor:
        print({
            "id": str(doc.get("_id")),
            "restaurant_id": doc.get("restaurant_id"),
            "category": doc.get("category"),
            "recorded_at": str(doc.get("recorded_at")),
            "price": doc.get("price"),
            "billable": doc.get("billable"),
        })

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
