import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.database import get_db
from app.services.alert_service import alert_service, AlertService
from app.constants.alert_types import AlertType
import inspect

async def trigger_test_alert(restaurant_id: str):
    db = get_db()
    print(f"Force-triggering unread alert for {restaurant_id}...")
    
    # We use the internal sender to bypass cooldown/threshold checks for the test
    # Find restaurant
    from bson.objectid import ObjectId
    from bson.errors import InvalidId
    try:
        rid_oid = ObjectId(restaurant_id) if isinstance(restaurant_id, str) else restaurant_id
        restaurant = await db.restaurants.find_one({"_id": rid_oid})
    except InvalidId:
        restaurant = await db.restaurants.find_one({"id": restaurant_id})

    if not restaurant:
        print(f"Restaurant {restaurant_id} not found.")
        return

    # Call the core sender directly for the test
    await alert_service.send_alert_email(
        db,
        AlertType.UNREAD_THRESHOLD,
        restaurant,
        f"TEST ALERT: {12} Unread Messages",
        "unread_alert.html",
        {"unread_count": 12}
    )
    print("Alert dispatched via Resend.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scratch/trigger_unread_test.py <restaurant_id>")
    else:
        asyncio.run(trigger_test_alert(sys.argv[1]))
