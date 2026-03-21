from pydantic import BaseModel, EmailStr, Field
from typing import Literal
from datetime import datetime


Role = Literal["super_admin", "admin", "viewer"]


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: Role = "viewer"


class UserInDB(BaseModel):
    id: str
    email: EmailStr
    hashed_password: str
    role: Role
    is_active: bool = True
    created_at: datetime
    last_login: datetime | None = None


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    role: Role
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
