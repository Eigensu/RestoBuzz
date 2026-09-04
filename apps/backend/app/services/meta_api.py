import httpx
import mimetypes
from urllib.parse import urlsplit
from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

META_BASE = f"https://graph.facebook.com/{settings.meta_api_version}"

# WhatsApp header media kinds and the file extensions that map to them. Used to
# build the correct header parameter ("image"/"video"/"document") since Meta
# rejects a send whose header parameter type doesn't match the template's
# declared header format.
_VIDEO_EXTS = (".mp4", ".3gp")
_DOC_EXTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt")


def _resolve_media_kind(media_url: str, media_type: str | None) -> str:
    """Return 'image' | 'video' | 'document' for a header media parameter.

    Prefers an explicit ``media_type`` (derived from the template's header
    format); otherwise infers from the URL's file extension, defaulting to
    "image" for backwards compatibility with image-only templates.
    """
    if media_type:
        mt = media_type.strip().lower()
        if mt in ("image", "video", "document"):
            return mt
    path = urlsplit(media_url).path.lower()
    if path.endswith(_VIDEO_EXTS):
        return "video"
    if path.endswith(_DOC_EXTS):
        return "document"
    return "image"


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
                    f"Non-JSON response from Meta (status {resp.status_code})",
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
    media_type: str | None = None,
) -> dict:
    components = []

    if media_url:
        kind = _resolve_media_kind(media_url, media_type)
        components.append(
            {
                "type": "header",
                "parameters": [{"type": kind, kind: {"link": media_url}}],
            }
        )

    if variables:
        # Sort variables by numeric key (1, 2, 3...) to ensure correct order for Meta API
        try:
            sorted_vars = sorted(variables.items(), key=lambda x: int(x[0]))
            body_params = [{"type": "text", "text": str(v)} for k, v in sorted_vars]
        except (ValueError, TypeError):
            # If keys aren't numeric, fall back to value order
            body_params = [{"type": "text", "text": str(v)} for v in variables.values()]
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
    phone_id: str | None = None,
    access_token: str | None = None,
    media_type: str | None = None,
) -> tuple[str, str]:
    """Returns (wa_message_id, endpoint_used).

    If `phone_id` and `access_token` are provided the message is sent through
    that restaurant-specific WABA exclusively — no fallback to the global chain.
    A failure surfaces immediately so the operator knows the credential is broken.

    If either credential is absent the legacy global primary → fallback chain
    from settings is used, preserving backwards-compatibility for restaurants
    that have not yet been configured.
    """
    if phone_id and access_token:
        # Restaurant-specific WABA — single endpoint, fail loudly on error
        endpoints = [(phone_id, access_token, "primary")]
    elif bool(phone_id) != bool(access_token):
        # Prevent cross-tenant leakage: if they provided a specific phone_id
        # but the token failed to resolve, or vice versa, fail loudly rather than 
        # falling back to the global (potentially wrong) account.
        raise MetaAPIError(
            "config_error",
            "Partial restaurant credentials provided (phone_id or access_token is missing or failed to resolve). Both must be present."
        )
    else:
        # Global fallback chain (legacy / unconfigured restaurants)
        endpoints = [
            (
                settings.meta_primary_phone_id,
                settings.meta_primary_access_token,
                "primary",
            ),
            (
                settings.meta_fallback_phone_id,
                settings.meta_fallback_access_token,
                "fallback",
            ),
        ]

    payload = _build_payload(
        to, template_name, variables, media_url, language, media_type
    )
    last_error = None

    async with httpx.AsyncClient(timeout=15.0) as client:
        for ep_phone_id, ep_token, label in endpoints:
            if not ep_phone_id or not ep_token:
                continue
            url = f"{META_BASE}/{ep_phone_id}/messages"
            headers = {"Authorization": f"Bearer {ep_token}"}
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
                    "meta_send_failed",
                    endpoint=label,
                    phone_id=ep_phone_id,
                    error=str(last_error),
                )
            except httpx.RequestError as e:
                last_error = MetaAPIError("network_error", str(e))
                logger.error("meta_network_error", endpoint=label, error=str(e))

    raise last_error or MetaAPIError("no_endpoint", "No valid WABA endpoint configured")


# Safety valve for the pagination loop below. 100 templates/page, so this caps
# a sync at 5000 templates — far beyond Meta's per-WABA limit.
MAX_TEMPLATE_PAGES = 50


async def fetch_templates(waba_id: str, token: str) -> list[dict]:
    """Fetch every message template on a WABA, following cursor pagination.

    `id` must be requested explicitly — it is what PATCH /templates keys off to
    edit a template on Meta.
    """
    url: str | None = f"{META_BASE}/{waba_id}/message_templates"
    # Only sent for the first page. Meta's `paging.next` already carries the
    # cursor in its query string, and httpx REPLACES a URL's query when
    # `params` is passed (it does not merge) — so re-sending params on later
    # pages strips the cursor and refetches page 1 forever.
    params: dict | None = {
        "limit": 100,
        "fields": "id,name,status,category,language,components",
    }
    headers = {"Authorization": f"Bearer {token}"}
    templates: list[dict] = []
    pages = 0

    async with httpx.AsyncClient(timeout=15.0) as client:
        while url and pages < MAX_TEMPLATE_PAGES:
            pages += 1
            try:
                resp = await client.get(
                    url, headers=headers, **({"params": params} if params else {})
                )
            except httpx.TimeoutException as e:
                raise MetaAPIError(
                    "timeout", f"Meta did not respond within 15s (page {pages})"
                ) from e
            except httpx.RequestError as e:
                raise MetaAPIError("network_error", str(e) or type(e).__name__) from e

            try:
                data = resp.json()
            except Exception as esc:
                raise MetaAPIError(
                    "invalid_response",
                    f"Non-JSON response from Meta (status {resp.status_code})",
                ) from esc

            if resp.status_code != 200:
                error = data.get("error", {})
                code = str(error.get("code", "unknown"))
                message = error.get("error_user_msg") or error.get(
                    "message", str(data)
                )
                logger.error(
                    "meta_fetch_templates_failed",
                    waba_id=waba_id,
                    status_code=resp.status_code,
                    code=code,
                    message=message,
                    page=pages,
                )
                raise MetaAPIError(code, message)
            page = data.get("data", [])
            if not page:
                # Meta keeps returning `paging.next` past the last page; an
                # empty page is the real terminator.
                break
            templates.extend(page)
            url = data.get("paging", {}).get("next")
            params = None

    if url and pages >= MAX_TEMPLATE_PAGES:
        logger.error(
            "meta_fetch_templates_page_limit_reached",
            waba_id=waba_id,
            pages=pages,
            fetched=len(templates),
        )
        # Both callers prune local templates against whatever this returns, so
        # handing back a partial list would delete valid templates. Hitting the
        # cap means pagination is misbehaving — fail the sync instead.
        raise MetaAPIError(
            "pagination_limit",
            f"Meta returned more than {MAX_TEMPLATE_PAGES} pages of templates; "
            "refusing to sync from a partial result",
        )

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
                logger.error(
                    "meta_api_error",
                    status_code=resp.status_code,
                    error=error,
                    payload=payload,
                )
                error_msg = error.get("error_user_msg") or error.get("message", str(data))
                raise MetaAPIError(
                    str(error.get("code", "unknown")), error_msg
                )
            return data
    except httpx.RequestError as e:
        raise MetaAPIError("network_error", str(e)) from e


# Per-format ceilings for template header media, keyed by the top-level content
# type. Meta caps image headers at 5 MB and video headers at 16 MB; documents it
# allows far more, but /media/upload never stores anything above 16 MB, so the
# same limit here keeps a pasted URL from streaming an unbounded file into
# memory. Keep in sync with cloudinary_service's MAX_*_BYTES.
MAX_MEDIA_BYTES_BY_TYPE = {
    "image": 5 * 1024 * 1024,         # 5 MB
    "video": 16 * 1024 * 1024,        # 16 MB
    "application": 16 * 1024 * 1024,  # 16 MB (PDF documents)
}
MAX_MEDIA_BYTES = 16 * 1024 * 1024  # fallback for unrecognised content types


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

                # MIME tokens are case-insensitive, so normalise before the
                # cap lookup — "IMAGE/PNG" would otherwise miss the image entry
                # and fall through to the widest ceiling.
                content_type = (
                    fetch_resp.headers.get("content-type", "application/octet-stream")
                    .split(";")[0]
                    .strip()
                    .lower()
                )
                max_bytes = MAX_MEDIA_BYTES_BY_TYPE.get(
                    content_type.split("/")[0], MAX_MEDIA_BYTES
                )

                content = b""
                async for chunk in fetch_resp.aiter_bytes():
                    content += chunk
                    if len(content) > max_bytes:
                        raise MetaAPIError(
                            "media_too_large",
                            f"{content_type} media exceeds the "
                            f"{max_bytes // (1024 * 1024)} MB limit",
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
                raise MetaAPIError(
                    "parse_error", "Failed to parse create upload session response"
                ) from esc

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
                raise MetaAPIError(
                    "parse_error", "Failed to parse upload session response"
                ) from esc

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
            except Exception as esc:
                raise MetaAPIError(
                    "invalid_response",
                    f"Non-JSON response from Meta (status {resp.status_code})",
                ) from esc
            if resp.status_code != 200:
                error = data.get("error", {})
                logger.error(
                    "meta_api_edit_error",
                    status_code=resp.status_code,
                    error=error,
                    template_id=template_id,
                    components=components,
                )
                error_msg = error.get("error_user_msg") or error.get("message", str(data))
                raise MetaAPIError(
                    str(error.get("code", "unknown")), error_msg
                )
            return data
    except httpx.RequestError as e:
        raise MetaAPIError("network_error", str(e)) from e


async def send_interactive_quick_reply(
    to: str,
    body_text: str,
    buttons: list[dict],
    phone_id: str,
    token: str,
    header_text: str | None = None,
    footer_text: str | None = None,
) -> str:
    """Send an interactive message with quick-reply buttons.

    Each button in `buttons` must be: {"id": "...", "title": "..."}
    Returns the wa_message_id on success.
    """
    interactive: dict = {
        "type": "button",
        "body": {"text": body_text},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"]}}
                for btn in buttons
            ]
        },
    }
    if header_text:
        interactive["header"] = {"type": "text", "text": header_text}
    if footer_text:
        interactive["footer"] = {"text": footer_text}

    url = f"{META_BASE}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    }
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        data = resp.json()
        if resp.status_code == 200:
            wa_id = data["messages"][0]["id"]
            logger.info("meta_interactive_sent", to=to, wa_id=wa_id)
            return wa_id
        error = data.get("error", {})
        raise MetaAPIError(str(error.get("code", "unknown")), error.get("message", ""))


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
