from pydantic import BaseModel
from datetime import datetime


class DashboardStats(BaseModel):
    total_assets: int = 0
    assigned_assets: int = 0
    in_stock_assets: int = 0
    in_maintenance_assets: int = 0
    total_licenses: int = 0
    expiring_licenses: int = 0
    total_subscriptions: int = 0
    monthly_subscription_cost: float = 0.0
    total_ip_addresses: int = 0
    used_ip_addresses: int = 0
    expiring_certificates: int = 0
    low_stock_consumables: int = 0
    upcoming_maintenance: int = 0
    recent_changes: int = 0


class CategoryCount(BaseModel):
    category_id: int
    category_name: str
    count: int


class StatusCount(BaseModel):
    status: str
    count: int


class MonthlyCost(BaseModel):
    month: str
    cost: float


class ExpiringItem(BaseModel):
    id: int
    name: str
    type: str  # license, certificate, warranty, subscription
    expiry_date: datetime
    days_remaining: int
