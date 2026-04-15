from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
import httpx

from app.config import settings

router = APIRouter()


@router.get("/auth/login")
def login():
    authorize_url = settings.AUTHENTIK_AUTHORIZE_URL
    if not authorize_url:
        authorize_url = f"{settings.AUTHENTIK_BASE_URL}/application/o/authorize/"
    params = {
        "client_id": settings.AUTHENTIK_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.AUTHENTIK_REDIRECT_URI,
        "scope": "openid profile email",
    }
    url = f"{authorize_url}?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url)


@router.get("/auth/callback")
async def callback(code: str, request: Request):
    token_url = settings.AUTHENTIK_TOKEN_URL
    if not token_url:
        token_url = f"{settings.AUTHENTIK_BASE_URL}/application/o/token/"

    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.AUTHENTIK_REDIRECT_URI,
            "client_id": settings.AUTHENTIK_CLIENT_ID,
            "client_secret": settings.AUTHENTIK_CLIENT_SECRET,
        })
    tokens = resp.json()

    # Redirect to frontend with token
    frontend_url = settings.FRONTEND_URL
    access_token = tokens.get("access_token", "")
    return RedirectResponse(f"{frontend_url}/auth/callback?token={access_token}")


@router.get("/auth/me")
async def me(request: Request):
    from app.api.deps import get_current_user
    from app.database import get_db
    from fastapi.security import HTTPAuthorizationCredentials

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return {"error": "Not authenticated"}

    token = auth_header.split(" ")[1]
    db = next(get_db())
    try:
        from app.utils.auth import verify_token, get_or_create_user
        payload = await verify_token(token)
        user = get_or_create_user(db, payload)
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "department": user.department,
            "avatar_url": user.avatar_url,
        }
    finally:
        db.close()
