from pydantic import BaseModel
from typing import Literal

RestaurantRole = Literal["admin", "viewer"]


class UserRestaurantRole(BaseModel):
    user_id: str
    restaurant_id: str
    role: RestaurantRole


class AssignUserRequest(BaseModel):
    user_id: str
    role: RestaurantRole = "viewer"
