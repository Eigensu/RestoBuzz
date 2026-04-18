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
    
    phones = await db.inbound_messages.distinct("from_phone")
    print(f"Sample Inbound Phones: {phones[:10]}")
    
    # Check if any of these match a member
    for p in phones[:10]:
        m = await db.members.find_one({"phone": p})
        print(f"Phone {p} match: {m is not None}")

    client.close()

if __name__ == "__main__":
    asyncio.run(check())
