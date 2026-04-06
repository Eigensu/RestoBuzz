"""
Email provider abstraction layer.

Currently implements ResendProvider.
Future: add SESProvider, SendGridProvider behind the same interface.
"""
import resend
from jinja2 import Environment, BaseLoader, select_autoescape
from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Initialise Resend SDK on module load
resend.api_key = settings.resend_api_key

# Jinja2 environment for safe HTML rendering
_jinja_env = Environment(
    loader=BaseLoader(),
    autoescape=select_autoescape(default_for_string=True, default=True),
)


class ResendSendError(Exception):
    """Raised when Resend returns an error for a send call."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def render_template(html: str, variables: dict) -> str:
    """Render a Jinja2 template string with the given variables.
    Variables use triple-brace syntax {{{ VAR }}} in the HTML to match Resend convention,
    but we normalise to Jinja2 {{ VAR }} internally."""
    # Convert Resend-style {{{VAR}}} to Jinja2 {{VAR}}
    normalised = html.replace("{{{", "{{").replace("}}}", "}}")
    template = _jinja_env.from_string(normalised)
    return template.render(**variables)


def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    from_email: str | None = None,
    reply_to: str | None = None,
    tags: dict[str, str] | None = None,
) -> str:
    """Send a single email via Resend. Returns the Resend email ID."""
    params: dict = {
        "from": from_email or settings.resend_from_email,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if reply_to:
        params["reply_to"] = [reply_to]
    if tags:
        params["tags"] = [{"name": k, "value": v} for k, v in tags.items()]

    try:
        result = resend.Emails.send(params)
    except Exception as e:
        logger.error("resend_sdk_exception", to=to, error=str(e))
        raise ResendSendError(str(e))

    if isinstance(result, dict) and result.get("id"):
        return result["id"]

    # handle error response
    error_msg = str(result)
    logger.error("resend_send_failed", to=to, error=error_msg)
    raise ResendSendError(error_msg)


def verify_webhook(payload: str, headers: dict) -> dict:
    """Verify and parse a Resend webhook payload using svix.
    Returns the parsed event dict on success, raises on failure."""
    from svix.webhooks import Webhook, WebhookVerificationError

    if not settings.resend_webhook_secret:
        logger.warning("resend_webhook_secret_not_configured")
        # If secret not configured, parse but don't verify (dev mode)
        import json
        return json.loads(payload)

    wh = Webhook(settings.resend_webhook_secret)
    svix_headers = {
        "svix-id": headers.get("svix-id", ""),
        "svix-timestamp": headers.get("svix-timestamp", ""),
        "svix-signature": headers.get("svix-signature", ""),
    }

    try:
        return wh.verify(payload, svix_headers)
    except WebhookVerificationError as e:
        logger.warning("resend_webhook_verification_failed", error=str(e))
        raise
