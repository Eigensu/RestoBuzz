"""Run once to create indexes and seed a default super_admin user."""

import asyncio
import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017/whatsapp_bulk")
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
    if not existing:
        await db.users.insert_one(
            {
                "email": ADMIN_EMAIL,
                "hashed_password": pwd_context.hash(ADMIN_PASSWORD),
                "role": "super_admin",
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "last_login": None,
            }
        )
        print(f"Created super_admin: {ADMIN_EMAIL}")
    else:
        print(f"User {ADMIN_EMAIL} already exists")

    client.close()
    print("DB initialization complete.")


if __name__ == "__main__":
    asyncio.run(main())
