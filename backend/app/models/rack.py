from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base


class Rack(Base):
    __tablename__ = "racks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    total_units = Column(Integer, default=42)
    power_capacity = Column(Float, nullable=True)  # watts
    description = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    location = relationship("Location", lazy="joined")


class RackUnit(Base):
    __tablename__ = "rack_units"

    id = Column(Integer, primary_key=True, index=True)
    rack_id = Column(Integer, ForeignKey("racks.id"), nullable=False, index=True)
    start_unit = Column(Integer, nullable=False)
    end_unit = Column(Integer, nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    position = Column(String, default="front")  # front, rear
    notes = Column(String, nullable=True)

    rack = relationship("Rack", lazy="joined")
    asset = relationship("Asset", lazy="joined")
