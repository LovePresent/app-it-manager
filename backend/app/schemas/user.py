from pydantic import BaseModel, EmailStr
from datetime import datetime


class UserBase(BaseModel):
    email: str
    name: str
    department: str | None = None
    role: str = "user"


class UserCreate(UserBase):
    authentik_id: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    department: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserResponse(UserBase):
    id: int
    authentik_id: str | None = None
    is_active: bool = True
    avatar_url: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
