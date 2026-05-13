import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

async def fix_id():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    
    # Update phone_id for Soraia (r1)
    result = await db.restaurants.update_one(
        {"id": "r1"},
        {"$set": {"wa_phones.0.phone_id": "1069035316301067"}}
    )
    print(f"Matched: {result.matched_count}, Modified: {result.modified_count}")

if __name__ == "__main__":
    asyncio.run(fix_id())
