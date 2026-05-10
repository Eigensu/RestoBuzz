import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta

import os

def _normalize_fielia_phone(phone: any) -> str | None:
    if not phone:
        return None
    clean = "".join(filter(str.isdigit, str(phone)))
    return clean[-10:] if len(clean) >= 10 else None

def _normalize_visit_time(dt: any) -> datetime:
    if not isinstance(dt, datetime):
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

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
            norm = _normalize_fielia_phone(doc.get("phone"))
            if not norm:
                continue
            
            updated_at = _normalize_visit_time(doc.get("updatedAt"))

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
