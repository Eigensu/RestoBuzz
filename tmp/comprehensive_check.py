import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient

# Set PYTHONPATH to include apps/backend
base_path = os.getcwd()
sys.path.append(os.path.join(base_path, "apps", "backend"))

from app.config import settings

async def check():
    print(f"DEBUG: Using MongoDB URL: {settings.mongodb_url}")
    print(f"DEBUG: Using DB Name: {settings.mongodb_db_name}")
    
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    
    # Check users
    user = await db.users.find_one({"email": "admin@example.com"})
    print(f"DEBUG: admin@example.com found: {user is not None}")
    if user:
        print(f"DEBUG: admin@example.com role: {user.get('role')}")
        print(f"DEBUG: admin@example.com _id: {user.get('_id')}")
    
    # Check restaurants
    count = await db.restaurants.count_documents({})
    print(f"DEBUG: Restaurant count: {count}")
    
    if count > 0:
        first = await db.restaurants.find_one()
        print(f"DEBUG: Example restaurant fields: {list(first.keys())}")
        print(f"DEBUG: Example restaurant 'id' field: {first.get('id')}")

    # Check collections
    colls = await db.list_collection_names()
    print(f"DEBUG: Collections: {colls}")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(check())
