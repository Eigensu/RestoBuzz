import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
import sys
from datetime import datetime, timedelta, timezone

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.config import settings

async def verify():
    print("Verifying Global Inbox Engagement Report...")
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    
    # Mock parameters
    from_dt = datetime.now(timezone.utc) - timedelta(days=90)
    to_dt = datetime.now(timezone.utc)
    
    # Run the same logic as _build_inbox_data
    pipeline = [
        {"$match": {
            "received_at": {"$gte": from_dt, "$lte": to_dt}
        }},
        {"$sort": {"received_at": -1}},
        {
            "$lookup": {
                "from": "restaurants",
                "localField": "restaurant_id",
                "foreignField": "id",
                "as": "restaurant_info",
            }
        },
        {
            "$addFields": {
                "restaurantName": {
                    "$ifNull": [
                        {"$arrayElemAt": ["$restaurant_info.name", 0]},
                        "Unassigned"
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": "$from_phone",
                "restaurant_name": {"$first": "$restaurantName"},
                "message_count": {"$sum": 1},
            }
        }
    ]
    
    results = await db.inbound_messages.aggregate(pipeline).to_list(None)
    
    total_messages = sum(r["message_count"] for r in results)
    unique_senders = len(results)
    
    print("Report Validation Results:")
    print(f"  Total Messages (Global): {total_messages}")
    print(f"  Unique Senders: {unique_senders}")
    
    if total_messages > 0:
        print(f"  Sample Result: {results[0]}")
    else:
        print("  WARNING: Report still shows 0 messages. Checking date range...")
        # Check date range of records
        sample = await db.inbound_messages.find_one({}, sort=[("received_at", 1)])
        if sample:
            print(f"  Oldest message date: {sample.get('received_at')}")
        sample_new = await db.inbound_messages.find_one({}, sort=[("received_at", -1)])
        if sample_new:
            print(f"  Newest message date: {sample_new.get('received_at')}")

    client.close()

if __name__ == "__main__":
    asyncio.run(verify())
