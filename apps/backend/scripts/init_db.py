"""Run once to create indexes and seed a default super_admin user."""

import asyncio
import os
import sys
import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

# Add the apps/backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def main():
    from app.config import settings
    # For Atlas SRV URLs, we must use the configured mongodb_url and mongodb_db_name
    # directly to ensure consistency with the backend.
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_default_database(settings.mongodb_db_name)
    
    admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "changeme123")

    # Create indexes via central database module
    from app.database import init_indexes
    await init_indexes()
    print("Database indexes initialized")

    # Seed super_admin
    existing = await db.users.find_one({"email": admin_email})
    admin_id = None
    if not existing:
        result = await db.users.insert_one(
            {
                "email": admin_email,
                "hashed_password": pwd_context.hash(admin_password),
                "role": "super_admin",
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "last_login": None,
            }
        )
        admin_id = result.inserted_id
        print(f"Created super_admin: {admin_email}")
    else:
        admin_id = existing["_id"]
        # Update user to ensure role and password match current configuration
        await db.users.update_one(
            {"_id": admin_id},
            {"$set": {
                "hashed_password": pwd_context.hash(admin_password),
                "role": "super_admin",
                "is_active": True
            }}
        )
        print(f"User {admin_email} already exists — password and role (super_admin) updated.")

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
