import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.config import settings

async def check_baseline():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    
    total_inbound = await db.inbound_messages.count_documents({})
    missing_tenant = await db.inbound_messages.count_documents({"restaurant_id": None})
    
    print(f"Total inbound messages: {total_inbound}")
    print(f"Messages missing restaurant_id: {missing_tenant}")
    
    # Distribution before
    pipeline = [{"$group": {"_id": "$restaurant_id", "count": {"$sum": 1}}}]
    async for res in db.inbound_messages.aggregate(pipeline):
        print(f"Tenant {res['_id']}: {res['count']}")

    client.close()

if __name__ == "__main__":
    asyncio.run(check_baseline())
