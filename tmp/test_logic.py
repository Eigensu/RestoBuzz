import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings

async def test_logic():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    
    # Mock current_user
    current_user = {"role": "super_admin"}
    
    if current_user.get("role") == "super_admin":
        cursor = db.restaurants.find({}, {"id": 1, "_id": 0})
        ids = {doc["id"] async for doc in cursor}
        print(f"DEBUG: Found IDs for super_admin: {ids}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(test_logic())
