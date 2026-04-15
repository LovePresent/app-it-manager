from pydantic import BaseModel
from datetime import datetime


class NetworkPortBase(BaseModel):
    panel_name: str
    port_number: str
    connected_asset_id: int | None = None
    cable_type: str | None = None
    vlan: str | None = None
    status: str = "available"
    location_id: int | None = None
    notes: str | None = None


class NetworkPortCreate(NetworkPortBase):
    pass


class NetworkPortUpdate(BaseModel):
    panel_name: str | None = None
    port_number: str | None = None
    connected_asset_id: int | None = None
    cable_type: str | None = None
    vlan: str | None = None
    status: str | None = None
    location_id: int | None = None
    notes: str | None = None


class NetworkPortResponse(NetworkPortBase):
    id: int
    asset_name: str | None = None
    asset_tag: str | None = None
    location_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
