import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings
from app.services.alert_service import alert_service

async def force():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "RestoBuzz")
    
    restaurant_id = "r2" # Fielia
    print(f"Forcing unread alert check for {restaurant_id}...")
    
    await alert_service.check_unread_threshold_alert(db, restaurant_id)
    
    print("\n--- Checking logs for results ---")
    log = await db.email_alert_logs.find().sort("created_at", -1).limit(1).to_list(1)
    if log:
        l = log[0]
        print(f"Status: {l.get('status')}")
        print(f"Recipients: {l.get('recipients')}")
        if l.get("error"):
            print(f"Error: {l.get('error')}")
    else:
        print("No log entry created - threshold may not have been met or cooldown active.")

if __name__ == "__main__":
    asyncio.run(force())
