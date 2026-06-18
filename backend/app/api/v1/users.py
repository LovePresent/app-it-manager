from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter()


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "display_name": user.name,
        "role": user.role,
        "is_admin": user.role == "admin",
        "is_active": user.is_active,
        "department": user.department,
        "avatar_url": user.avatar_url,
    }


@router.get("/users", response_model=dict)
def list_users(
    roles: str | None = Query(None, description="Comma-separated role list"),
    active: bool | None = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(User)
    if active is not None:
        query = query.filter(User.is_active.is_(active))
    if roles:
        role_values = [item.strip() for item in roles.split(",") if item.strip()]
        if role_values:
            query = query.filter(User.role.in_(role_values))
    items = query.order_by(User.name.asc(), User.email.asc()).all()
    return {"items": [_serialize_user(item) for item in items], "total": len(items)}
