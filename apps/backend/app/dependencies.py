from typing import Annotated
from fastapi import Depends, Header, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.database import get_db as _get_db
from app.core.security import decode_token
from app.core.rbac import check_role
from app.core.errors import (
    ForbiddenError,
    InvalidTokenError,
    UserNotFoundError,
    ValidationError,
)
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
    except ValueError as err:
        raise InvalidTokenError("Invalid or expired token") from err

    if payload.get("type") != "access":
        raise InvalidTokenError("Not an access token")

    try:
        user_id = to_object_id(payload["sub"])
    except ValidationError as err:
        raise InvalidTokenError("Invalid token subject") from err

    user = await db.users.find_one({"_id": user_id})
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
    # Bypass for super_admin: Return ALL unique identifiers for every restaurant in the collection
    if current_user.get("role") == "super_admin":
        cursor = db.restaurants.find({}, {"id": 1, "_id": 1})
        all_ids = set()
        async for doc in cursor:
            # We add BOTH the custom slug 'id' and the MongoDB stringified '_id'
            if doc.get("id"):
                all_ids.add(str(doc["id"]))
            all_ids.add(str(doc["_id"]))
        return all_ids

    # For regular users: Fetch assigned IDs from the user_restaurant_roles bridge table
    cursor = db.user_restaurant_roles.find(
        {"user_id": ObjectId(current_user["_id"])}, {"restaurant_id": 1, "_id": 0}
    )
    assigned_ids = {doc["restaurant_id"] async for doc in cursor}
    return assigned_ids


async def validate_restaurant_access(
    current_user: dict, restaurant_id: str, db: AsyncIOMotorDatabase
) -> str:
    """Helper to validate access. Raises ForbiddenError if denied.
    Returns the restaurant_id if access is granted.
    Standardized to check for assignments using either Slugs or ObjectIds."""
    # super_admin bypass
    if current_user.get("role") == "super_admin":
        return restaurant_id

    user_oid = ObjectId(current_user["_id"])
    
    # We check if the user is assigned via the provided restaurant_id string
    assignment = await db.user_restaurant_roles.find_one(
        {
            "user_id": user_oid,
            "restaurant_id": restaurant_id,
        }
    )
    
    if not assignment:
        # If not found directly, this could be a slug/hash mismatch.
        # However, the standard is to find assignments by the stored ID string.
        # If we still can't find it, we deny access.
        logger.warning(
            "restaurant_access_denied",
            user_id=str(user_oid),
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
async def get_active_restaurant(
    restaurant_id: str | None = None,
    x_restaurant_id: Annotated[str | None, Header(alias="X-Restaurant-ID")] = None,
    query_rid: Annotated[str | None, Query(alias="restaurant_id")] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """
    Unified dependency for restaurant-scoped operations.
    Supports fetching restaurant_id from:
    1. Path parameter (if named 'restaurant_id')
    2. Header ('X-Restaurant-ID')
    3. Query parameter ('restaurant_id')
    """
    target_rid = restaurant_id or x_restaurant_id or query_rid
    if not target_rid:
        raise ValidationError("restaurant_id is required (in path, X-Restaurant-ID header, or query string)")
    
    target_rid = str(target_rid)

    # Validate RBAC
    await validate_restaurant_access(current_user, target_rid, db)

    # Fetch Data
    rest_oid = ObjectId(target_rid) if ObjectId.is_valid(target_rid) else None

    restaurant = await db.restaurants.find_one(
        {"$or": [{"id": target_rid}, {"_id": rest_oid}]}
    )

    if not restaurant:
        logger.error("restaurant_not_found", restaurant_id=restaurant_id)
        raise ValidationError(f"Restaurant '{restaurant_id}' not found")

    # Standardize ID field for downstream route logic
    restaurant["id"] = str(restaurant.get("id") or restaurant["_id"])

    # Bulletproof Read: Handle field renaming migration
    # 1. Primary: member_categories (the new standard)
    # 2. Secondary: categories (the legacy field)
    # 3. Fallback: ["nfc", "ecard"] (system default)
    if not restaurant.get("member_categories"):
        restaurant["member_categories"] = restaurant.get("categories") or ["nfc", "ecard"]

    return restaurant
