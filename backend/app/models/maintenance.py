from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import relationship
from app.database import Base


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    maintenance_type = Column(String, nullable=False)  # preventive, corrective, upgrade
    description = Column(Text, nullable=True)
    cost = Column(Float, nullable=True)
    scheduled_date = Column(Date, nullable=True)
    completed_date = Column(Date, nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    technician = Column(String, nullable=True)
    status = Column(String, default="scheduled")  # scheduled, in_progress, completed, cancelled
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    asset = relationship("Asset", lazy="joined")
    vendor = relationship("Vendor", lazy="joined")
