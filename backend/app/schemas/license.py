from pydantic import BaseModel
from datetime import date, datetime


class LicenseBase(BaseModel):
    asset_id: int
    license_key: str | None = None
    license_type: str | None = None
    seats_total: int | None = None
    seats_used: int = 0
    expiry_date: date | None = None
    vendor_id: int | None = None
    notes: str | None = None


class LicenseCreate(LicenseBase):
    pass


class LicenseUpdate(BaseModel):
    license_key: str | None = None
    license_type: str | None = None
    seats_total: int | None = None
    seats_used: int | None = None
    expiry_date: date | None = None
    vendor_id: int | None = None
    notes: str | None = None


class LicenseResponse(LicenseBase):
    id: int
    asset_name: str | None = None
    asset_tag: str | None = None
    vendor_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
