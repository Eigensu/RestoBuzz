import asyncio
import os
import sys

# Fix path resolution to be absolute relative to this script
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_root = os.path.dirname(current_dir) # apps/backend
sys.path.append(backend_root)

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

async def get_message_summary():
    client = AsyncIOMotorClient(settings.mongodb_url)
    try:
        db = client.get_database(settings.mongodb_db_name or "restobuzz")

        print(f"{'Rest ID':<10} | {'Name':<20} | {'Inbound':<10} | {'Outbound':<10} | {'Unread':<10}")
        print("-" * 70)

        restaurants = await db.restaurants.find().to_list(100)
        for rest in restaurants:
            rid = str(rest.get("id") or rest.get("_id"))
            name = rest.get("name", "Unknown")

            inbound_count = await db.inbound_messages.count_documents({"restaurant_id": rid})
            unread_count = await db.inbound_messages.count_documents({"restaurant_id": rid, "is_read": False})
            outbound_count = await db.message_logs.count_documents({"restaurant_id": rid})

            print(f"{rid:<10} | {name[:20]:<20} | {inbound_count:<10} | {outbound_count:<10} | {unread_count:<10}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(get_message_summary())
