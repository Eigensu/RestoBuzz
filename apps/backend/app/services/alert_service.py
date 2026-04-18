from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.services.resend_client import send_email
from app.config import settings
from app.core.logging import get_logger
from app.core.utils import to_object_id

logger = get_logger(__name__)

async def get_restaurant_admin_emails(db: AsyncIOMotorDatabase, restaurant_id: str) -> list[str]:
    """Find all users with 'admin' role (and potentially others) for this restaurant."""
    # We can expand roles list here as needed
    target_roles = ["admin"]
    cursor = db.user_restaurant_roles.find({"restaurant_id": restaurant_id, "role": {"$in": target_roles}})
    admin_roles = [doc async for doc in cursor]
    
    if not admin_roles:
        return []
        
    user_ids = [to_object_id(r["user_id"]) for r in admin_roles]
    users_cursor = db.users.find({"_id": {"$in": user_ids}, "is_active": True})
    return [u["email"] async for u in users_cursor if u.get("email")]

async def notify_restaurant_admins(db: AsyncIOMotorDatabase, restaurant_id: str, subject: str, html: str):
    """Sends an email to all active admins of a restaurant."""
    emails = await get_restaurant_admin_emails(db, restaurant_id)
    if not emails:
        logger.info("no_admins_to_notify", restaurant_id=restaurant_id)
        return

    for email in emails:
        try:
            send_email(to=email, subject=subject, html=html)
            logger.info("alert_email_sent", to=email, subject=subject, restaurant_id=restaurant_id)
        except Exception as e:
            logger.error("alert_email_failed", to=email, error=str(e))

async def handle_template_approval_alert(db: AsyncIOMotorDatabase, template_name: str, language: str, category: str = "MARKETING"):
    """Notify admins that a WhatsApp template has been approved."""
    # Since templates are global to the WABA, we notify all restaurants.
    # In a multi-tenant WABA setup, we'd filter by WABA ID.
    cursor = db.restaurants.find({}, {"id": 1, "name": 1})
    async for rest in cursor:
        rid = rest.get("id") or str(rest["_id"])
        name = rest.get("name", "Your Restaurant")
        
        subject = f"✅ Template Approved: {template_name}"
        html = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
            <h2 style="color: #24422e;">Great news, {name}!</h2>
            <p>Your WhatsApp template <strong>{template_name}</strong> ({language}) category <strong>{category}</strong> has been <strong>APPROVED</strong> by Meta.</p>
            <p>You can now use this template in your marketing campaigns.</p>
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #888;">
                Sent by RestoBuzz Automated Alerts
            </div>
        </div>
        """
        await notify_restaurant_admins(db, rid, subject, html)

async def check_unread_threshold_alert(db: AsyncIOMotorDatabase, restaurant_id: str):
    """Check if unread messages > 9 and send alert if not recently alerted."""
    unread_count = await db.inbound_messages.count_documents({
        "restaurant_id": restaurant_id,
        "is_read": False
    })
    
    if unread_count <= 9:
        return

    # Check debouncing
    restaurant = await db.restaurants.find_one({"id": restaurant_id})
    if not restaurant:
        # Fallback to _id search
        try:
            restaurant = await db.restaurants.find_one({"_id": to_object_id(restaurant_id)})
        except:
            return
            
    if not restaurant:
        return

    last_alert = restaurant.get("last_unread_alert_at")
    now = datetime.now(timezone.utc)
    
    # 4 hour cooldown
    if last_alert and (now - last_alert.replace(tzinfo=timezone.utc) < timedelta(hours=4)):
        return

    name = restaurant.get("name", "Your Restaurant")
    subject = f"⚠️ Action Required: {unread_count} Unread Messages"
    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #d32f2f;">Unread Messages Alert</h2>
        <p>Hello {name},</p>
        <p>You have <strong>{unread_count}</strong> unread messages in your inbox.</p>
        <p>Please check your dashboard to respond to your customers and maintain a good response rate.</p>
        <a href="{settings.dashboard_url}/reservations" style="display: inline-block; background-color: #24422e; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 10px;">Open Dashboard</a>
        <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #888;">
            You are receiving this because unread messages exceeded the threshold of 9.
            Cooldown period is 4 hours.
        </div>
    </div>
    """
    
    await notify_restaurant_admins(db, restaurant_id, subject, html)
    
    # Update last alert timestamp
    await db.restaurants.update_one(
        {"_id": restaurant["_id"]},
        {"$set": {"last_unread_alert_at": now}}
    )
