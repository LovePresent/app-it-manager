from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text, func

from app.database import Base


class AIUsageSubscription(Base):
    __tablename__ = "ai_usage_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=True, index=True)
    model_name = Column(String, nullable=True, index=True)
    plan_name = Column(String, nullable=True)
    account_email = Column(String, nullable=True, index=True)
    owner_name = Column(String, nullable=True, index=True)
    employee_number = Column(String, nullable=True, index=True)
    department = Column(String, nullable=True, index=True)
    billing_cycle = Column(String, nullable=True)
    monthly_cost = Column(Float, nullable=True)
    token_limit = Column(Integer, nullable=True)
    used_tokens = Column(Integer, nullable=True)
    renewal_date = Column(Date, nullable=True)
    auto_renew = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="active", index=True)
    usage_purpose = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
