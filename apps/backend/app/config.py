from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Prefer the nearest existing .env while developing locally.
# In containers, .env may not exist and that's fine because Railway injects env vars.
_CONFIG_PATH = Path(__file__).resolve()
_ROOT_ENV = next(
    (parent / ".env" for parent in _CONFIG_PATH.parents if (parent / ".env").exists()),
    _CONFIG_PATH.parents[min(3, len(_CONFIG_PATH.parents) - 1)] / ".env",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MongoDB
    # Prioritizes MONGODB_URL_PROD if present in .env, otherwise falls back to MONGODB_URL
    mongodb_url: str = Field(
        default="mongodb://localhost:27017/dishpatch",
        validation_alias=AliasChoices("MONGODB_URL_PROD", "MONGODB_URL"),
    )
    mongodb_db_name: str = (
        "restobuzz"  # leave blank to derive from URL path, or set a default
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret: str = "change_me"  # NOSONAR
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Meta Cloud API
    meta_api_version: str = "v25.0"
    meta_app_id: str = ""
    meta_waba_id: str = ""
    meta_primary_phone_id: str = ""
    meta_primary_access_token: str = ""
    meta_fallback_phone_id: str = ""
    meta_fallback_access_token: str = ""
    meta_webhook_verify_token: str = "verify_token"  # NOSONAR
    meta_webhook_secret: str = ""

    # Cloudinary
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    # Resend (Email)
    resend_api_key: str = Field(
        default="", validation_alias=AliasChoices("RESEND_API_KEY")
    )
    resend_webhook_secret: str = Field(
        default="", validation_alias=AliasChoices("RESEND_WEBHOOK_SECRET")
    )
    resend_from_email: str = Field(
        default="RestoBuzz <noreply@restobuzz.com>",
        validation_alias=AliasChoices("RESEND_FROM_EMAIL"),
    )
    resend_rate_limit: int = 5  # Resend default: 5 req/s

    # Celery
    celery_concurrency: int = 4
    rate_limit_mps: int = 80

    # CORS — comma-separated list of allowed origins
    # Do NOT include "*" in production; set this explicitly per environment
    cors_origins: str = "http://localhost:3000"

    # Seed Data (Optional, used by init_db.py)
    admin_email: str = "admin@example.com"
    admin_password: str = ""
    reset_password: bool = False

    # WhatsApp quick-reply auto-response
    # The link sent automatically when a user taps the "Get the benefits" button
    benefits_link: str = Field(
        default="", validation_alias=AliasChoices("BENEFITS_LINK")
    )

    # ReserveGo upload portal credentials
    reservego_user: str = ""
    reservego_password: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
