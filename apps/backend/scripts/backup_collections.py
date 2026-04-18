import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json
from datetime import datetime
import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.config import settings

async def backup():
    print("Starting collection backup...")
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    
    collections = ["inbound_messages", "restaurants"]
    backup_dir = "backups"
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for coll_name in collections:
        print(f"Backing up {coll_name}...")
        docs = await db[coll_name].find({}).to_list(None)
        
        # Convert ObjectId and datetime to string for JSON serialization
        def serialize(obj):
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            if hasattr(obj, "__str__"):
                return str(obj)
            return obj

        filepath = os.path.join(backup_dir, f"{coll_name}_{timestamp}.json")
        
        def _write(p_filepath, p_docs, p_serialize):
            with open(p_filepath, "w", encoding="utf-8") as f:
                json.dump(p_docs, f, default=p_serialize, indent=2)

        await asyncio.to_thread(_write, filepath, docs, serialize)
        print(f"  Saved {len(docs)} documents to {filepath}")

    client.close()
    print("Backup complete.")

if __name__ == "__main__":
    asyncio.run(backup())
