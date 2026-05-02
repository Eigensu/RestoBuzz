import asyncio
import os
import sys

# Add the app directory to sys.path so we can import config
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))

from config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def investigate_billing():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.split("/")[-1].split("?")[0]
    if not db_name:
        db_name = "dishpatch"
    db = client[db_name]
    
    print("1. Checking total message_logs per restaurant")
    pipeline_logs = [
        {"$group": {"_id": "$restaurant_id", "total": {"$sum": 1}}}
    ]
    async for doc in db.message_logs.aggregate(pipeline_logs):
        print(f"Restaurant {doc['_id']}: {doc['total']} total message logs")

    print("\n2. Checking total sent/delivered from campaign_jobs per restaurant")
    pipeline_campaigns = [
        {"$group": {
            "_id": "$restaurant_id", 
            "total_sent": {"$sum": "$sent_count"},
            "total_delivered": {"$sum": "$delivered_count"}
        }}
    ]
    async for doc in db.campaign_jobs.aggregate(pipeline_campaigns):
        print(f"Restaurant {doc['_id']}: {doc['total_sent']} sent, {doc['total_delivered']} delivered in campaigns")
        
    print("\n3. Sample of pricing objects from a single number to see if multiple messages get billable=True")
    cursor = db.message_logs.find({"status_history.meta.pricing": {"$exists": True}}).limit(10)
    async for doc in cursor:
        pricing_info = None
        for s in doc.get("status_history", []):
            if s.get("meta", {}).get("pricing"):
                pricing_info = s["meta"]["pricing"]
                break
        print(f"Message {doc['wa_message_id']} to {doc.get('recipient_phone')}: Pricing {pricing_info}")

if __name__ == "__main__":
    asyncio.run(investigate_billing())
