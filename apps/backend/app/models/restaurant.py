from pydantic import BaseModel


class RestaurantResponse(BaseModel):
    id: str
    name: str
    location: str
    emoji: str
    color: str  # tailwind bg color class
    member_categories: list[str] = ["nfc", "ecard"]


class UpdateCategoriesRequest(BaseModel):
    categories: list[str]
