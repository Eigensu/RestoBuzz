import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient

# Set PYTHONPATH to include apps/backend
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings

async def main():
    print(f"Connecting to {settings.mongodb_url}")
    client = AsyncIOMotorClient(settings.mongodb_url)
    
    # Check databases
    db_names = await client.list_database_names()
    print(f"Databases: {db_names}")
    
    # Check collections in configured DB
    db = client[settings.mongodb_db_name]
    coll_names = await db.list_collection_names()
    print(f"Collections in {settings.mongodb_db_name}: {coll_names}")
    
    # Check count in restaurants
    if "restaurants" in coll_names:
        count = await db.restaurants.count_documents({})
        print(f"Restaurant count: {count}")
    else:
        print("RESTAURANTS COLLECTION NOT FOUND!")

    # Check admin user
    if "users" in coll_names:
        user = await db.users.find_one({"email": "admin@example.com"})
        if user:
            print(f"User admin@example.com found. Role: {user.get('role')}")
        else:
            print("User admin@example.com not found!")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
