from pydantic import BaseModel, field_validator


class WaPhone(BaseModel):
    """WhatsApp configuration for a single phone number / WABA.

    phone_id and waba_id are non-sensitive IDs stored directly in MongoDB.
    The actual access token is never stored in the database — instead,
    access_token_env_key holds the name of the Railway/environment variable
    that contains the token (e.g. "META_PRIMARY_ACCESS_TOKEN").
    """

    phone_id: str  # Meta Phone Number ID
    access_token_env_key: str  # Name of the env var holding the access token
    waba_id: str = ""  # WhatsApp Business Account ID (for template management)
    label: str = "primary"  # Human-readable label, e.g. "primary", "backup"

    @field_validator("access_token_env_key")
    @classmethod
    def validate_env_key(cls, v: str) -> str:
        import re

        v = v.strip()
        if not v:
            raise ValueError("Env key cannot be empty")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v):
            raise ValueError(
                "Env key must be a valid environment variable name "
                "(letters, digits, underscores; cannot start with a digit)"
            )
        return v


class RestaurantResponse(BaseModel):
    id: str
    name: str
    location: str
    emoji: str
    color: str  # tailwind bg color class
    member_categories: list[str] = ["nfc", "ecard"]
    wa_phone_ids: list[str] = []
    wa_phones: list[WaPhone] = []


class UpdateCategoriesRequest(BaseModel):
    member_categories: list[str]


class UpdateWaPhonesRequest(BaseModel):
    wa_phones: list[WaPhone]
