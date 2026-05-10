import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings

async def fix():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "restobuzz")
    
    phone_id = "936956752843517"
    restaurant_id = "r2" # Assuming Fielia
    
    print(f"Mapping {phone_id} to {restaurant_id}...")
    
    # Update restaurant - using ID field which is 'r2'
    await db.restaurants.update_one(
        {"id": restaurant_id},
        {"$set": {"wa_phone_ids": [phone_id]}}
    )
    
    print("Backfilling quarantined messages...")
    result = await db.inbound_messages.update_many(
        {"wa_phone_id": phone_id, "restaurant_id": None},
        {"$set": {"restaurant_id": restaurant_id}}
    )
    print(f"Updated {result.modified_count} messages.")
    
    # Also verify there are no other unread messages for other restaurants
    unreads = await db.inbound_messages.count_documents({"restaurant_id": restaurant_id, "is_read": False})
    print(f"Total unread for {restaurant_id} now: {unreads}")

if __name__ == "__main__":
    asyncio.run(fix())
