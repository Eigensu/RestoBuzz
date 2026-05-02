import asyncio
import os
import sys
from bson.objectid import ObjectId

# Add the app directory to sys.path so we can import config
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))

from config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def fix_restaurant_ids_correctly():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.split("/")[-1].split("?")[0]
    if not db_name:
        db_name = "dishpatch"
    db = client[db_name]
    
    print("Fixing restaurant_id in meta_billing_events (with ObjectId)...")
    
    cursor = db.meta_billing_events.find({"restaurant_id": None})
    updated = 0
    scanned = 0
    
    job_cache = {}
    
    async for doc in cursor:
        scanned += 1
        job_id = doc.get("job_id")
        if not job_id:
            continue
            
        rest_id = job_cache.get(job_id)
        if not rest_id:
            # TRY STRING AND OBJECTID
            job = None
            if isinstance(job_id, str):
                try:
                    job = await db.campaign_jobs.find_one({"_id": ObjectId(job_id)})
                except:
                    pass
            
            if not job:
                job = await db.campaign_jobs.find_one({"_id": job_id})
                
            if job and job.get("restaurant_id"):
                rest_id = job.get("restaurant_id")
                job_cache[job_id] = rest_id
                
        if rest_id:
            await db.meta_billing_events.update_one(
                {"_id": doc["_id"]},
                {"$set": {"restaurant_id": rest_id}}
            )
            updated += 1
            
        if scanned % 500 == 0:
            print(f"Scanned {scanned}, updated {updated}...")
            
    print(f"Done! Scanned {scanned}, updated {updated} records with correct restaurant_id.")

if __name__ == "__main__":
    asyncio.run(fix_restaurant_ids_correctly())
