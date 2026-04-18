import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.config import settings

async def check():
    print("Checking restaurant configuration...")
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    
    async for r in db.restaurants.find({}):
        print(f"Name: {r.get('name')}")
        print(f"  ID: {r.get('id')} / {str(r['_id'])}")
        print(f"  Phone IDs: {r.get('wa_phone_ids', 'FIELD MISSING')}")
        print("-" * 20)

    client.close()

if __name__ == "__main__":
    asyncio.run(check())
