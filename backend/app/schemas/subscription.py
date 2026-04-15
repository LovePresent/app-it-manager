from pydantic import BaseModel
from datetime import date, datetime


class SubscriptionBase(BaseModel):
    asset_id: int
    provider: str | None = None
    plan: str | None = None
    billing_cycle: str | None = None
    monthly_cost: float | None = None
    renewal_date: date | None = None
    auto_renew: bool = False
    account_url: str | None = None
    notes: str | None = None


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionUpdate(BaseModel):
    provider: str | None = None
    plan: str | None = None
    billing_cycle: str | None = None
    monthly_cost: float | None = None
    renewal_date: date | None = None
    auto_renew: bool | None = None
    account_url: str | None = None
    notes: str | None = None


class SubscriptionResponse(SubscriptionBase):
    id: int
    asset_name: str | None = None
    asset_tag: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
