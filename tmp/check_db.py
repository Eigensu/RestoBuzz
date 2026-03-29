import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

# Set PYTHONPATH to include apps/backend
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings

async def check():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    
    user = await db.users.find_one({"email": "admin@example.com"})
    print(f"DEBUG: Found user: {user is not None}")
    if user:
        print(f"DEBUG: User role: {user.get('role')}")
    
    count = await db.restaurants.count_documents({})
    print(f"DEBUG: Restaurants count: {count}")
    
    assignments = await db.user_restaurant_roles.count_documents({})
    print(f"DEBUG: Assignments count: {assignments}")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(check())
