import asyncio
import os
from datetime import timezone

from pathlib import Path
import sys

# Standard root-relative import bootstrap
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.config import settings
from motor.motor_asyncio import AsyncIOMotorClient

def _as_utc(ts):
    """Attach UTC to a naive timestamp. None and already-aware values pass through."""
    if ts and ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _first_billable(log):
    """First billable pricing entry in the status history, with its timestamp."""
    for status_item in log.get("status_history", []):
        pricing = status_item.get("meta", {}).get("pricing")
        if pricing and pricing.get("billable"):
            return pricing, status_item.get("timestamp")
    return None, None


def _resolve_pricing_and_ts(log):
    """Extract pricing and timestamp from log status history."""
    pricing, ts = _first_billable(log)
    # Fall back to the log's own timestamps when the billable entry carried none.
    recorded_at = _as_utc(ts) or _as_utc(log.get("updated_at") or log.get("created_at"))
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
