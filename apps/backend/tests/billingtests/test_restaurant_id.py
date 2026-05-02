import asyncio
import os
import sys

# Add the app directory to sys.path so we can import config
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))

from config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def check_restaurant_id():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.split("/")[-1].split("?")[0]
    if not db_name:
        db_name = "dishpatch"
    db = client[db_name]
    
    # Let's find one message log with a valid restaurant_id
    doc_with_rest = await db.message_logs.find_one({"restaurant_id": {"$exists": True, "$ne": None}})
    if doc_with_rest:
        print("Found a message_log with restaurant_id:", doc_with_rest.get("restaurant_id"))
    else:
        print("NO message_logs have restaurant_id!")
        
    doc_with_job = await db.message_logs.find_one({"job_id": {"$exists": True, "$ne": None}})
    if doc_with_job:
        job_id = doc_with_job.get("job_id")
        print("Found a message_log with job_id:", job_id)
        # Let's check if the campaign_job has a restaurant_id
        job = await db.campaign_jobs.find_one({"_id": job_id})
        if job:
            print("Campaign job has restaurant_id:", job.get("restaurant_id"))
        else:
            print("Campaign job not found!")

if __name__ == "__main__":
    asyncio.run(check_restaurant_id())
