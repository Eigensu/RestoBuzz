import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings
from app.database import get_fielia_db

async def _check_recent_alerts(db):
    print("\n--- Recent Alert Logs ---")
    logs = await db.email_alert_logs.find().sort("created_at", -1).limit(10).to_list(10)
    if not logs:
        print("No alert logs found.")
    for log in logs:
        print(f"Time: {log.get('created_at')} | Type: {log.get('alert_type')} | Status: {log.get('status')} | Subject: {log.get('subject')}")
        if log.get("error"):
            print(f"   Error: {log.get('error')}")

async def _check_global_unreads(db):
    print("\n--- Global Unread Scan ---")
    local_unreads = await db.inbound_messages.find({"is_read": False}).to_list(100)
    print(f"Found {len(local_unreads)} unread messages in Local DB.")
    for m in local_unreads[:5]:
        print(f"   - From: {m.get('from_phone')}, Restaurant: {m.get('restaurant_id')}, PhoneID: {m.get('wa_phone_id')}")

async def _check_restaurant_mapping(db):
    print("\n--- Restaurant Mapping Check ---")
    restaurants = await db.restaurants.find().to_list(10)
    for rest in restaurants:
        print(f"Restaurant: {rest.get('name')} | wa_phone_ids: {rest.get('wa_phone_ids')}")

async def _check_restaurant_alert_state(db):
    print("\n--- Restaurant Alert State ---")
    restaurants = await db.restaurants.find().to_list(10)
    for rest in restaurants:
        rid = rest.get("id") or str(rest["_id"])
        unread = await db.inbound_messages.count_documents({"restaurant_id": rid, "is_read": False})
        
        fielia_unread = 0
        if rid == "r2":
            f_db = get_fielia_db()
            if f_db is not None:
                fielia_unread = await f_db.inbound_messages.count_documents({"is_read": False})

        print(f"Restaurant: {rest.get('name')} ({rid})")
        print(f"   Local Unread: {unread}")
        if rid == "r2":
            print(f"   Fielia External Unread: {fielia_unread}")
            print(f"   Total Unread: {unread + fielia_unread}")
        
        print(f"   Last Alert At: {rest.get('last_unread_alert_at')}")
        print(f"   Last Alert Count: {rest.get('last_unread_alert_count')}")
        print(f"   Emails: {rest.get('email')}, Team: {rest.get('notification_emails')}")

async def check():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or "RestoBuzz"
    db = client.get_database(db_name)
    
    print(f"Checking DB: {db_name}")
    
    await _check_recent_alerts(db)
    await _check_global_unreads(db)
    await _check_restaurant_mapping(db)
    await _check_restaurant_alert_state(db)

if __name__ == "__main__":
    asyncio.run(check())
