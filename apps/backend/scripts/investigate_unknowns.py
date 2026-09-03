import asyncio
import os

from pathlib import Path
import sys

# Standard root-relative import bootstrap
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def check_job_exists(db, job_id_str):
    """Check if a job exists in campaign_jobs and print its status."""
    from bson.objectid import ObjectId
    try:
        job_oid = ObjectId(job_id_str)
        job = await db.campaign_jobs.find_one({"_id": job_oid})
        if job:
            print(f"Job {job_id_str} EXISTS in campaign_jobs and belongs to restaurant_id: {job.get('restaurant_id')}")
            return True
    except Exception:
        pass

    # maybe it's string
    job = await db.campaign_jobs.find_one({"_id": job_id_str})
    if job:
        print(f"Job {job_id_str} EXISTS in campaign_jobs and belongs to restaurant_id: {job.get('restaurant_id')}")
        return True
    
    print(f"Job {job_id_str} NOT FOUND in campaign_jobs")
    return False


async def investigate_unknowns():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.split("/")[-1].split("?")[0]
    db = client[db_name or "dishpatch"]
    
    print("Investigating 11366 'Unknown' billing events...")
    
    # Check how many have a job_id
    with_job = await db.meta_billing_events.count_documents({"restaurant_id": None, "job_id": {"$ne": None}})
    without_job = await db.meta_billing_events.count_documents({"restaurant_id": None, "job_id": None})
    
    print(f"Unknowns WITH job_id: {with_job}")
    print(f"Unknowns WITHOUT job_id: {without_job}")
    
    if with_job > 0:
        print("\nLet's check if the jobs exist in campaign_jobs")
        pipeline = [
            {"$match": {"restaurant_id": None, "job_id": {"$ne": None}}},
            {"$group": {"_id": "$job_id", "count": {"$sum": 1}}},
            {"$limit": 5}
        ]
        async for doc in db.meta_billing_events.aggregate(pipeline):
            await check_job_exists(db, str(doc["_id"]))
                    
    # Also check how many message_logs have restaurant_id vs job_id
    total_ml = await db.message_logs.count_documents({})
    ml_with_rest = await db.message_logs.count_documents({"restaurant_id": {"$ne": None}})
    ml_with_job = await db.message_logs.count_documents({"job_id": {"$ne": None}})
    
    print(f"\nTotal message_logs: {total_ml}")
    print(f"Message logs with restaurant_id: {ml_with_rest}")
    print(f"Message logs with job_id: {ml_with_job}")

if __name__ == "__main__":
    asyncio.run(investigate_unknowns())
