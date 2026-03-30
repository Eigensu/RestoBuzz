from pathlib import Path
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
    mongodb_url: str = "mongodb://localhost:27017/restobuzz"
    mongodb_db_name: str = "restobuzz"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret: str = "change_me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Meta Cloud API
    meta_api_version: str = "v25.0"
    meta_waba_id: str = ""
    meta_primary_phone_id: str = ""
    meta_primary_access_token: str = ""
    meta_fallback_phone_id: str = ""
    meta_fallback_access_token: str = ""
    meta_webhook_verify_token: str = "verify_token"
    meta_webhook_secret: str = ""

    # Cloudinary
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    # Celery
    celery_concurrency: int = 4
    rate_limit_mps: int = 80

    # CORS — comma-separated list of allowed origins
    # Do NOT include "*" in production; set this explicitly per environment
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
