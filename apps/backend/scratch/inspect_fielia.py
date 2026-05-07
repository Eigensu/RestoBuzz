import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings

async def check():
    uri = settings.fielia_mongo_uri
    client = AsyncIOMotorClient(uri)
    db = client.get_database("test")
    
    print(f"--- Inspecting Fielia [test] Database ---")
    
    # 1. Check cards (Members)
    m_count = await db.cards.count_documents({})
    print(f"Cards count: {m_count}")
    if m_count > 0:
        sample = await db.cards.find().limit(5).to_list(5)
        for s in sample:
            print(f"Card: {s.get('_id')} | phone={s.get('phone')} | last_visit={s.get('last_visit')}")

    # 2. Check if there are ANY other visit-like collections
    colls = await db.list_collection_names()
    print(f"\nCollections in [test]: {colls}")
    
    for c in colls:
        # Check if this collection has 'phone' and some date
        sample = await db[c].find_one({"phone": {"$exists": True}})
        if sample:
            print(f"Collection [{c}] has 'phone' field. Sample: {sample.get('phone')}")

if __name__ == "__main__":
    asyncio.run(check())
