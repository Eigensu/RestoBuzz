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
    doc = await db.inbound_messages.find_one({})
    print(f"Sample Inbound Message:\n{doc}")
    client.close()

if __name__ == "__main__":
    asyncio.run(check())
