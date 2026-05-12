import os
import sys

# Ensure backend app is in path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

async def check_errors():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "restobuzz")
    
    print("--- Recent Webhook Errors ---")
    errors = await db.webhook_errors.find().sort("received_at", -1).limit(5).to_list(5)
    for err in errors:
        print(f"Time: {err.get('received_at')} | Error: {err.get('error')}")
        # print(f"Payload: {err.get('payload')}")

if __name__ == "__main__":
    asyncio.run(check_errors())
