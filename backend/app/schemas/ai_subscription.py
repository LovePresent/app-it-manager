from datetime import date, datetime

from pydantic import BaseModel


class AIUsageSubscriptionBase(BaseModel):
    service_name: str
    provider: str | None = None
    model_name: str | None = None
    plan_name: str | None = None
    account_email: str | None = None
    owner_name: str | None = None
    employee_number: str | None = None
    department: str | None = None
    billing_cycle: str | None = None
    monthly_cost: float | None = None
    token_limit: int | None = None
    used_tokens: int | None = None
    renewal_date: date | None = None
    auto_renew: bool = False
    status: str = "active"
    usage_purpose: str | None = None
    notes: str | None = None


class AIUsageSubscriptionCreate(AIUsageSubscriptionBase):
    pass


class AIUsageSubscriptionUpdate(BaseModel):
    service_name: str | None = None
    provider: str | None = None
    model_name: str | None = None
    plan_name: str | None = None
    account_email: str | None = None
    owner_name: str | None = None
    employee_number: str | None = None
    department: str | None = None
    billing_cycle: str | None = None
    monthly_cost: float | None = None
    token_limit: int | None = None
    used_tokens: int | None = None
    renewal_date: date | None = None
    auto_renew: bool | None = None
    status: str | None = None
    usage_purpose: str | None = None
    notes: str | None = None


class AIUsageSubscriptionResponse(AIUsageSubscriptionBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
