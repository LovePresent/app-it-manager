from pydantic import BaseModel
from datetime import datetime


class LocationBase(BaseModel):
    name: str
    type: str | None = None
    parent_id: int | None = None
    description: str | None = None


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    parent_id: int | None = None
    description: str | None = None


class LocationResponse(LocationBase):
    id: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DepartmentBase(BaseModel):
    name: str
    code: str | None = None
    manager: str | None = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    manager: str | None = None


class DepartmentResponse(DepartmentBase):
    id: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class VendorBase(BaseModel):
    name: str
    contact_person: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    contract_info: str | None = None
    notes: str | None = None


class VendorCreate(VendorBase):
    pass


class VendorUpdate(BaseModel):
    name: str | None = None
    contact_person: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    contract_info: str | None = None
    notes: str | None = None


class VendorResponse(VendorBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
