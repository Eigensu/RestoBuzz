import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta

import os

async def count_active_inactive():
    uri = os.environ.get("FIELIA_MONGO_URI")
    if not uri:
        raise RuntimeError("FIELIA_MONGO_URI is not set")
    client = AsyncIOMotorClient(uri)
    db = client["test"]
    col = db["cards"]
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=30)
    
    processed = set()
    active_count = 0
    inactive_count = 0
    
    async for doc in col.find({}, {"phone": 1, "updatedAt": 1}):
        phone = doc.get("phone")
        if not phone: continue
        clean = "".join(filter(str.isdigit, str(phone)))
        if len(clean) < 10: continue
        norm = clean[-10:]
        
        if norm in processed: continue
        processed.add(norm)
        
        updated_at = doc.get("updatedAt")
        if isinstance(updated_at, datetime):
            updated_at = updated_at.replace(tzinfo=None)
            if updated_at >= cutoff:
                active_count += 1
            else:
                inactive_count += 1
        else:
            inactive_count += 1
            
    print(f"Total Unique Valid: {len(processed)}")
    print(f"Active (visited < 30d): {active_count}")
    print(f"Inactive: {inactive_count}")
    client.close()

if __name__ == "__main__":
    asyncio.run(count_active_inactive())
