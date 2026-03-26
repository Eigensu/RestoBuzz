from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from bson import ObjectId
from app.database import get_db
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.errors import (
    InvalidCredentialsError,
    AccountDisabledError,
    InvalidTokenError,
    UserNotFoundError,
)
from app.models.user import (
    LoginRequest,
    TokenPair,
    RefreshRequest,
    UserResponse,
)
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, db=Depends(get_db)):
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
async def refresh(body: RefreshRequest, db=Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
    except ValueError as exc:
        raise InvalidTokenError("Invalid refresh token") from exc
    if payload.get("type") != "refresh":
        raise InvalidTokenError("Not a refresh token")

    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise UserNotFoundError("User not found")

    uid = str(user["_id"])
    return TokenPair(
        access_token=create_access_token(uid, user["role"]),
        refresh_token=create_refresh_token(uid),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user["_id"]),
        email=current_user["email"],
        role=current_user["role"],
        is_active=current_user["is_active"],
        created_at=current_user["created_at"],
    )
