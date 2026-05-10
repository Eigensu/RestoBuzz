import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta

import os

async def count_active_inactive():
    uri = os.environ.get("FIELIA_MONGO_URI")
    if not uri:
        raise RuntimeError("FIELIA_MONGO_URI is not set")
        
    client = AsyncIOMotorClient(uri)
    try:
        db = client["test"]
        col = db["cards"]
        
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=30)
        
        # Track latest updated_at per normalized phone
        latest_visits = {}
        
        async for doc in col.find({}, {"phone": 1, "updatedAt": 1}):
            phone = doc.get("phone")
            if not phone:
                continue
                
            clean = "".join(filter(str.isdigit, str(phone)))
            if len(clean) < 10:
                continue
            norm = clean[-10:]
            
            updated_at = doc.get("updatedAt")
            if not isinstance(updated_at, datetime):
                # Ensure we at least track the phone if updatedAt is missing/invalid
                if norm not in latest_visits:
                    latest_visits[norm] = datetime.min.replace(tzinfo=timezone.utc)
                continue

            # Normalize to UTC
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            else:
                updated_at = updated_at.astimezone(timezone.utc)

            # Keep the most recent visit per phone
            if norm not in latest_visits or updated_at > latest_visits[norm]:
                latest_visits[norm] = updated_at
                
        active_count = 0
        inactive_count = 0
        for visit_time in latest_visits.values():
            if visit_time >= cutoff:
                active_count += 1
            else:
                inactive_count += 1
                
        print(f"Total Unique Valid: {len(latest_visits)}")
        print(f"Active (visited < 30d): {active_count}")
        print(f"Inactive: {inactive_count}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(count_active_inactive())
