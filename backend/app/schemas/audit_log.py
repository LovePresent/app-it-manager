from pydantic import BaseModel
from datetime import datetime


class AuditLogResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    action: str
    changes: dict | None = None
    user_id: int | None = None
    user_name: str | None = None
    ip_address: str | None = None
    timestamp: datetime | None = None

    model_config = {"from_attributes": True}
