from pydantic import BaseModel
from datetime import datetime


class PaginationParams(BaseModel):
    page: int = 1
    size: int = 20


class PaginatedResponse(BaseModel):
    items: list = []
    total: int = 0
    page: int = 1
    size: int = 20
    pages: int = 0


class MessageResponse(BaseModel):
    message: str
    detail: str | None = None


class TimestampMixin(BaseModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
