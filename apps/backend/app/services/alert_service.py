import asyncio
import html
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


async def notify_restaurant_admins(db: AsyncIOMotorDatabase, restaurant_id: str, subject: str, html_body: str):
    """Sends an email to all active admins of a restaurant."""
    emails = await get_restaurant_admin_emails(db, restaurant_id)
    if not emails:
        logger.info("no_admins_to_notify", restaurant_id=restaurant_id)
        return

    for email_addr in emails:
        try:
            # send_email is synchronous (Resend SDK); run it off the event loop
            # so we don't block uvicorn's async event loop.
            await asyncio.to_thread(send_email, to=email_addr, subject=subject, html=html_body)
            logger.info("alert_email_sent", to=email_addr, subject=subject, restaurant_id=restaurant_id)
        except Exception as e:
            logger.error("alert_email_failed", to=email_addr, error=str(e))


async def handle_template_approval_alert(
    db: AsyncIOMotorDatabase,
    template_name: str,
    language: str,
    category: str = "MARKETING",
):
    """Notify admins that a WhatsApp template has been approved.

    NOTE: This is intended to be called from a Celery background task
    (app.workers.alert_tasks.send_template_approval_alert_task) — not directly
    from an HTTP handler — so the email fan-out does not block a request.
    """
    # Escape all user-controlled values before interpolating into HTML.
    safe_template_name = html.escape(template_name)
    safe_language = html.escape(language)
    safe_category = html.escape(category)

    # Since templates are global to the WABA, notify all restaurants.
    # In a multi-tenant WABA setup, filter by WABA ID.
    cursor = db.restaurants.find({}, {"id": 1, "name": 1})
    async for rest in cursor:
        rid = rest.get("id") or str(rest["_id"])
        safe_name = html.escape(rest.get("name", "Your Restaurant"))

        subject = f"✅ Template Approved: {safe_template_name}"
        html_body = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
            <h2 style="color: #24422e;">Great news, {safe_name}!</h2>
            <p>Your WhatsApp template <strong>{safe_template_name}</strong> ({safe_language}) category <strong>{safe_category}</strong> has been <strong>APPROVED</strong> by Meta.</p>
            <p>You can now use this template in your marketing campaigns.</p>
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #888;">
                Sent by RestoBuzz Automated Alerts
            </div>
        </div>
        """
        await notify_restaurant_admins(db, rid, subject, html_body)


async def check_unread_threshold_alert(db: AsyncIOMotorDatabase, restaurant_id: str):
    """Check if unread messages exceed threshold and send alert if not recently alerted.

    Uses find_one_and_update to atomically claim the alert slot (prevents duplicate
    emails when called concurrently) before building and sending the email.
    """
    threshold = settings.unread_alert_threshold
    unread_count = await db.inbound_messages.count_documents({
        "restaurant_id": restaurant_id,
        "is_read": False,
    })

    if unread_count <= threshold:
        return

    now = datetime.now(timezone.utc)
    cooldown_cutoff = now - timedelta(hours=4)

    # Atomic claim: only proceed if last_unread_alert_at is missing or older
    # than the cooldown window. This replaces the old read+check+update pattern.
    restaurant = await db.restaurants.find_one_and_update(
        {
            "$and": [
                {
                    "$or": [
                        {"id": restaurant_id},
                        {"_id": _try_object_id(restaurant_id)},
                    ]
                },
                {
                    "$or": [
                        {"last_unread_alert_at": {"$exists": False}},
                        {"last_unread_alert_at": None},
                        {"last_unread_alert_at": {"$lt": cooldown_cutoff}},
                    ]
                },
            ]
        },
        {"$set": {"last_unread_alert_at": now}},
        return_document=False,  # we only need to know the claim succeeded
    )

    if not restaurant:
        # Either the restaurant doesn't exist or it was alerted within the cooldown.
        return

    safe_name = html.escape(restaurant.get("name", "Your Restaurant"))

    subject = f"⚠️ Action Required: {unread_count} Unread Messages"
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #d32f2f;">Unread Messages Alert</h2>
        <p>Hello {safe_name},</p>
        <p>You have <strong>{unread_count}</strong> unread messages in your inbox.</p>
        <p>Please check your dashboard to respond to your customers and maintain a good response rate.</p>
        <a href="{settings.dashboard_url}/reservations" style="display: inline-block; background-color: #24422e; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 10px;">Open Dashboard</a>
        <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #888;">
            You are receiving this because unread messages exceeded the threshold of {threshold}.
            Cooldown period is 4 hours.
        </div>
    </div>
    """

    await notify_restaurant_admins(db, restaurant_id, subject, html_body)


def _try_object_id(value: str):
    """Return an ObjectId from value, or None if it's not a valid ObjectId string."""
    try:
        return to_object_id(value)
    except Exception:
        return None
