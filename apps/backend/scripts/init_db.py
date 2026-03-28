"""Run once to create indexes and seed a default super_admin user."""

import asyncio
import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017/restobuzz")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme123")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def main():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client.get_default_database()

    # Create indexes
    from pymongo import ASCENDING, DESCENDING, IndexModel

    await db.users.create_index("email", unique=True)
    await db.campaign_jobs.create_indexes(
        [
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_by", ASCENDING)]),
        ]
    )
    await db.message_logs.create_indexes(
        [
            IndexModel([("job_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel(
                [("wa_message_id", ASCENDING)],
                unique=True,
                partialFilterExpression={"wa_message_id": {"$type": "string"}},
            ),
            IndexModel([("locked_until", ASCENDING)]),
        ]
    )
    await db.inbound_messages.create_indexes(
        [
            IndexModel([("wa_message_id", ASCENDING)], unique=True),
            IndexModel([("from_phone", ASCENDING), ("received_at", DESCENDING)]),
        ]
    )
    await db.suppression_list.create_index("phone", unique=True)

    # Seed super_admin
    existing = await db.users.find_one({"email": ADMIN_EMAIL})
    admin_id = None
    if not existing:
        result = await db.users.insert_one(
            {
                "email": ADMIN_EMAIL,
                "hashed_password": pwd_context.hash(ADMIN_PASSWORD),
                "role": "super_admin",
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "last_login": None,
            }
        )
        admin_id = result.inserted_id
        print(f"Created super_admin: {ADMIN_EMAIL}")
    else:
        admin_id = existing["_id"]
        print(f"User {ADMIN_EMAIL} already exists")

    # Seed restaurants
    from app.database import init_indexes
    await init_indexes() # ensure ALL indexes (including new ones) are created

    RESTAURANTS = [
        {"id": "r1", "name": "Soraia", "location": "Downtown", "emoji": "🍔", "color": "bg-orange-500"},
        {"id": "r2", "name": "Fielia", "location": "Midtown", "emoji": "🍣", "color": "bg-pink-500"},
        {"id": "r3", "name": "Gigi", "location": "West End", "emoji": "🍕", "color": "bg-red-500"},
        {"id": "r4", "name": "Scarlett House Bandra", "location": "East Side", "emoji": "🍛", "color": "bg-yellow-500"},
        {"id": "r5", "name": "Scarlett House Juhu", "location": "Uptown", "emoji": "🥗", "color": "bg-green-500"},
        {"id": "r6", "name": "Sweeney", "location": "Waterfront", "emoji": "🦞", "color": "bg-blue-500"},
    ]

    for r in RESTAURANTS:
        await db.restaurants.update_one(
            {"id": r["id"]},
            {"$set": r},
            upsert=True
        )
    print(f"Seeded {len(RESTAURANTS)} restaurants")

    # Although super_admin bypasses the check, we can still assign them to all for consistency
    # especially for the UI which might rely on the list_restaurants endpoint.
    for r in RESTAURANTS:
        await db.user_restaurant_roles.update_one(
            {"user_id": admin_id, "restaurant_id": r["id"]},
            {"$set": {"role": "admin"}},
            upsert=True
        )
    print("Assigned super_admin to all restaurants")

    client.close()
    print("DB initialization complete.")


if __name__ == "__main__":
    asyncio.run(main())
