import asyncio
import resend
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape, StrictUndefined
from email_validator import validate_email, EmailNotValidError
from motor.motor_asyncio import AsyncIOMotorDatabase
import os

from app.config import settings
from app.database import get_fielia_db
from app.core.logging import get_logger
from app.constants.alert_types import AlertType

logger = get_logger(__name__)

# Initialize Resend SDK
resend.api_key = settings.resend_api_key

# Initialize Jinja2 Environment as a singleton
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
    undefined=StrictUndefined
)

class AlertService:
    @staticmethod
    def _get_now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    async def resolve_alert_recipients(restaurant: dict) -> List[str]:
        """
        Combines global recipients, restaurant-specific recipients, and admin email.
        Handles validation, deduplication, and guardrails.
        """
        candidates = []
        
        # 1. Global recipients from env
        candidates.extend(settings.parsed_alert_recipients)
        
        # 2. Restaurant-level specific team
        candidates.extend(restaurant.get("notification_emails", []))
        
        # 3. Restaurant primary email
        admin_email = restaurant.get("email")
        if admin_email:
            candidates.append(admin_email)
            
        final_recipients = []
        seen = set()
        
        for email in candidates:
            if not email or not isinstance(email, str):
                continue
            
            email_cleaned = email.strip().lower()
            if email_cleaned in seen:
                continue
                
            try:
                # Use email-validator to verify format
                validated = validate_email(email_cleaned, check_deliverability=False)
                final_recipients.append(validated.email)
                seen.add(validated.email)
            except EmailNotValidError as e:
                logger.warning("invalid_alert_recipient_skipped", email=email_cleaned, error=str(e))

        # Apply Recipient Count Guardrail
        if len(final_recipients) > settings.max_alert_recipients:
            logger.warning("alert_recipients_truncated", count=len(final_recipients), limit=settings.max_alert_recipients)
            final_recipients = final_recipients[:settings.max_alert_recipients]
            
        return final_recipients

    @staticmethod
    async def _send_email_async(params: dict) -> dict:
        """
        Async-safe wrapper for the synchronous Resend SDK.
        Includes timeout protection.
        """
        loop = asyncio.get_running_loop()
        try:
            # Wrap in wait_for to prevent hanging threads
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: resend.Emails.send(params)),
                timeout=15.0
            )
            return response
        except asyncio.TimeoutError:
            logger.error("resend_timeout", timeout=15.0)
            raise TimeoutError("Resend API request timed out")
        except Exception as e:
            logger.error("resend_execution_failed", error=str(e))
            raise e

    @staticmethod
    async def _log_alert(
        db: AsyncIOMotorDatabase,
        alert_type: AlertType,
        restaurant: dict,
        recipients: List[str],
        subject: str,
        status: str,
        context: Optional[dict] = None,
        provider_response: Optional[dict] = None,
        error: Optional[str] = None
    ):
        """Audit logging for every email alert attempt."""
        try:
            log_doc = {
                "alert_type": alert_type.value,
                "restaurant_id": str(restaurant.get("_id") or restaurant.get("id")),
                "restaurant_name": restaurant.get("name", "Unknown"),
                "recipients": recipients,
                "subject": subject,
                "status": status,
                "context": context,
                "provider": "resend",
                "provider_response": provider_response,
                "error": error,
                "delivery_mode": "background_task",
                "created_at": AlertService._get_now_utc()
            }
            await db.email_alert_logs.insert_one(log_doc)
        except Exception as e:
            logger.error("audit_log_failed", error=str(e))

    @staticmethod
    async def send_alert_email(
        db: AsyncIOMotorDatabase,
        alert_type: AlertType,
        restaurant: dict,
        subject: str,
        template_name: str,
        context: dict
    ):
        """
        Unified internal sender that handles resolution, templating, sending, and logging.
        """
        recipients = await AlertService.resolve_alert_recipients(restaurant)
        
        # Safety check: No recipients
        if not recipients:
            logger.warning("alert_skipped_no_recipients", alert_type=alert_type, restaurant_id=restaurant.get("id"))
            await AlertService._log_alert(db, alert_type, restaurant, [], subject, "SKIPPED", context=context, error="No valid recipients resolved")
            return

        # Prepare context
        full_subject = f"[Dishpatch Alert] {subject}"
        # Compose URLs from dashboard_base_url
        base_url = (settings.dashboard_base_url or "https://restobuzz.eigensu.in").rstrip("/")
        email_context = {
            "subject": full_subject,
            "restaurant_name": restaurant.get("name", "Your Restaurant"),
            "dashboard_url": base_url,
            "cta_url": base_url,
            "now": AlertService._get_now_utc(),
            **context
        }

        # Render Templates
        try:
            template = templates_env.get_template(f"email/{template_name}")
            rendered_html = template.render(**email_context)
            # Simple plain text fallback
            rendered_text = f"Dishpatch Alert: {subject}\n\nRestaurant: {restaurant.get('name')}\n\nPlease check your dashboard for details: {email_context['cta_url']}"
        except Exception as e:
            logger.error("template_rendering_failed", template=template_name, error=str(e))
            await AlertService._log_alert(db, alert_type, restaurant, recipients, subject, "FAILED", context=context, error=f"Template error: {str(e)}")
            return

        # Send via Resend
        params = {
            "from": f"Team Dishpatch <{settings.resend_from_email}>",
            "to": recipients,
            "subject": full_subject,
            "html": rendered_html,
            "text": rendered_text
        }

        try:
            response = await AlertService._send_email_async(params)
            provider_id = response.get("id") if isinstance(response, dict) else None
            await AlertService._log_alert(db, alert_type, restaurant, recipients, params["subject"], "SUCCESS", context=context, provider_response=response)
            logger.info("alert_sent", alert_type=alert_type, recipients=len(recipients), provider_id=provider_id)
        except Exception as e:
            await AlertService._log_alert(db, alert_type, restaurant, recipients, params["subject"], "FAILED", context=context, error=str(e))
            logger.error("alert_dispatch_failed", alert_type=alert_type, error=str(e))

    # --- Public API Functions ---

    @staticmethod
    async def is_idempotent_template_alert(db: AsyncIOMotorDatabase, restaurant_id: str, template_name: str, alert_type: AlertType) -> bool:
        """Ensures we don't send duplicate template alerts within a 5-minute window for a specific restaurant."""
        five_minutes_ago = AlertService._get_now_utc() - timedelta(minutes=5)
        count = await db.email_alert_logs.count_documents({
            "restaurant_id": restaurant_id,
            "alert_type": alert_type.value,
            "context.template_name": template_name,
            "created_at": {"$gte": five_minutes_ago},
            "status": "SUCCESS"
        })
        return count == 0

    @staticmethod
    async def send_template_approved_alert(db: AsyncIOMotorDatabase, restaurant: dict, template_name: str):
        rid = str(restaurant.get("_id") or restaurant.get("id"))
        if not await AlertService.is_idempotent_template_alert(db, rid, template_name, AlertType.TEMPLATE_APPROVED):
            logger.info("template_alert_suppressed_idempotency", template_name=template_name, restaurant_id=rid)
            return

        await AlertService.send_alert_email(
            db,
            AlertType.TEMPLATE_APPROVED,
            restaurant,
            f"Template Approved: {template_name}",
            "template_approved.html",
            {"template_name": template_name}
        )

    @staticmethod
    async def send_template_rejected_alert(db: AsyncIOMotorDatabase, restaurant: dict, template_name: str, rejection_reason: Optional[str] = None):
        rid = str(restaurant.get("_id") or restaurant.get("id"))
        if not await AlertService.is_idempotent_template_alert(db, rid, template_name, AlertType.TEMPLATE_REJECTED):
            logger.info("template_alert_suppressed_idempotency", template_name=template_name, restaurant_id=rid)
            return

        await AlertService.send_alert_email(
            db,
            AlertType.TEMPLATE_REJECTED,
            restaurant,
            f"Template Rejected: {template_name}",
            "template_rejected.html",
            {"template_name": template_name, "rejection_reason": rejection_reason}
        )

    @staticmethod
    async def check_unread_threshold_alert(db: AsyncIOMotorDatabase, restaurant_id: str):
        """
        Intelligent alerting:
        1. Check threshold (9+) (Local + Fielia External)
        2. Check 4h cooldown
        3. Check count growth (only re-alert if count increased by +10 since last alert)
        """
        threshold = settings.unread_alert_threshold
        now = AlertService._get_now_utc()
        cooldown_cutoff = now - timedelta(hours=settings.unread_alert_cooldown_hours)

        # 1. Resolve restaurant first to get settings and last alert state
        from bson.objectid import ObjectId
        from bson.errors import InvalidId
        try:
            rid_oid = ObjectId(restaurant_id) if isinstance(restaurant_id, str) else restaurant_id
            restaurant = await db.restaurants.find_one({"_id": rid_oid})
        except InvalidId:
            restaurant = await db.restaurants.find_one({"id": restaurant_id})

        if not restaurant:
            logger.warning("unread_alert_restaurant_not_found", restaurant_id=restaurant_id)
            return

        # 2. Check local unread count
        unread_count = await db.inbound_messages.count_documents({
            "restaurant_id": restaurant_id,
            "is_read": False,
        })

        # 3. Check Fielia external unread count if feature flag is set
        if restaurant.get("settings", {}).get("uses_fielia_inbox") or restaurant.get("uses_fielia_inbox"):
            try:
                f_db = get_fielia_db()
                if f_db is not None:
                    f_unread = await f_db.inbound_messages.count_documents({"is_read": False})
                    unread_count += f_unread
            except Exception as e:
                logger.error("fielia_count_check_failed", error=str(e), restaurant_id=restaurant_id)

        if unread_count < threshold:
            return

        last_alert_at = restaurant.get("last_unread_alert_at")
        last_alert_count = restaurant.get("last_unread_alert_count", 0)


        # Cooldown check
        if last_alert_at:
            if last_alert_at.tzinfo is None:
                last_alert_at = last_alert_at.replace(tzinfo=timezone.utc)
            
            if last_alert_at >= cooldown_cutoff:
                # Within cooldown, but check for significant growth (+10 messages)
                if unread_count < (last_alert_count + settings.unread_alert_growth_threshold):
                    logger.info("unread_alert_suppressed_cooldown", restaurant_id=restaurant_id, current=unread_count, last=last_alert_count)
                    return

        # Atomically update to prevent race conditions (Compare-And-Swap)
        # Only send if last_unread_alert_at is still what we read (or never existed)
        cas_filter = {
            "_id": restaurant["_id"],
            "$or": [
                {"last_unread_alert_at": last_alert_at},
                {"last_unread_alert_at": {"$exists": False}}
            ]
        }
        
        update_result = await db.restaurants.update_one(
            cas_filter,
            {
                "$set": {
                    "last_unread_alert_at": now,
                    "last_unread_alert_count": unread_count
                }
            }
        )
        
        if update_result.modified_count > 0:
            await AlertService.send_alert_email(
                db,
                AlertType.UNREAD_THRESHOLD,
                restaurant,
                f"{unread_count} Unread Messages",
                "unread_alert.html",
                {"unread_count": unread_count}
            )

    @staticmethod
    async def send_waba_disconnected_alert(db: AsyncIOMotorDatabase, restaurant: dict):
        await AlertService.send_alert_email(
            db,
            AlertType.WABA_DISCONNECTED,
            restaurant,
            "WhatsApp Account Disconnected",
            "waba_disconnected.html",
            {}
        )

    @staticmethod
    async def send_campaign_failed_alert(db: AsyncIOMotorDatabase, restaurant: dict, campaign_name: str, reason: str):
        await AlertService.send_alert_email(
            db,
            AlertType.CAMPAIGN_FAILED,
            restaurant,
            f"Campaign Failed: {campaign_name}",
            "campaign_failed.html",
            {"campaign_name": campaign_name, "failure_reason": reason}
        )

# Singleton instance
alert_service = AlertService()
