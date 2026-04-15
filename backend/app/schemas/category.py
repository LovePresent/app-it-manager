from pydantic import BaseModel
from datetime import datetime


class CategoryBase(BaseModel):
    name: str
    slug: str
    icon: str | None = None
    description: str | None = None
    custom_field_schema: list | None = None
    sort_order: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    description: str | None = None
    custom_field_schema: list | None = None
    sort_order: int | None = None


class CategoryResponse(CategoryBase):
    id: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
