from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    PROJECT_NAME: str = "IT Asset Manager"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./data/itam.db"

    # Authentik OIDC
    AUTHENTIK_BASE_URL: str = "https://auth.example.com"
    AUTHENTIK_CLIENT_ID: str = ""
    AUTHENTIK_CLIENT_SECRET: str = ""
    AUTHENTIK_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/callback"
    AUTHENTIK_JWKS_URL: str = ""
    AUTHENTIK_TOKEN_URL: str = ""
    AUTHENTIK_AUTHORIZE_URL: str = ""
    AUTHENTIK_USERINFO_URL: str = ""

    # App
    SECRET_KEY: str = "change-me-in-production"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:80"]
    QR_BASE_URL: str = "http://localhost:80"
    ASSET_TAG_PREFIX: str = "IT"

    @property
    def oidc_discovery_url(self) -> str:
        return f"{self.AUTHENTIK_BASE_URL}/application/o/.well-known/openid-configuration"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
