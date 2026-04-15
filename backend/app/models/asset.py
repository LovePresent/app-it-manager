from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Float, Text,
    ForeignKey, JSON, Enum, func,
)
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class AssetStatus(str, enum.Enum):
    IN_STOCK = "in_stock"
    ASSIGNED = "assigned"
    IN_MAINTENANCE = "in_maintenance"
    RETIRED = "retired"
    DISPOSED = "disposed"
    LOST = "lost"


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    asset_tag = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("asset_categories.id"), nullable=False)
    status = Column(String, nullable=False, default=AssetStatus.IN_STOCK.value, index=True)

    # Identification
    serial_number = Column(String, nullable=True, index=True)
    model = Column(String, nullable=True)
    manufacturer = Column(String, nullable=True)

    # Purchase info
    purchase_date = Column(Date, nullable=True)
    purchase_price = Column(Float, nullable=True)
    warranty_expiry = Column(Date, nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)

    # Location & assignment
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Extra
    notes = Column(Text, nullable=True)
    custom_fields = Column(JSON, nullable=True, default=dict)
    qr_code_path = Column(String, nullable=True)
    image_path = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    category = relationship("AssetCategory", lazy="joined")
    location = relationship("Location", lazy="joined")
    department = relationship("Department", lazy="joined")
    assigned_user = relationship("User", lazy="joined")
    vendor = relationship("Vendor", lazy="joined")


class AssetAssignment(Base):
    __tablename__ = "asset_assignments"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime, server_default=func.now())
    returned_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    asset = relationship("Asset", lazy="joined")
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
