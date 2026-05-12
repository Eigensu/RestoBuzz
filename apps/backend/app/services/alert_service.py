"""Alert service for sending email notifications via Resend."""

import asyncio
import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional, TypedDict

import resend
from bson.errors import InvalidId
from bson.objectid import ObjectId
from email_validator import validate_email, EmailNotValidError
from jinja2 import Environment, FileSystemLoader, select_autoescape, StrictUndefined
from motor.motor_asyncio import AsyncIOMotorDatabase

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
    undefined=StrictUndefined,
)


class _AlertLogExtras(TypedDict, total=False):
    """Optional keyword arguments for _log_alert to keep its signature under the limit."""

    context: Optional[dict]
    provider_response: Optional[dict]
    error: Optional[str]


class AlertService:
    """Service for dispatching email alerts via Resend with audit logging."""

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
                validated = validate_email(email_cleaned, check_deliverability=False)
                final_recipients.append(validated.email)
                seen.add(validated.email)
            except EmailNotValidError as e:
                logger.warning(
                    "invalid_alert_recipient_skipped", email=email_cleaned, error=str(e)
                )

        # Apply Recipient Count Guardrail
        if len(final_recipients) > settings.max_alert_recipients:
            logger.warning(
                "alert_recipients_truncated",
                count=len(final_recipients),
                limit=settings.max_alert_recipients,
            )
            final_recipients = final_recipients[: settings.max_alert_recipients]

        return final_recipients

    @staticmethod
    async def _send_email_async(params: dict) -> dict:
        """
        Async-safe wrapper for the synchronous Resend SDK.
        Includes timeout protection.
        """
        loop = asyncio.get_running_loop()
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: resend.Emails.send(params)),
                timeout=15.0,
            )
            return response
        except asyncio.TimeoutError as exc:
            logger.error("resend_timeout", timeout=15.0)
            raise TimeoutError("Resend API request timed out") from exc
        except Exception as e:
            logger.error("resend_execution_failed", error=str(e))
            raise

    @staticmethod
    async def _log_alert(
        db: AsyncIOMotorDatabase,
        alert_type: AlertType,
        restaurant: dict,
        recipients: List[str],
        subject: str,
        status: str,
        extras: Optional[_AlertLogExtras] = None,
    ) -> None:
        """Audit logging for every email alert attempt."""
        extras = extras or {}
        try:
            log_doc = {
                "alert_type": alert_type.value,
                "restaurant_id": str(restaurant.get("_id") or restaurant.get("id")),
                "restaurant_name": restaurant.get("name", "Unknown"),
                "recipients": recipients,
                "subject": subject,
                "status": status,
                "context": extras.get("context"),
                "provider": "resend",
                "provider_response": extras.get("provider_response"),
                "error": extras.get("error"),
                "delivery_mode": "background_task",
                "created_at": AlertService._get_now_utc(),
            }
            await db.email_alert_logs.insert_one(log_doc)
        except Exception as e:
            logger.error("audit_log_failed", error=str(e))

    @staticmethod
    def _build_email_context(
        subject: str, restaurant: dict, context: dict
    ) -> tuple[str, dict]:
        """Build the full subject line and Jinja2 template context."""
        full_subject = f"[Dishpatch Alert] {subject}"
        base_url = (
            settings.dashboard_base_url or "https://restobuzz.eigensu.in"
        ).rstrip("/")
        email_context = {
            "subject": full_subject,
            "restaurant_name": restaurant.get("name", "Your Restaurant"),
            "dashboard_url": base_url,
            "cta_url": base_url,
            "now": AlertService._get_now_utc(),
            **context,
        }
        return full_subject, email_context

    @staticmethod
    async def send_alert_email(
        db: AsyncIOMotorDatabase,
        alert_type: AlertType,
        restaurant: dict,
        subject: str,
        template_name: str,
        context: dict,
    ) -> None:
        """
        Unified internal sender that handles resolution, templating, sending, and logging.
        """
        recipients = await AlertService.resolve_alert_recipients(restaurant)

        if not recipients:
            logger.warning(
                "alert_skipped_no_recipients",
                alert_type=alert_type,
                restaurant_id=restaurant.get("id"),
            )
            await AlertService._log_alert(
                db,
                alert_type,
                restaurant,
                [],
                subject,
                "SKIPPED",
                extras={"context": context, "error": "No valid recipients resolved"},
            )
            return

        full_subject, email_context = AlertService._build_email_context(
            subject, restaurant, context
        )

        rendered_html, rendered_text = AlertService._render_template(
            template_name, subject, email_context
        )
        if rendered_html is None:
            await AlertService._log_alert(
                db,
                alert_type,
                restaurant,
                recipients,
                subject,
                "FAILED",
                extras={"context": context, "error": rendered_text},
            )
            return

        params = {
            "from": f"Team Dishpatch <{settings.resend_from_email}>",
            "to": recipients,
            "subject": full_subject,
            "html": rendered_html,
            "text": rendered_text,
        }

        await AlertService._dispatch_email(
            db, alert_type, restaurant, recipients, params, context
        )

    @staticmethod
    def _render_template(
        template_name: str, subject: str, email_context: dict
    ) -> tuple[Optional[str], str]:
        """Render the Jinja2 template. Returns (html, text) on success or (None, error_msg) on failure."""
        try:
            template = templates_env.get_template(f"email/{template_name}")
            rendered_html = template.render(**email_context)
            rendered_text = (
                f"Dishpatch Alert: {subject}\n\n"
                f"Restaurant: {email_context.get('restaurant_name')}\n\n"
                f"Please check your dashboard for details: {email_context['cta_url']}"
            )
            return rendered_html, rendered_text
        except Exception as e:
            logger.error(
                "template_rendering_failed", template=template_name, error=str(e)
            )
            return None, f"Template error: {str(e)}"

    @staticmethod
    async def _dispatch_email(
        db: AsyncIOMotorDatabase,
        alert_type: AlertType,
        restaurant: dict,
        recipients: List[str],
        params: dict,
        context: dict,
    ) -> None:
        """Send via Resend and write the audit log entry."""
        try:
            response = await AlertService._send_email_async(params)
            provider_id = response.get("id") if isinstance(response, dict) else None
            await AlertService._log_alert(
                db,
                alert_type,
                restaurant,
                recipients,
                params["subject"],
                "SUCCESS",
                extras={"context": context, "provider_response": response},
            )
            logger.info(
                "alert_sent",
                alert_type=alert_type,
                recipients=len(recipients),
                provider_id=provider_id,
            )
        except Exception as e:
            await AlertService._log_alert(
                db,
                alert_type,
                restaurant,
                recipients,
                params["subject"],
                "FAILED",
                extras={"context": context, "error": str(e)},
            )
            logger.error("alert_dispatch_failed", alert_type=alert_type, error=str(e))

    # --- Public API Functions ---

    @staticmethod
    async def is_idempotent_template_alert(
        db: AsyncIOMotorDatabase,
        restaurant_id: str,
        template_name: str,
        alert_type: AlertType,
    ) -> bool:
        """Return True if no duplicate alert was sent in the last 5 minutes for this restaurant."""
        five_minutes_ago = AlertService._get_now_utc() - timedelta(minutes=5)
        count = await db.email_alert_logs.count_documents(
            {
                "restaurant_id": restaurant_id,
                "alert_type": alert_type.value,
                "context.template_name": template_name,
                "created_at": {"$gte": five_minutes_ago},
                "status": "SUCCESS",
            }
        )
        return count == 0

    @staticmethod
    async def send_template_approved_alert(
        db: AsyncIOMotorDatabase, restaurant: dict, template_name: str
    ) -> None:
        """Send a template-approved notification, suppressed if sent within the last 5 minutes."""
        rid = str(restaurant.get("_id") or restaurant.get("id"))
        if not await AlertService.is_idempotent_template_alert(
            db, rid, template_name, AlertType.TEMPLATE_APPROVED
        ):
            logger.info(
                "template_alert_suppressed_idempotency",
                template_name=template_name,
                restaurant_id=rid,
            )
            return

        await AlertService.send_alert_email(
            db,
            AlertType.TEMPLATE_APPROVED,
            restaurant,
            f"Template Approved: {template_name}",
            "template_approved.html",
            {"template_name": template_name},
        )

    @staticmethod
    async def send_template_rejected_alert(
        db: AsyncIOMotorDatabase,
        restaurant: dict,
        template_name: str,
        rejection_reason: Optional[str] = None,
    ) -> None:
        """Send a template-rejected notification, suppressed if sent within the last 5 minutes."""
        rid = str(restaurant.get("_id") or restaurant.get("id"))
        if not await AlertService.is_idempotent_template_alert(
            db, rid, template_name, AlertType.TEMPLATE_REJECTED
        ):
            logger.info(
                "template_alert_suppressed_idempotency",
                template_name=template_name,
                restaurant_id=rid,
            )
            return

        await AlertService.send_alert_email(
            db,
            AlertType.TEMPLATE_REJECTED,
            restaurant,
            f"Template Rejected: {template_name}",
            "template_rejected.html",
            {"template_name": template_name, "rejection_reason": rejection_reason},
        )

    @staticmethod
    async def _fetch_unread_count(
        db: AsyncIOMotorDatabase, restaurant: dict, restaurant_id: str
    ) -> int:
        """Return total unread count across local and optional Fielia inbox."""
        unread_count = await db.inbound_messages.count_documents(
            {"restaurant_id": restaurant_id, "is_read": False}
        )

        uses_fielia = restaurant.get("settings", {}).get(
            "uses_fielia_inbox"
        ) or restaurant.get("uses_fielia_inbox")
        if uses_fielia:
            try:
                f_db = get_fielia_db()
                if f_db is not None:
                    unread_count += await f_db.inbound_messages.count_documents(
                        {"is_read": False}
                    )
            except Exception as e:
                logger.error(
                    "fielia_count_check_failed",
                    error=str(e),
                    restaurant_id=restaurant_id,
                )

        return unread_count

    @staticmethod
    async def _fetch_restaurant(
        db: AsyncIOMotorDatabase, restaurant_id: str
    ) -> Optional[dict]:
        """Fetch a restaurant document by string ID, trying ObjectId then string id."""
        try:
            rid_oid = (
                ObjectId(restaurant_id)
                if isinstance(restaurant_id, str)
                else restaurant_id
            )
            return await db.restaurants.find_one({"_id": rid_oid})
        except InvalidId:
            return await db.restaurants.find_one({"id": restaurant_id})

    @staticmethod
    async def check_unread_threshold_alert(
        db: AsyncIOMotorDatabase, restaurant_id: str
    ) -> None:
        """
        Intelligent alerting:
        1. Check threshold (9+) (Local + Fielia External)
        2. Check 4h cooldown
        3. Check count growth (only re-alert if count increased by +10 since last alert)
        """
        restaurant = await AlertService._fetch_restaurant(db, restaurant_id)
        if not restaurant:
            return

        unread_count = await AlertService._fetch_unread_count(
            db, restaurant, restaurant_id
        )
        if unread_count < settings.unread_alert_threshold:
            return

        now = AlertService._get_now_utc()
        cooldown_cutoff = now - timedelta(hours=settings.unread_alert_cooldown_hours)
        last_alert_at = restaurant.get("last_unread_alert_at")
        last_alert_count = restaurant.get("last_unread_alert_count", 0)

        if last_alert_at and last_alert_at >= cooldown_cutoff:
            if unread_count < (last_alert_count + 10):
                return

        # Atomically claim the send slot (Compare-And-Swap).
        # Only one worker wins if multiple Celery tasks race here simultaneously.
        cas_filter = {
            "_id": restaurant["_id"],
            "$or": [
                {"last_unread_alert_at": last_alert_at},
                {"last_unread_alert_at": {"$exists": False}},
            ],
            "unread_alert_claimed": {"$ne": True},
        }

        update_result = await db.restaurants.update_one(
            cas_filter,
            {"$set": {"unread_alert_claimed": True, "unread_alert_claimed_at": now}},
        )

        if update_result.modified_count == 0:
            return

        # We hold the claim. Attempt the send.
        try:
            await AlertService.send_alert_email(
                db,
                AlertType.UNREAD_THRESHOLD,
                restaurant,
                f"{unread_count} Unread Messages",
                "unread_alert.html",
                {"unread_count": unread_count},
            )
            # Finalize: record the cooldown timestamp only after a successful send.
            await db.restaurants.update_one(
                {"_id": restaurant["_id"]},
                {
                    "$set": {
                        "last_unread_alert_at": now,
                        "last_unread_alert_count": unread_count,
                    },
                    "$unset": {
                        "unread_alert_claimed": "",
                        "unread_alert_claimed_at": "",
                    },
                },
            )
        except Exception:
            # Roll back the claim so the next webhook attempt can retry.
            await db.restaurants.update_one(
                {"_id": restaurant["_id"]},
                {
                    "$unset": {
                        "unread_alert_claimed": "",
                        "unread_alert_claimed_at": "",
                    }
                },
            )
            raise

    @staticmethod
    async def send_waba_disconnected_alert(
        db: AsyncIOMotorDatabase, restaurant: dict
    ) -> None:
        """Send a WhatsApp account disconnected alert."""
        await AlertService.send_alert_email(
            db,
            AlertType.WABA_DISCONNECTED,
            restaurant,
            "WhatsApp Account Disconnected",
            "waba_disconnected.html",
            {},
        )

    @staticmethod
    async def send_campaign_failed_alert(
        db: AsyncIOMotorDatabase, restaurant: dict, campaign_name: str, reason: str
    ) -> None:
        """Send a campaign failure alert."""
        await AlertService.send_alert_email(
            db,
            AlertType.CAMPAIGN_FAILED,
            restaurant,
            f"Campaign Failed: {campaign_name}",
            "campaign_failed.html",
            {"campaign_name": campaign_name, "failure_reason": reason},
        )


# Singleton instance
alert_service = AlertService()
