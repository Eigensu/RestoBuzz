from pydantic import BaseModel


class RestaurantResponse(BaseModel):
    id: str
    name: str
    location: str
    emoji: str
    color: str  # tailwind bg color class
    member_categories: list[str] = ["nfc", "ecard"]
    wa_phone_ids: list[str] = []


class UpdateCategoriesRequest(BaseModel):
    member_categories: list[str]
