import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings
from app.services.dormancy_sync_service import dormancy_sync_service
from app.services.member_match_service import member_match_service
from app.services.phone_normalizer import phone_normalizer

async def migrate():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "restobuzz")
    
    restaurants = await db.restaurants.find().to_list(100)
    
    for rest in restaurants:
        rid = rest.get("id") or str(rest["_id"])
        print(f"Migrating tiers for {rest.get('name')} ({rid})...")
        
        m_db, m_coll, m_filter = await member_match_service.get_member_db_context(rid)
        
        cursor = m_db[m_coll].find(m_filter)
        ops = []
        
        async for member in cursor:
            raw_phone = member.get("phone")
            last_visit = member.get("last_visit")
            
            update_fields = {}
            
            # 1. Ensure normalized phone
            if not member.get("normalized_phone") and raw_phone:
                norm = phone_normalizer.normalize(raw_phone)
                if norm:
                    update_fields["normalized_phone"] = norm
            
            # 2. Calculate Tier
            tier = dormancy_sync_service.calculate_tier(last_visit)
            update_fields["dormancy_tier"] = tier
            
            if update_fields:
                ops.append(UpdateOne(
                    {"_id": member["_id"]},
                    {"$set": update_fields}
                ))
            
            if len(ops) >= 500:
                await m_db[m_coll].bulk_write(ops, ordered=False)
                ops = []
                
        if ops:
            await m_db[m_coll].bulk_write(ops, ordered=False)
            
    print("\n--- Migration Complete ---")

if __name__ == "__main__":
    asyncio.run(migrate())
