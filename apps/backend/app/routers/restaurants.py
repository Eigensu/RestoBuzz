from fastapi import APIRouter, Depends
from bson import ObjectId
from app.database import get_db
from app.dependencies import require_role, get_user_restaurant_ids
from app.models.restaurant import RestaurantResponse
from app.models.user_restaurant import AssignUserRequest, UserRestaurantRole
from app.core.errors import NotFoundError, ValidationError
from app.core.utils import to_object_id

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


@router.get("", response_model=list[RestaurantResponse])
@router.get("/", response_model=list[RestaurantResponse])
async def list_restaurants(
    allowed_ids: set[str] = Depends(get_user_restaurant_ids),
    db=Depends(get_db),
):
    """Returns only the restaurants the authenticated user has access to.
    super_admin gets all restaurants."""
    query = {"id": {"$in": list(allowed_ids)}} if allowed_ids else {"id": None}
    cursor = db.restaurants.find(query).sort("name", 1)
    return [
        RestaurantResponse(
            id=doc.get("id") or str(doc["_id"]),
            name=doc.get("name", ""),
            location=doc.get("location", ""),
            emoji=doc.get("emoji", "🏪"),
            color=doc.get("color", "gray"),
        )
        async for doc in cursor
    ]


@router.post("/{restaurant_id}/assign", status_code=201)
async def assign_user(
    restaurant_id: str,
    body: AssignUserRequest,
    current_user: dict = Depends(require_role("super_admin")),
    db=Depends(get_db),
):
    """super_admin assigns a user to a restaurant with a given role."""
    # Check restaurant exists
    restaurant = await db.restaurants.find_one({"id": restaurant_id})
    if not restaurant:
        raise NotFoundError(f"Restaurant '{restaurant_id}' not found")

    # Check user exists
    user_oid = to_object_id(body.user_id)
    target_user = await db.users.find_one({"_id": user_oid})
    if not target_user:
        raise NotFoundError(f"User '{body.user_id}' not found")

    await db.user_restaurant_roles.update_one(
        {"user_id": user_oid, "restaurant_id": restaurant_id},
        {"$set": {"role": body.role}},
        upsert=True,
    )
    return {"status": "assigned", "restaurant_id": restaurant_id, "user_id": body.user_id, "role": body.role}


@router.delete("/{restaurant_id}/unassign/{user_id}")
async def unassign_user(
    restaurant_id: str,
    user_id: str,
    current_user: dict = Depends(require_role("super_admin")),
    db=Depends(get_db),
):
    """super_admin removes a user's access to a restaurant."""
    user_oid = to_object_id(user_id)
    result = await db.user_restaurant_roles.delete_one(
        {"user_id": user_oid, "restaurant_id": restaurant_id}
    )
    if result.deleted_count == 0:
        raise NotFoundError(f"No assignment found for user '{user_id}' at restaurant '{restaurant_id}'")
    return {"status": "unassigned"}


@router.get("/{restaurant_id}/users", response_model=list[UserRestaurantRole])
async def list_restaurant_users(
    restaurant_id: str,
    current_user: dict = Depends(require_role("super_admin")),
    db=Depends(get_db),
):
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
