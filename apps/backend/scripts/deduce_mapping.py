import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.config import settings

async def deduce_mapping():
    print("Attempting to deduce Phone ID mapping from member data...")
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    
    # 1. Get unique (wa_phone_id, from_phone) pairs
    pipeline = [
        {"$match": {"wa_phone_id": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": {"wa_phone_id": "$wa_phone_id", "from_phone": "$from_phone"}
        }}
    ]
    
    mapping = {} # wa_phone_id -> set of restaurant_ids
    
    async for entry in db.inbound_messages.aggregate(pipeline):
        wa_id = entry["_id"]["wa_phone_id"]
        from_phone = entry["_id"]["from_phone"]
        
        # Check if this customer is a member of any restaurant
        member = await db.members.find_one({"phone": from_phone})
        if member:
            rid = member.get("restaurant_id")
            if rid:
                if wa_id not in mapping:
                    mapping[wa_id] = set()
                mapping[wa_id].add(rid)
    
    print("\nDeduction Results:")
    for wa_id, rids in mapping.items():
        print(f"Phone ID {wa_id} messaged by members of: {rids}")

    client.close()

if __name__ == "__main__":
    asyncio.run(deduce_mapping())
