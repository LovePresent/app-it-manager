from pydantic import BaseModel
from datetime import datetime


class RackBase(BaseModel):
    name: str
    location_id: int | None = None
    total_units: int = 42
    power_capacity: float | None = None
    description: str | None = None


class RackCreate(RackBase):
    pass


class RackUpdate(BaseModel):
    name: str | None = None
    location_id: int | None = None
    total_units: int | None = None
    power_capacity: float | None = None
    description: str | None = None


class RackResponse(RackBase):
    id: int
    location_name: str | None = None
    used_units: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class RackUnitBase(BaseModel):
    rack_id: int
    start_unit: int
    end_unit: int
    asset_id: int | None = None
    position: str = "front"
    notes: str | None = None


class RackUnitCreate(RackUnitBase):
    pass


class RackUnitUpdate(BaseModel):
    asset_id: int | None = None
    position: str | None = None
    notes: str | None = None


class RackUnitResponse(RackUnitBase):
    id: int
    asset_name: str | None = None
    asset_tag: str | None = None

    model_config = {"from_attributes": True}
