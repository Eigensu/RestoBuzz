import asyncio
import os
from datetime import datetime, timezone, timedelta

def normalize(p):
    if not p: return ""
    return "".join(filter(str.isdigit, str(p)))

async def backfill():
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ.get("MONGODB_URL", "mongodb://localhost:27017/restobuzz")
    client = AsyncIOMotorClient(mongo_url)
    db_name = "restobuzz"
    if "/" in mongo_url.split("mongodb.net")[-1]:
         parsed = mongo_url.split("mongodb.net")[-1].split("?")[0].strip("/")
         if parsed:
             db_name = parsed
    
    db = client.get_database(db_name)
    
    print(f"Starting Robust Normalized Backfill on DB: {db_name}...")
    
    # 1. Reset all replies_count in campaign_jobs to 0 before recount for accuracy
    # Optional: Only if we want a fresh start. Given the issues, it's safer.
    print("Resetting replies_count for all jobs...")
    await db.campaign_jobs.update_many({}, {"$set": {"replies_count": 0}})
    await db.message_logs.update_many({}, {"$set": {"replied": False}})

    # 2. Get all message logs to build a lookup map
    print("Building recipient map...")
    logs_cursor = db.message_logs.find()
    recipient_map = {} # normalized_phone -> list of logs (sorted by time)
    async for l in logs_cursor:
        norm = normalize(l.get("recipient_phone"))
        if not norm: continue
        if norm not in recipient_map:
            recipient_map[norm] = []
        recipient_map[norm].append(l)
    
    # Sort each list by created_at
    for p in recipient_map:
        recipient_map[p].sort(key=lambda x: x.get("created_at"))

    # 3. Process all inbound messages
    print("Processing inbound messages...")
    inbound_cursor = db.inbound_messages.find()
    
    updated_messages = 0
    updated_campaigns = 0

    async for msg in inbound_cursor:
        from_phone = normalize(msg.get("from_phone"))
        received_at = msg.get("received_at")
        if not from_phone or not received_at: continue
        
        # Ensure received_at is timezone-aware
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)

        # Look for the last message sent to this user BEFORE they replied
        if from_phone in recipient_map:
            candidates = [l for l in recipient_map[from_phone] if l.get("created_at").replace(tzinfo=timezone.utc) < received_at]
            if candidates:
                # Latest candidate
                best_match = candidates[-1]
                
                # Check if already marked as replied for this specific log to avoid double counting same user response multi-inc
                # Actually, if we reset everything, we just need to ensure we only mark a log as replied once.
                
                # For this backfill, we mark the log as replied and increment the job.
                # However, if a user replies 3 times to 1 campaign, we should only count as 1 unique reply per Meta?
                # Meta insights say 202 "Unique replies". 
                # Our logic increments replies_count for every inbound message? 
                # Let's change it to 1 reply per log entry.
                
                if not best_match.get("temp_replied"):
                    best_match["temp_replied"] = True
                    
                    # Update DB
                    await db.message_logs.update_one({"_id": best_match["_id"]}, {"$set": {"replied": True}})
                    await db.campaign_jobs.update_one({"_id": best_match["job_id"]}, {"$inc": {"replies_count": 1}})
                    
                    updated_messages += 1
                    updated_campaigns += 1

    print(f"Backfill complete! Captured {updated_messages} unique campaign replies.")
    client.close()

if __name__ == "__main__":
    asyncio.run(backfill())
