import httpx
from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

META_BASE = f"https://graph.facebook.com/{settings.meta_api_version}"


class MetaAPIError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def _build_payload(
    to: str,
    template_name: str,
    variables: dict,
    media_url: str | None,
    language: str = "en",
) -> dict:
    components = []

    if media_url:
        components.append(
            {
                "type": "header",
                "parameters": [{"type": "image", "image": {"link": media_url}}],
            }
        )

    if variables:
        body_params = [{"type": "text", "text": v} for v in variables.values()]
        components.append({"type": "body", "parameters": body_params})

    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": components,
        },
    }


async def send_template_message(
    to: str,
    template_name: str,
    variables: dict,
    media_url: str | None = None,
    language: str = "en",
) -> tuple[str, str]:
    """Returns (wa_message_id, endpoint_used). Tries primary then fallback."""
    endpoints = [
        (settings.meta_primary_phone_id, settings.meta_primary_access_token, "primary"),
        (
            settings.meta_fallback_phone_id,
            settings.meta_fallback_access_token,
            "fallback",
        ),
    ]

    payload = _build_payload(to, template_name, variables, media_url)
    last_error = None

    async with httpx.AsyncClient(timeout=15.0) as client:
        for phone_id, token, label in endpoints:
            if not phone_id or not token:
                continue
            url = f"{META_BASE}/{phone_id}/messages"
            headers = {"Authorization": f"Bearer {token}"}
            try:
                resp = await client.post(url, json=payload, headers=headers)
                data = resp.json()
                if resp.status_code == 200:
                    wa_id = data["messages"][0]["id"]
                    logger.info("meta_send_success", to=to, endpoint=label, wa_id=wa_id)
                    return wa_id, label
                error = data.get("error", {})
                last_error = MetaAPIError(
                    str(error.get("code", "unknown")),
                    error.get("message", "Unknown error"),
                )
                logger.warning(
                    "meta_send_failed", endpoint=label, error=str(last_error)
                )
            except httpx.RequestError as e:
                last_error = MetaAPIError("network_error", str(e))
                logger.error("meta_network_error", endpoint=label, error=str(e))

    raise last_error or MetaAPIError("no_endpoint", "No valid WABA endpoint configured")


async def fetch_templates(waba_id: str, token: str) -> list[dict]:
    url = f"{META_BASE}/{waba_id}/message_templates"
    params = {"limit": 100, "fields": "name,status,category,language,components"}
    headers = {"Authorization": f"Bearer {token}"}
    templates = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        while url:
            resp = await client.get(url, params=params, headers=headers)
            data = resp.json()
            if resp.status_code != 200:
                error = data.get("error", {})
                raise MetaAPIError(
                    str(error.get("code", "unknown")), error.get("message", str(data))
                )
            templates.extend(data.get("data", []))
            url = data.get("paging", {}).get("next")
            params = {}

    return templates


async def create_template(waba_id: str, token: str, payload: dict) -> dict:
    """Create a new message template via the Business Management API.
    Returns the created template dict (includes id, name, status)."""
    url = f"{META_BASE}/{waba_id}/message_templates"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        data = resp.json()
        if resp.status_code not in (200, 201):
            error = data.get("error", {})
            raise MetaAPIError(
                str(error.get("code", "unknown")), error.get("message", str(data))
            )
        return data


async def edit_template(template_id: str, token: str, components: list) -> dict:
    """Edit an existing template's components (body text only for APPROVED templates).
    Meta allows 1 edit/day, max 10/month per template."""
    url = f"{META_BASE}/{template_id}"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json={"components": components}, headers=headers)
        data = resp.json()
        if resp.status_code != 200:
            error = data.get("error", {})
            raise MetaAPIError(
                str(error.get("code", "unknown")), error.get("message", str(data))
            )
        return data


async def send_text_message(to: str, body: str, phone_id: str, token: str) -> str:
    url = f"{META_BASE}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        data = resp.json()
        if resp.status_code == 200:
            return data["messages"][0]["id"]
        error = data.get("error", {})
        raise MetaAPIError(str(error.get("code", "unknown")), error.get("message", ""))
