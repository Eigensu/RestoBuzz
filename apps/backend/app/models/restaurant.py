from pydantic import BaseModel


class RestaurantResponse(BaseModel):
    id: str
    name: str
    location: str
    emoji: str
    color: str  # tailwind bg color class
