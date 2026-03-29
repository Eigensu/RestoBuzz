"""
Centralised application error classes.

Raise these instead of bare HTTPException so error types are consistent
and the global handler can serialise them uniformly.

Each class only defines status_code and error_type — the message is always
provided at the call site.

Example:
    raise InvalidCredentialsError("The email or password you entered is incorrect")
    raise CampaignNotFoundError(f"Campaign {campaign_id} does not exist")
"""

from fastapi import status


class AppError(Exception):
    """Base application error."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type: str = "server_error"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

    def to_dict(self) -> dict:
        return {"detail": self.message, "type": self.error_type}


# ── 400 Bad Request ────────────────────────────────────────────────────────────


class ValidationError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "validation_error"


class ContactFileExpiredError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "contact_file_expired"


class InvalidFileFormatError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "invalid_file_format"


# ── 401 Unauthorized ───────────────────────────────────────────────────────────


class AuthError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_type = "auth_error"


class InvalidCredentialsError(AuthError):
    error_type = "invalid_credentials"


class InvalidTokenError(AuthError):
    error_type = "invalid_token"


class TokenExpiredError(AuthError):
    error_type = "token_expired"


# ── 403 Forbidden ──────────────────────────────────────────────────────────────


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    error_type = "permission_error"


class AccountDisabledError(ForbiddenError):
    error_type = "account_disabled"


class InsufficientRoleError(ForbiddenError):
    error_type = "insufficient_role"


class WebhookSignatureError(ForbiddenError):
    error_type = "webhook_signature_invalid"


# ── 404 Not Found ──────────────────────────────────────────────────────────────


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "not_found"


class CampaignNotFoundError(NotFoundError):
    error_type = "campaign_not_found"


class UserNotFoundError(NotFoundError):
    error_type = "user_not_found"


class TemplateNotFoundError(NotFoundError):
    error_type = "template_not_found"


# ── 409 Conflict ───────────────────────────────────────────────────────────────


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    error_type = "conflict"


class EmailAlreadyExistsError(ConflictError):
    error_type = "email_already_exists"


# ── 500 / 503 Server Errors ────────────────────────────────────────────────────


class ServerError(AppError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type = "server_error"


class RedisError(ServerError):
    error_type = "redis_error"


class WhatsAppAPIError(ServerError):
    error_type = "whatsapp_api_error"
