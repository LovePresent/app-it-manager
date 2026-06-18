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
    change_reason: str | None = None


class IPAddressResponse(IPAddressBase):
    id: int
    asset_name: str | None = None
    asset_tag: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class IPChangeHistoryResponse(BaseModel):
    id: int
    source_type: str
    source_id: int
    device_id: int | None = None
    ip_address_id: int | None = None
    old_serial_number: str | None = None
    new_serial_number: str | None = None
    user_name: str | None = None
    employee_number: str | None = None
    asset_tag: str | None = None
    asset_name: str | None = None
    old_ip_address: str | None = None
    new_ip_address: str | None = None
    old_mac_address: str | None = None
    new_mac_address: str | None = None
    old_status: str | None = None
    new_status: str | None = None
    change_reason: str
    notes: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
