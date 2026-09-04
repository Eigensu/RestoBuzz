import asyncio
import os
import sys
from pathlib import Path

# Setup import path
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def ensure_indexes():
    print("Connecting to MongoDB...")
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.split("/")[-1].split("?")[0]
    if not db_name:
        db_name = "dishpatch"
    db = client[db_name]
    
    print(f"Using database: {db_name}")
    
    # 1. Unique index on phone + restaurant_id for members
    # This prevents duplicates and race conditions
    print("Creating unique index on members(restaurant_id, phone)...")
    await db.members.create_index(
        [("restaurant_id", 1), ("phone", 1)],
        unique=True,
        partialFilterExpression={"phone": {"$type": "string"}}
    )
    
    # 2. Index on type for filtering
    print("Creating index on members(type)...")
    await db.members.create_index([("type", 1)])
    
    # 3. Index on joined_at for sorting
    print("Creating index on members(joined_at)...")
    await db.members.create_index([("joined_at", -1)])
    
    # 4. Indexes for ReserveGo
    print("Creating indexes for ReserveGo data...")
    await db.reservego_uploads.create_index([("restaurant_id", 1), ("phone", 1)])
    await db.reservego_bill_data.create_index([("restaurant_id", 1), ("bill_number", 1)])
    
    # 5. BSUID identity links (see app/services/wa_identity.py)
    print("Creating indexes for wa_identities...")
    await db.wa_identities.create_index([("bsuid", 1)], unique=True)
    # Sparse: rows for a username user we have never learned a phone for carry
    # no phone field, and they must not collide on null.
    await db.wa_identities.create_index([("phone", 1)], sparse=True)

    # 6. Conversation grouping key on inbound messages. Sparse because rows
    # written before BSUID support have no contact_key and are matched on
    # from_phone instead.
    print("Creating index on inbound_messages(restaurant_id, contact_key)...")
    await db.inbound_messages.create_index(
        [("restaurant_id", 1), ("contact_key", 1), ("received_at", -1)],
        sparse=True,
    )

    print("\nAll indexes ensured successfully.")
    client.close()

if __name__ == "__main__":
    asyncio.run(ensure_indexes())
