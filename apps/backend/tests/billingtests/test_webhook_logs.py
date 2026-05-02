import asyncio
import os
import sys

# Add the app directory to sys.path so we can import config
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))

from config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def check_webhook_logs():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.split("/")[-1].split("?")[0]
    if not db_name:
        db_name = "dishpatch"
    db = client[db_name]
    
    # Check if there are any message_logs with pricing info
    print("\n1. Checking message_logs for status_history containing 'pricing'")
    count_with_pricing = await db.message_logs.count_documents({
        "status_history.meta.pricing": {"$exists": True}
    })
    print(f"Message logs with pricing info: {count_with_pricing}")

    if count_with_pricing > 0:
        print("\nSample 'pricing' objects from message_logs:")
        cursor = db.message_logs.find({"status_history.meta.pricing": {"$exists": True}}).limit(3)
        async for doc in cursor:
            for status_obj in doc.get("status_history", []):
                meta = status_obj.get("meta", {})
                pricing = meta.get("pricing")
                if pricing:
                    print(f"Message ID: {doc.get('wa_message_id')} -> pricing: {pricing}")
    else:
        print("\nNo 'pricing' found in status_history.meta!")
        
        # Let's check raw payload from inbound_messages
        print("\nChecking inbound_messages for pricing...")
        count_inbound = await db.inbound_messages.count_documents({})
        print(f"Total inbound_messages: {count_inbound}")
        
    print("\n2. Let's check a random status_history object")
    random_log = await db.message_logs.find_one({"status_history": {"$exists": True, "$ne": []}})
    if random_log:
        print(f"Sample meta object inside status_history:\n{random_log['status_history'][0].get('meta', {})}")

if __name__ == "__main__":
    asyncio.run(check_webhook_logs())
