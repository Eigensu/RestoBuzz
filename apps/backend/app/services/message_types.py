from app.models.inbox import MessageType


_SUPPORTED_MESSAGE_TYPES: set[str] = {
    "text",
    "image",
    "document",
    "location",
    "sticker",
}


def normalize_message_type(raw_type: str | None) -> MessageType:
    if raw_type in _SUPPORTED_MESSAGE_TYPES:
        return raw_type  # type: ignore[return-value]
    return "unknown"