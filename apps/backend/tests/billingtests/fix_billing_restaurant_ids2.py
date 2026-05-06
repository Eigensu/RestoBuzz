import asyncio
import os
from bson.objectid import ObjectId

from pathlib import Path
import sys

# Standard root-relative import bootstrap
ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "app"))

from config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def resolve_restaurant_id(db, job_id, job_cache):
    """Resolve restaurant_id for a given job_id with caching."""
    if job_id in job_cache:
        return job_cache[job_id]

    job = None
    if isinstance(job_id, str) and ObjectId.is_valid(job_id):
        try:
            job = await db.campaign_jobs.find_one({"_id": ObjectId(job_id)})
        except Exception:
            pass
    
    if not job:
        job = await db.campaign_jobs.find_one({"_id": job_id})
        
    if job and job.get("restaurant_id"):
        rest_id = job.get("restaurant_id")
        job_cache[job_id] = rest_id
        return rest_id
    return None


async def fix_restaurant_ids_correctly():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.split("/")[-1].split("?")[0]
    db = client[db_name or "dishpatch"]
    
    print("Fixing restaurant_id in meta_billing_events (with ObjectId)...")
    cursor = db.meta_billing_events.find({"restaurant_id": None})
    updated = scanned = 0
    job_cache = {}
    
    async for doc in cursor:
        scanned += 1
        job_id = doc.get("job_id")
        if not job_id:
            continue
            
        rest_id = await resolve_restaurant_id(db, job_id, job_cache)
        if rest_id:
            await db.meta_billing_events.update_one(
                {"_id": doc["_id"]},
                {"$set": {"restaurant_id": rest_id}}
            )
            updated += 1
            
        if scanned % 500 == 0:
            print(f"Scanned {scanned}, updated {updated}...")
            
    print(f"Done! Scanned {scanned}, updated {updated} records.")

if __name__ == "__main__":
    asyncio.run(fix_restaurant_ids_correctly())
