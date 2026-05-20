import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    print("Checking DB...")
    client = AsyncIOMotorClient(settings.mongodb_url, serverSelectionTimeoutMS=5000)
    db_name = settings.mongodb_db_name or "dishpatch"
    db = client[db_name]
    try:
        await db.command("ping")
        print("DB Ping OK")
    except Exception as e:
        print("DB Ping Failed:", e)
    client.close()

if __name__ == "__main__":
    asyncio.run(check())
