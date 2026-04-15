from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, DateTime, Boolean, func
from sqlalchemy.orm import relationship
from app.database import Base


class CloudSubscription(Base):
    __tablename__ = "cloud_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    provider = Column(String, nullable=True)
    plan = Column(String, nullable=True)
    billing_cycle = Column(String, nullable=True)  # monthly, yearly
    monthly_cost = Column(Float, nullable=True)
    renewal_date = Column(Date, nullable=True)
    auto_renew = Column(Boolean, default=False)
    account_url = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    asset = relationship("Asset", lazy="joined")
