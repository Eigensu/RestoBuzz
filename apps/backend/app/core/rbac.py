from functools import wraps
from fastapi import HTTPException, status

ROLE_HIERARCHY = {"viewer": 0, "admin": 1, "super_admin": 2}


def require_role(minimum_role: str):
    """Dependency factory — use as: Depends(require_role('admin'))"""
    def dependency(current_user=None):
        # current_user injected via get_current_user dependency in routes
        pass
    return dependency


def check_role(user_role: str, minimum_role: str) -> None:
    if ROLE_HIERARCHY.get(user_role, -1) < ROLE_HIERARCHY.get(minimum_role, 99):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires '{minimum_role}' role or higher",
        )
