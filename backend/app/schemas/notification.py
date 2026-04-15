from pydantic import BaseModel
from datetime import date, datetime


class NotificationResponse(BaseModel):
    id: int
    type: str
    entity_type: str | None = None
    entity_id: int | None = None
    title: str
    message: str | None = None
    due_date: date | None = None
    is_read: bool = False
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class NotificationMarkRead(BaseModel):
    ids: list[int]
