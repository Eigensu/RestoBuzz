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
        v = v.strip()
        if " " in v:
            raise ValueError("Env key cannot contain spaces")
        if not v.startswith("META_") and not v.startswith("WHATSAPP_TOKEN_"):
            raise ValueError("Env key must start with META_ or WHATSAPP_TOKEN_")
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
