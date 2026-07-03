from typing import Annotated
from fastapi import APIRouter, Depends, Path, Body
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.database import get_db
from app.dependencies import (
    require_role,
    get_user_restaurant_ids,
    get_current_user,
    get_active_restaurant,
)
from app.models.user_restaurant import AssignUserRequest, UserRestaurantRole
from app.models.restaurant import (
    RestaurantResponse,
    UpdateCategoriesRequest,
    UpdateWaPhonesRequest,
)
from app.core.errors import NotFoundError, ValidationError
from app.core.utils import to_object_id

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


def _serialize_restaurant(doc: dict) -> RestaurantResponse:
    return RestaurantResponse(
        id=doc.get("id") or str(doc["_id"]),
        name=doc.get("name", ""),
        location=doc.get("location", ""),
        emoji=doc.get("emoji", "🏪"),
        color=doc.get("color", "gray"),
        member_categories=doc.get("member_categories")
        or doc.get("categories")
        or ["nfc", "ecard"],
        wa_phone_ids=doc.get("wa_phone_ids", []),
        wa_phones=doc.get("wa_phones", []),
        ecard_config=doc.get("ecard_config"),
    )


@router.get("")
async def list_restaurants(
    current_user: Annotated[dict, Depends(get_current_user)],
    allowed_ids: Annotated[set[str], Depends(get_user_restaurant_ids)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> list[RestaurantResponse]:
    """Returns only the restaurants the authenticated user has access to.
    super_admin gets all restaurants in the system."""
    if current_user.get("role") == "super_admin":
        query = {}
    else:
        object_ids = []
        for aid in allowed_ids:
            if ObjectId.is_valid(aid):
                object_ids.append(ObjectId(aid))

        query = (
            {"$or": [{"id": {"$in": list(allowed_ids)}}, {"_id": {"$in": object_ids}}]}
            if allowed_ids
            else {"id": None}
        )

    cursor = db.restaurants.find(query).sort("name", 1)
    return [_serialize_restaurant(doc) async for doc in cursor]


@router.post("/{restaurant_id}/assign", status_code=201)
async def assign_user(
    restaurant_id: Annotated[str, Path()],
    body: Annotated[AssignUserRequest, Body()],
    current_user: Annotated[dict, Depends(require_role("super_admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    """super_admin assigns a user to a restaurant with a given role."""
    restaurant = await db.restaurants.find_one({"id": restaurant_id})
    if not restaurant:
        raise NotFoundError(f"Restaurant '{restaurant_id}' not found")

    user_oid = to_object_id(body.user_id)
    target_user = await db.users.find_one({"_id": user_oid})
    if not target_user:
        raise NotFoundError(f"User '{body.user_id}' not found")

    await db.user_restaurant_roles.update_one(
        {"user_id": user_oid, "restaurant_id": restaurant_id},
        {"$set": {"role": body.role}},
        upsert=True,
    )
    return {
        "status": "assigned",
        "restaurant_id": restaurant_id,
        "user_id": body.user_id,
        "role": body.role,
    }


@router.delete("/{restaurant_id}/unassign/{user_id}")
async def unassign_user(
    restaurant_id: Annotated[str, Path()],
    user_id: Annotated[str, Path()],
    current_user: Annotated[dict, Depends(require_role("super_admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    """super_admin removes a user's access to a restaurant."""
    user_oid = to_object_id(user_id)
    result = await db.user_restaurant_roles.delete_one(
        {"user_id": user_oid, "restaurant_id": restaurant_id}
    )
    if result.deleted_count == 0:
        raise NotFoundError(
            f"No assignment found for user '{user_id}' at restaurant '{restaurant_id}'"
        )
    return {"status": "unassigned"}


@router.get("/{restaurant_id}/users")
async def list_restaurant_users(
    restaurant_id: Annotated[str, Path()],
    current_user: Annotated[dict, Depends(require_role("super_admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> list[UserRestaurantRole]:
    """super_admin lists all users assigned to a restaurant."""
    cursor = db.user_restaurant_roles.find({"restaurant_id": restaurant_id})
    return [
        UserRestaurantRole(
            user_id=str(doc["user_id"]),
            restaurant_id=doc["restaurant_id"],
            role=doc["role"],
        )
        async for doc in cursor
    ]


@router.put("/{restaurant_id}/categories")
async def update_categories(
    restaurant_id: Annotated[str, Path()],
    body: Annotated[UpdateCategoriesRequest, Body()],
    restaurant: Annotated[dict, Depends(get_active_restaurant)],
    _user: Annotated[dict, Depends(require_role("admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> RestaurantResponse:
    """Updates the member category list for a restaurant."""
    seen: set[str] = set()
    cleaned_categories: list[str] = []

    for cat in body.member_categories:
        normalised = cat.strip().lower()
        if normalised and normalised not in seen:
            seen.add(normalised)
            cleaned_categories.append(normalised)

    if not cleaned_categories:
        raise ValidationError("At least one category is required")

    rest_oid = restaurant["_id"]
    result = await db.restaurants.find_one_and_update(
        {"_id": rest_oid},
        {
            "$set": {"member_categories": cleaned_categories},
            "$unset": {"categories": ""},
        },
        return_document=True,
    )
    return _serialize_restaurant(result)


@router.put("/{restaurant_id}/phones")
async def update_wa_phones(
    restaurant_id: Annotated[str, Path()],
    body: Annotated[UpdateWaPhonesRequest, Body()],
    _user: Annotated[dict, Depends(require_role("super_admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> RestaurantResponse:
    """super_admin sets the WhatsApp WABA configuration for a restaurant.

    phone_id and waba_id are stored in MongoDB.
    access_token_env_key is the name of the Railway env var that holds the
    actual token — the token itself is never stored in the database.

    The first entry in wa_phones is used as the primary outbound number.
    wa_phone_ids is kept in sync automatically for inbound webhook routing.
    """
    cleaned_phones = []
    seen_phone_ids = set()
    new_phone_ids = []

    for entry in body.wa_phones:
        phone_id = entry.phone_id.strip()
        env_key = entry.access_token_env_key.strip()
        
        if not phone_id:
            raise ValidationError("Each wa_phone entry must have a non-empty phone_id")
        if not env_key:
            raise ValidationError("Each wa_phone entry must have a non-empty access_token_env_key")
            
        cleaned_entry = entry.model_dump()
        cleaned_entry["phone_id"] = phone_id
        cleaned_entry["access_token_env_key"] = env_key
        
        cleaned_phones.append(cleaned_entry)
        if phone_id not in seen_phone_ids:
            seen_phone_ids.add(phone_id)
            new_phone_ids.append(phone_id)

    query: dict = {"id": restaurant_id}
    if ObjectId.is_valid(restaurant_id):
        query = {"$or": [{"id": restaurant_id}, {"_id": ObjectId(restaurant_id)}]}

    result = await db.restaurants.find_one_and_update(
        query,
        {
            "$set": {
                "wa_phones": cleaned_phones,
                "wa_phone_ids": new_phone_ids,
            }
        },
        return_document=True,
    )
    if not result:
        raise NotFoundError(f"Restaurant '{restaurant_id}' not found")
    return _serialize_restaurant(result)
