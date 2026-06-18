from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User

router = APIRouter()

ALLOWED_LOCAL_ROLES = {"admin", "manager", "user"}


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


def _get_or_create_local_user(db: Session) -> User:
    email = settings.LOCAL_LOGIN_EMAIL.strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LOCAL_LOGIN_EMAIL is not configured",
        )

    role = settings.LOCAL_LOGIN_ROLE if settings.LOCAL_LOGIN_ROLE in ALLOWED_LOCAL_ROLES else "admin"
    local_subject = f"local:{email}"
    user = db.query(User).filter(User.email == email).first()

    if user:
        user.authentik_id = local_subject
        user.name = settings.LOCAL_LOGIN_NAME
        user.department = settings.LOCAL_LOGIN_DEPARTMENT or user.department
        user.role = role
        user.is_active = True
    else:
        user = User(
            authentik_id=local_subject,
            email=email,
            name=settings.LOCAL_LOGIN_NAME,
            department=settings.LOCAL_LOGIN_DEPARTMENT,
            role=role,
            is_active=True,
        )
        db.add(user)

    db.commit()
    db.refresh(user)
    return user


@router.post("/auth/local-login")
def local_login(db: Session = Depends(get_db)):
    if not settings.LOCAL_LOGIN_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local login is disabled")

    user = _get_or_create_local_user(db)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=settings.LOCAL_LOGIN_TOKEN_HOURS)
    token = jwt.encode(
        {
            "iss": settings.LOCAL_LOGIN_TOKEN_ISSUER,
            "sub": user.authentik_id,
            "email": user.email,
            "name": user.name,
            "preferred_username": user.email,
            "local": True,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "user": _serialize_user(user),
    }
