import asyncio
import os
from datetime import timezone

from pathlib import Path
import sys

# Standard root-relative import bootstrap
ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "app"))

from config import settings
from motor.motor_asyncio import AsyncIOMotorClient

def _resolve_pricing_and_ts(log):
    """Extract pricing and timestamp from log status history."""
    pricing = None
    recorded_at = None
    for status_item in log.get("status_history", []):
        meta = status_item.get("meta", {})
        p = meta.get("pricing")
        if p and p.get("billable"):
            pricing = p
            ts = status_item.get("timestamp")
            if ts:
                recorded_at = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
            break
    
    if not recorded_at:
        recorded_at = log.get("updated_at") or log.get("created_at")
        if recorded_at and recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)
            
    return pricing, recorded_at


async def backfill_billing_events():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.split("/")[-1].split("?")[0]
    db = client[db_name or "dishpatch"]
    
    print("Starting backfill from message_logs to meta_billing_events...")
    cursor = db.message_logs.find({"status_history.meta.pricing": {"$exists": True}})
    upserted_count = scanned_count = 0
    
    async for log in cursor:
        scanned_count += 1
        wa_id = log.get("wa_message_id")
        if not wa_id:
            continue
            
        pricing, recorded_at = _resolve_pricing_and_ts(log)
        if not pricing or not recorded_at:
            continue
            
        result = await db.meta_billing_events.update_one(
            {"wa_message_id": wa_id},
            {
                "$setOnInsert": {
                    "wa_message_id": wa_id,
                    "restaurant_id": log.get("restaurant_id"),
                    "job_id": log.get("job_id"),
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
            print(f"Scanned {scanned_count}, upserted {upserted_count} billing events so far...")
            
    print(f"Done! Scanned {scanned_count}, upserted {upserted_count} records.")

if __name__ == "__main__":
    asyncio.run(backfill_billing_events())
