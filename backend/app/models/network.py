from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base


class NetworkPort(Base):
    __tablename__ = "network_ports"

    id = Column(Integer, primary_key=True, index=True)
    panel_name = Column(String, nullable=False)
    port_number = Column(String, nullable=False)
    connected_asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    cable_type = Column(String, nullable=True)  # cat5e, cat6, cat6a, fiber_sm, fiber_mm
    vlan = Column(String, nullable=True)
    status = Column(String, default="available")  # available, connected, reserved, faulty
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    asset = relationship("Asset", lazy="joined")
    location = relationship("Location", lazy="joined")
