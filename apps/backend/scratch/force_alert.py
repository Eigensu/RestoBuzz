import asyncio
import os
import sys

# Ensure backend app is in path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.services.alert_service import alert_service

async def main():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "restobuzz")
    print("Forcing alert check for Fielia (r2)...")
    await alert_service.check_unread_threshold_alert(db, "r2")
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
