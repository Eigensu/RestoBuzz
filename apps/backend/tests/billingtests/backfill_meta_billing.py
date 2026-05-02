import asyncio
import os
import sys
from datetime import timezone

# Add the app directory to sys.path so we can import config
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))

from config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def backfill_billing_events():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.split("/")[-1].split("?")[0]
    if not db_name:
        db_name = "dishpatch"
    db = client[db_name]
    
    print("Starting backfill from message_logs to meta_billing_events...")
    
    # We only care about message_logs that have pricing
    cursor = db.message_logs.find({"status_history.meta.pricing": {"$exists": True}})
    
    upserted_count = 0
    scanned_count = 0
    
    async for log in cursor:
        scanned_count += 1
        wa_id = log.get("wa_message_id")
        restaurant_id = log.get("restaurant_id")
        job_id = log.get("job_id")
        
        if not wa_id:
            continue
            
        # Find the pricing object from the status history
        # (usually sent with 'sent' or 'delivered' status)
        pricing = None
        recorded_at = None
        for status_item in log.get("status_history", []):
            meta = status_item.get("meta", {})
            p = meta.get("pricing")
            if p and p.get("billable"):
                pricing = p
                # ensure recorded_at is timezone-aware if possible, 
                # but fallback to whatever is there.
                ts = status_item.get("timestamp")
                if ts:
                    if ts.tzinfo is None:
                        recorded_at = ts.replace(tzinfo=timezone.utc)
                    else:
                        recorded_at = ts
                break
                
        if not pricing:
            continue
            
        if not recorded_at:
            # Fallback to updated_at or created_at
            recorded_at = log.get("updated_at") or log.get("created_at")
            if recorded_at and recorded_at.tzinfo is None:
                recorded_at = recorded_at.replace(tzinfo=timezone.utc)
                
        # Insert into meta_billing_events
        result = await db.meta_billing_events.update_one(
            {"wa_message_id": wa_id},
            {
                "$setOnInsert": {
                    "wa_message_id": wa_id,
                    "restaurant_id": restaurant_id,
                    "job_id": job_id,
                    "category": (pricing.get("category") or "").lower(),
                    "pricing_model": pricing.get("pricing_model") or "PMP",
                    "recorded_at": recorded_at,
                }
            },
            upsert=True,
        )
        
        if result.upserted_id:
            upserted_count += 1
            
        if scanned_count % 1000 == 0:
            print(f"Scanned {scanned_count} logs, upserted {upserted_count} billing events so far...")
            
    print(f"Done! Scanned {scanned_count} logs. Upserted {upserted_count} new billing events.")

if __name__ == "__main__":
    asyncio.run(backfill_billing_events())
