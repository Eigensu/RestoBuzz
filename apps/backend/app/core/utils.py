from bson import ObjectId, errors
from app.core.errors import ValidationError


def to_object_id(id_str: str) -> ObjectId:
    """
    Safely convert a string to a BSON ObjectId.
    Raises a custom ValidationError (400 Bad Request) if the string is not valid.
    """
    try:
        if isinstance(id_str, ObjectId):
            return id_str
        return ObjectId(id_str)
    except errors.InvalidId:
        raise ValidationError(f"Invalid ID format: '{id_str}'")
