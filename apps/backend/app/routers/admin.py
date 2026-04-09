from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from pydantic import BaseModel, EmailStr, Field

from app.core.errors import EmailAlreadyExistsError
from app.core.security import hash_password
from app.database import get_db
from app.dependencies import require_role
from app.models.user import UserResponse

router = APIRouter(prefix="/admin", tags=["admin"])


class CreateAdminRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_admin_user(
    body: Annotated[CreateAdminRequest, Body()],
    current_user: Annotated[dict, Depends(require_role("super_admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    existing = await db.users.find_one({"email": body.email})
    if existing:
        raise EmailAlreadyExistsError(f"User with email {body.email} already exists")

    now = datetime.now(timezone.utc)
    user_doc = {
        "email": body.email,
        "hashed_password": hash_password(body.password),
        "role": "admin",
        "first_name": body.first_name,
        "last_name": body.last_name,
        "phone": body.phone,
        "is_active": True,
        "created_at": now,
        "last_login": None,
        "created_by": str(current_user["_id"]),
    }

    try:
        result = await db.users.insert_one(user_doc)
    except DuplicateKeyError as exc:
        raise EmailAlreadyExistsError(f"User with email {body.email} already exists") from exc
    user_doc["_id"] = result.inserted_id

    return UserResponse(
        id=str(user_doc["_id"]),
        email=user_doc["email"],
        role=user_doc["role"],
        first_name=user_doc["first_name"],
        last_name=user_doc["last_name"],
        phone=user_doc["phone"],
        is_active=user_doc["is_active"],
        created_at=user_doc["created_at"],
    )


@router.get("/users", response_model=list[UserResponse])
async def list_admin_users(
    _current_user: Annotated[dict, Depends(require_role("super_admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    cursor = db.users.find(
        {"role": {"$in": ["super_admin", "admin"]}},
        {
            "_id": 1,
            "email": 1,
            "role": 1,
            "first_name": 1,
            "last_name": 1,
            "phone": 1,
            "is_active": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1)

    rows = [doc async for doc in cursor]
    return [
        UserResponse(
            id=str(doc["_id"]),
            email=doc["email"],
            role=doc["role"],
            first_name=doc.get("first_name"),
            last_name=doc.get("last_name"),
            phone=doc.get("phone"),
            is_active=doc.get("is_active", True),
            created_at=doc.get("created_at"),
        )
        for doc in rows
    ]


class UserAccessDetail(BaseModel):
    restaurant_name: str
    role: str


class UserAccessReport(BaseModel):
    user: UserResponse
    accesses: list[UserAccessDetail]


@router.get("/access-report", response_model=list[UserAccessReport])
async def get_access_report(
    _current_user: Annotated[dict, Depends(require_role("super_admin"))],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    # 1. Fetch all users
    users_cursor = db.users.find({})
    users = [doc async for doc in users_cursor]

    # 2. Fetch all roles/assignments
    roles_cursor = db.user_restaurant_roles.find({})
    all_roles = [doc async for doc in roles_cursor]

    # 3. Fetch all restaurants (to map names to roles)
    rest_cursor = db.restaurants.find({}, {"id": 1, "_id": 1, "name": 1})
    restaurants_map = {}
    async for doc in rest_cursor:
        name = doc.get("name", "Unknown Restaurant")
        # Map both Slug and Hex ID to the same Name
        if doc.get("id"):
            restaurants_map[str(doc["id"])] = name
        restaurants_map[str(doc["_id"])] = name

    report = []
    for user in users:
        user_id_str = str(user["_id"])
        user_accesses = []
        
        # Filter roles for this user
        for role in all_roles:
            if str(role["user_id"]) == user_id_str:
                rest_id = str(role["restaurant_id"])
                # Resolve name from map
                rest_name = restaurants_map.get(rest_id, f"Rest ID: {rest_id}")
                user_accesses.append(
                    UserAccessDetail(restaurant_name=rest_name, role=role["role"])
                )
        
        report.append(
            UserAccessReport(
                user=UserResponse(
                    id=user_id_str,
                    email=user["email"],
                    role=user.get("role", "viewer"),
                    first_name=user.get("first_name"),
                    last_name=user.get("last_name"),
                    phone=user.get("phone"),
                    is_active=user.get("is_active", True),
                    created_at=user.get("created_at") or datetime.now(timezone.utc),
                ),
                accesses=user_accesses
            )
        )
    
    return report

