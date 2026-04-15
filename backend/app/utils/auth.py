import httpx
from jose import jwt, JWTError
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User


_jwks_cache: dict | None = None


async def get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache:
        return _jwks_cache

    jwks_url = settings.AUTHENTIK_JWKS_URL
    if not jwks_url:
        # Discover from OIDC config
        async with httpx.AsyncClient() as client:
            resp = await client.get(settings.oidc_discovery_url)
            oidc_config = resp.json()
            jwks_url = oidc_config["jwks_uri"]

    async with httpx.AsyncClient() as client:
        resp = await client.get(jwks_url)
        _jwks_cache = resp.json()
    return _jwks_cache


async def verify_token(token: str) -> dict:
    try:
        jwks = await get_jwks()
        unverified_header = jwt.get_unverified_header(token)
        key = None
        for k in jwks.get("keys", []):
            if k["kid"] == unverified_header.get("kid"):
                key = k
                break
        if not key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token key")

        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.AUTHENTIK_CLIENT_ID,
            options={"verify_aud": bool(settings.AUTHENTIK_CLIENT_ID)},
        )
        return payload
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token validation failed: {e}")


def get_or_create_user(db: Session, token_payload: dict) -> User:
    sub = token_payload.get("sub", "")
    email = token_payload.get("email", "")
    name = token_payload.get("name") or token_payload.get("preferred_username", "")

    user = db.query(User).filter(User.authentik_id == sub).first()
    if not user and email:
        user = db.query(User).filter(User.email == email).first()

    if user:
        user.authentik_id = sub
        if name:
            user.name = name
        db.commit()
        db.refresh(user)
        return user

    user = User(
        authentik_id=sub,
        email=email or f"{sub}@authentik",
        name=name or "Unknown",
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
