from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.database import get_db as _get_db
from app.core.security import decode_token
from app.core.rbac import check_role
from app.core.errors import ForbiddenError, InvalidTokenError, UserNotFoundError
from app.core.utils import to_object_id
from app.core.logging import get_logger

bearer = HTTPBearer()
logger = get_logger(__name__)


def get_db() -> AsyncIOMotorDatabase:
    return _get_db()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise InvalidTokenError("Invalid or expired token")

    if payload.get("type") != "access":
        raise InvalidTokenError("Not an access token")

    user = await db.users.find_one({"_id": to_object_id(payload["sub"])})
    if not user or not user.get("is_active"):
        raise UserNotFoundError("User not found or inactive")

    user["id"] = str(user["_id"])
    return user


def require_role(minimum_role: str):
    async def dependency(current_user: dict = Depends(get_current_user)):
        check_role(current_user["role"], minimum_role)
        return current_user

    return dependency


async def get_user_restaurant_ids(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> set[str]:
    # Bypass for super_admin role ONLY
    if current_user.get("role") == "super_admin":
        cursor = db.restaurants.find({})
        ids = {str(doc["id"]) async for doc in cursor if "id" in doc}
        return ids

    cursor = db.user_restaurant_roles.find(
        {"user_id": ObjectId(current_user["_id"])}, {"restaurant_id": 1, "_id": 0}
    )
    ids = {doc["restaurant_id"] async for doc in cursor}
    return ids


async def validate_restaurant_access(
    current_user: dict, restaurant_id: str, db: AsyncIOMotorDatabase
) -> str:
    """Helper to validate access. Raises ForbiddenError if denied.
    Returns the restaurant_id if access is granted."""
    # super_admin bypass
    if current_user.get("role") == "super_admin":
        return restaurant_id

    assignment = await db.user_restaurant_roles.find_one(
        {
            "user_id": ObjectId(current_user["_id"]),
            "restaurant_id": restaurant_id,
        }
    )
    if not assignment:
        logger.warning(
            "restaurant_access_denied",
            user_id=str(current_user["_id"]),
            restaurant_id=restaurant_id
        )
        raise ForbiddenError(f"Access denied to restaurant '{restaurant_id}'")
    return restaurant_id


def require_restaurant_access():
    """Dependency factory. Use as: Depends(require_restaurant_access())
    Validates that the current user has access to the restaurant_id in the request.
    Returns the validated restaurant_id string on success."""

    async def dependency(
        restaurant_id: str,
        current_user: dict = Depends(get_current_user),
        db: AsyncIOMotorDatabase = Depends(get_db),
    ) -> str:
        return await validate_restaurant_access(current_user, restaurant_id, db)

    return dependency
