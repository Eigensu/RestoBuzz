from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyUrl


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MongoDB
    mongodb_url: str = "mongodb://localhost:27017/whatsapp_bulk"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret: str = "change_me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Meta Cloud API
    meta_api_version: str = "v21.0"
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


settings = Settings()
