from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, Body
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.core.utils import to_object_id
from app.database import get_db
from app.core.security import (
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.errors import (
    InvalidCredentialsError,
    AccountDisabledError,
    InvalidTokenError,
    UserNotFoundError,
    EmailAlreadyExistsError,
)
from app.models.user import (
    LoginRequest,
    RegisterRequest,
    TokenPair,
    RefreshRequest,
    UserResponse,
)
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    body: Annotated[RegisterRequest, Body()],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)]
):
    # Check if user already exists
    existing = await db.users.find_one({"email": body.email})
    if existing:
        raise EmailAlreadyExistsError(f"User with email {body.email} already exists")

    now = datetime.now(timezone.utc)
    user_doc = {
        "email": body.email,
        "hashed_password": hash_password(body.password),
        "role": "viewer",
        "first_name": body.firstName,
        "last_name": body.lastName,
        "phone": body.phone,
        "is_active": True,
        "created_at": now,
        "last_login": None,
    }

    result = await db.users.insert_one(user_doc)
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


@router.post("/login", response_model=TokenPair)
async def login(
    body: Annotated[LoginRequest, Body()],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)]
):
    user = await db.users.find_one({"email": body.email})
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise InvalidCredentialsError("Invalid email or password")
    if not user.get("is_active"):
        raise AccountDisabledError("This account has been disabled")

    await db.users.update_one(
        {"_id": user["_id"]}, {"$set": {"last_login": datetime.now(timezone.utc)}}
    )
    uid = str(user["_id"])
    return TokenPair(
        access_token=create_access_token(uid, user["role"]),
        refresh_token=create_refresh_token(uid),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: Annotated[RefreshRequest, Body()],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)]
):
    try:
        payload = decode_token(body.refresh_token)
    except ValueError as exc:
        raise InvalidTokenError("Invalid refresh token") from exc
    if payload.get("type") != "refresh":
        raise InvalidTokenError("Not a refresh token")

    user = await db.users.find_one({"_id": to_object_id(payload["sub"])})
    if not user:
        raise UserNotFoundError("User not found")

    uid = str(user["_id"])
    return TokenPair(
        access_token=create_access_token(uid, user["role"]),
        refresh_token=create_refresh_token(uid),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: Annotated[dict, Depends(get_current_user)]):
    return UserResponse(
        id=str(current_user["_id"]),
        email=current_user["email"],
        role=current_user["role"],
        is_active=current_user["is_active"],
        created_at=current_user["created_at"],
    )
