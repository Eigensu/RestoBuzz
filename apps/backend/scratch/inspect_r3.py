import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings

async def check():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "restobuzz")
    
    rid = "r3"
    print(f"--- Inspecting r3 Uploads ({rid}) ---")
    
    total = await db.reservego_uploads.count_documents({"restaurant_id": rid})
    with_phone = await db.reservego_uploads.count_documents({"restaurant_id": rid, "phone": {"$ne": None}})
    with_guest_num = await db.reservego_uploads.count_documents({"restaurant_id": rid, "guest_number": {"$ne": None}})
    
    print(f"Total uploads: {total}")
    print(f"Records with 'phone': {with_phone}")
    print(f"Records with 'guest_number': {with_guest_num}")
    
    sample = await db.reservego_uploads.find({"restaurant_id": rid}).limit(5).to_list(5)
    for s in sample:
        print(f"Record: {s.get('_id')} | phone={s.get('phone')} | guest_number={s.get('guest_number')}")

if __name__ == "__main__":
    asyncio.run(check())
