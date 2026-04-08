import httpx
import mimetypes
from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

META_BASE = f"https://graph.facebook.com/{settings.meta_api_version}"


class MetaAPIError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


async def _resolve_app_id(token: str, configured_app_id: str | None = None) -> str:
    if configured_app_id:
        return configured_app_id

    url = f"{META_BASE}/debug_token"
    params = {"input_token": token, "access_token": token}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            try:
                data = resp.json()
            except Exception as esc:
                raise MetaAPIError(
                    "parse_error",
                    f"Non-JSON response from Meta (status {resp.status_code})"
                ) from esc
            if resp.status_code != 200:
                error = data.get("error", {})
                raise MetaAPIError(
                    str(error.get("code", "unknown")),
                    error.get("message", str(data)),
                )
    except httpx.RequestError as e:
        raise MetaAPIError("network_error", str(e)) from e

    app_id = data.get("data", {}).get("app_id")
    if not app_id:
        raise MetaAPIError(
            "config_error",
            "Unable to resolve META_APP_ID from token; set META_APP_ID explicitly",
        )
    return str(app_id)


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

    template_obj = {
        "name": template_name,
        "language": {"code": language},
    }
    if components:
        template_obj["components"] = components

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": template_obj,
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

    payload = _build_payload(to, template_name, variables, media_url, language)
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
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            try:
                data = resp.json()
            except Exception as esc:
                raise MetaAPIError(
                    "invalid_response",
                    f"Non-JSON response from Meta (status {resp.status_code})",
                ) from esc
            if resp.status_code not in (200, 201):
                error = data.get("error", {})
                raise MetaAPIError(
                    str(error.get("code", "unknown")), error.get("message", str(data))
                )
            return data
    except httpx.RequestError as e:
        raise MetaAPIError("network_error", str(e)) from e


MAX_MEDIA_BYTES = 10 * 1024 * 1024  # 10MB limit

async def create_media_handle_from_url(
    media_url: str,
    app_id: str,
    token: str,
) -> str:
    """Download media and create a template upload handle (header_handle) via Graph uploads."""
    app_id = await _resolve_app_id(token, app_id)

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async with client.stream("GET", media_url) as fetch_resp:
                if fetch_resp.status_code != 200:
                    raise MetaAPIError(
                        "media_fetch_failed",
                        f"Unable to fetch media from URL (status {fetch_resp.status_code})",
                    )

                content = b""
                async for chunk in fetch_resp.aiter_bytes():
                    content += chunk
                    if len(content) > MAX_MEDIA_BYTES:
                        raise MetaAPIError("media_too_large", f"Media exceeds limit of {MAX_MEDIA_BYTES} bytes")

                content_type = (
                    fetch_resp.headers.get("content-type", "application/octet-stream")
                    .split(";")[0]
                    .strip()
                )

            ext = mimetypes.guess_extension(content_type) or ".bin"
            filename = f"template_header{ext}"
            file_length = len(content)

            create_upload_url = f"{META_BASE}/{app_id}/uploads"
            headers = {"Authorization": f"Bearer {token}"}
            params = {
                "file_name": filename,
                "file_length": str(file_length),
                "file_type": content_type,
            }

            create_resp = await client.post(
                create_upload_url, headers=headers, params=params
            )
            try:
                create_data = create_resp.json()
            except Exception as esc:
                raise MetaAPIError("parse_error", "Failed to parse create upload session response") from esc

            if create_resp.status_code not in (200, 201):
                error = create_data.get("error", {})
                raise MetaAPIError(
                    str(error.get("code", "unknown")),
                    error.get("message", str(create_data)),
                )

            upload_session_id = create_data.get("id")
            if not upload_session_id:
                raise MetaAPIError(
                    "upload_session_failed",
                    "Upload session creation returned no id",
                )

            upload_data_url = f"{META_BASE}/{upload_session_id}"
            upload_headers = {
                "Authorization": f"Bearer {token}",
                "file_offset": "0",
                "Content-Type": "application/octet-stream",
            }
            upload_resp = await client.post(
                upload_data_url, headers=upload_headers, content=content
            )
            try:
                uploaded = upload_resp.json()
            except Exception as esc:
                raise MetaAPIError("parse_error", "Failed to parse upload session response") from esc

            if upload_resp.status_code not in (200, 201):
                error = uploaded.get("error", {})
                raise MetaAPIError(
                    str(error.get("code", "unknown")),
                    error.get("message", str(uploaded)),
                )

            handle = uploaded.get("h")
            if not handle:
                raise MetaAPIError(
                    "upload_handle_missing",
                    "Upload completed but response did not include handle",
                )

            return str(handle)
    except httpx.RequestError as e:
        raise MetaAPIError("network_error", str(e)) from e


async def edit_template(template_id: str, token: str, components: list) -> dict:
    """Edit an existing template's components (body text only for APPROVED templates).
    Meta allows 1 edit/day, max 10/month per template."""
    url = f"{META_BASE}/{template_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url, json={"components": components}, headers=headers
            )
            try:
                data = resp.json()
            except Exception:
                raise MetaAPIError(
                    "invalid_response",
                    f"Non-JSON response from Meta (status {resp.status_code})",
                )
            if resp.status_code != 200:
                error = data.get("error", {})
                raise MetaAPIError(
                    str(error.get("code", "unknown")), error.get("message", str(data))
                )
            return data
    except httpx.RequestError as e:
        raise MetaAPIError("network_error", str(e)) from e


async def send_text_message(to: str, body: str, phone_id: str, token: str) -> str:
    url = f"{META_BASE}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
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
