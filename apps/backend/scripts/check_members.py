import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.config import settings

async def check():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    
    count = await db.members.count_documents({})
    print(f"Total members: {count}")
    
    async for m in db.members.find({}).limit(5):
        print(f"Member Phone: {m.get('phone')}")

    client.close()

if __name__ == "__main__":
    asyncio.run(check())
