import asyncio
import os
import sys

# Add the app directory to sys.path so we can import config
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))

from config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def get_total_messages_per_restaurant():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.split("/")[-1].split("?")[0]
    if not db_name:
        db_name = "dishpatch"
    db = client[db_name]
    
    print("Fetching total billable messages per restaurant...\n")
    
    pipeline = [
        {"$group": {"_id": "$restaurant_id", "total_messages": {"$sum": 1}}},
        {"$sort": {"total_messages": -1}}
    ]
    
    cursor = db.meta_billing_events.aggregate(pipeline)
    
    # Fetch restaurant names
    restaurants = {}
    async for r in db.restaurants.find({}, {"id": 1, "name": 1, "_id": 1}):
        # Store by string ID (for custom 'id' field or stringified '_id')
        if r.get("id"):
            restaurants[str(r["id"])] = r.get("name", "Unnamed")
        restaurants[str(r["_id"])] = r.get("name", "Unnamed")
    
    print(f"{'Restaurant Name':<30} | {'Restaurant ID':<15} | {'Total Billable Messages':<25}")
    print("-" * 75)
    
    async for doc in cursor:
        rest_id = doc["_id"]
        rest_name = restaurants.get(str(rest_id), "Unknown/Deleted") if rest_id else "Unknown"
        rest_id_str = str(rest_id) if rest_id else "None"
        print(f"{rest_name:<30} | {rest_id_str:<15} | {doc['total_messages']:<25}")

if __name__ == "__main__":
    asyncio.run(get_total_messages_per_restaurant())
