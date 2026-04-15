from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, DateTime, Boolean, func
from sqlalchemy.orm import relationship
from app.database import Base


class SoftwareLicense(Base):
    __tablename__ = "software_licenses"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    license_key = Column(String, nullable=True)
    license_type = Column(String, nullable=True)  # per_seat, volume, site, oem, subscription
    seats_total = Column(Integer, nullable=True)
    seats_used = Column(Integer, default=0)
    expiry_date = Column(Date, nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    asset = relationship("Asset", lazy="joined")
    vendor = relationship("Vendor", lazy="joined")
