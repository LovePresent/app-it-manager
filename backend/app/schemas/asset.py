from pydantic import BaseModel
from datetime import date, datetime


class AssetBase(BaseModel):
    name: str
    category_id: int
    status: str = "in_stock"
    serial_number: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    purchase_date: date | None = None
    purchase_price: float | None = None
    warranty_expiry: date | None = None
    vendor_id: int | None = None
    location_id: int | None = None
    department_id: int | None = None
    assigned_to: int | None = None
    notes: str | None = None
    custom_fields: dict | None = None


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    name: str | None = None
    category_id: int | None = None
    status: str | None = None
    serial_number: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    purchase_date: date | None = None
    purchase_price: float | None = None
    warranty_expiry: date | None = None
    vendor_id: int | None = None
    location_id: int | None = None
    department_id: int | None = None
    assigned_to: int | None = None
    notes: str | None = None
    custom_fields: dict | None = None


class AssetResponse(AssetBase):
    id: int
    asset_tag: str
    qr_code_path: str | None = None
    image_path: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    category_name: str | None = None
    location_name: str | None = None
    department_name: str | None = None
    assigned_user_name: str | None = None
    vendor_name: str | None = None

    model_config = {"from_attributes": True}


class AssetAssignRequest(BaseModel):
    user_id: int
    notes: str | None = None


class AssetReturnRequest(BaseModel):
    notes: str | None = None


class AssetAssignmentResponse(BaseModel):
    id: int
    asset_id: int
    user_id: int
    assigned_at: datetime | None = None
    returned_at: datetime | None = None
    notes: str | None = None
    user_name: str | None = None
    asset_name: str | None = None
    asset_tag: str | None = None

    model_config = {"from_attributes": True}
