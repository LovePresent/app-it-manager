from pydantic import BaseModel
from datetime import datetime


class IPAddressBase(BaseModel):
    address: str
    subnet: str | None = None
    gateway: str | None = None
    dns_primary: str | None = None
    dns_secondary: str | None = None
    vlan: str | None = None
    status: str = "available"
    asset_id: int | None = None
    description: str | None = None
    notes: str | None = None


class IPAddressCreate(IPAddressBase):
    pass


class IPAddressUpdate(BaseModel):
    address: str | None = None
    subnet: str | None = None
    gateway: str | None = None
    dns_primary: str | None = None
    dns_secondary: str | None = None
    vlan: str | None = None
    status: str | None = None
    asset_id: int | None = None
    description: str | None = None
    notes: str | None = None


class IPAddressResponse(IPAddressBase):
    id: int
    asset_name: str | None = None
    asset_tag: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
