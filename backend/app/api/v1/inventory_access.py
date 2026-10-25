from fastapi import Depends, HTTPException
from app.api.deps import get_current_user
from app.models.user import User


def require_inventory_editor(user: User = Depends(get_current_user)) -> User:
    if user.role not in {"admin", "manager"}:
        raise HTTPException(403, "장비 및 IP 대장 변경 권한이 없습니다.")
    return user
