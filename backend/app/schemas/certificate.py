from pydantic import BaseModel
from datetime import date, datetime


class CertificateBase(BaseModel):
    asset_id: int
    domain: str
    issuer: str | None = None
    issued_date: date | None = None
    expiry_date: date | None = None
    cert_type: str | None = None
    auto_renew: bool = False
    registrar: str | None = None
    notes: str | None = None


class CertificateCreate(CertificateBase):
    pass


class CertificateUpdate(BaseModel):
    domain: str | None = None
    issuer: str | None = None
    issued_date: date | None = None
    expiry_date: date | None = None
    cert_type: str | None = None
    auto_renew: bool | None = None
    registrar: str | None = None
    notes: str | None = None


class CertificateResponse(CertificateBase):
    id: int
    asset_name: str | None = None
    asset_tag: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
