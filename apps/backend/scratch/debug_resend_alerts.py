import os
import sys

# Ensure backend app is in path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.services.alert_service import AlertService
from app.constants.alert_types import AlertType

async def debug_alerts():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "restobuzz")
    
    # Check settings
    print(f"--- Settings ---")
    print(f"Alert Recipients (Raw): {settings.alert_recipients}")
    print(f"Alert Recipients (Parsed): {settings.parsed_alert_recipients}")

    # Check alert logs
    print("\n--- Recent UNREAD_THRESHOLD Alert Logs ---")
    logs = await db.email_alert_logs.find({"alert_type": AlertType.UNREAD_THRESHOLD.value}).sort("created_at", -1).limit(5).to_list(5)
    for log in logs:
        print(f"Time: {log.get('created_at')} | Status: {log.get('status')} | Count: {log.get('context', {}).get('unread_count')} | Recipients: {log.get('recipients')}")
        if log.get("error"):
            print(f"   Error: {log.get('error')}")

    # Check all restaurants with unread messages
    print("\n--- All Restaurants Unread Scan ---")
    restaurants = await db.restaurants.find().to_list(100)
    for r in restaurants:
        rid = r.get("id") or str(r["_id"])
        local_unread = await db.inbound_messages.count_documents({
            "restaurant_id": rid,
            "is_read": False,
        })
        if local_unread > 0:
            print(f"Rest: {r.get('name')} ({rid}) | Unread: {local_unread} | Last Alert: {r.get('last_unread_alert_at')}")


if __name__ == "__main__":
    asyncio.run(debug_alerts())
