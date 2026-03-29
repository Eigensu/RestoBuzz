from app.core.errors import InsufficientRoleError

ROLE_HIERARCHY = {"viewer": 0, "admin": 1, "super_admin": 2}


def check_role(user_role: str, minimum_role: str) -> None:
    if ROLE_HIERARCHY.get(user_role, -1) < ROLE_HIERARCHY.get(minimum_role, 99):
        raise InsufficientRoleError(f"Requires '{minimum_role}' role or higher")
