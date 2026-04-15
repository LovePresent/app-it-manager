from pydantic import BaseModel
from datetime import date, datetime


class MaintenanceBase(BaseModel):
    asset_id: int
    maintenance_type: str  # preventive, corrective, upgrade
    description: str | None = None
    cost: float | None = None
    scheduled_date: date | None = None
    completed_date: date | None = None
    vendor_id: int | None = None
    technician: str | None = None
    status: str = "scheduled"
    notes: str | None = None


class MaintenanceCreate(MaintenanceBase):
    pass


class MaintenanceUpdate(BaseModel):
    maintenance_type: str | None = None
    description: str | None = None
    cost: float | None = None
    scheduled_date: date | None = None
    completed_date: date | None = None
    vendor_id: int | None = None
    technician: str | None = None
    status: str | None = None
    notes: str | None = None


class MaintenanceResponse(MaintenanceBase):
    id: int
    asset_name: str | None = None
    asset_tag: str | None = None
    vendor_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
