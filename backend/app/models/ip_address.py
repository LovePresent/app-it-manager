from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base


class IPAddress(Base):
    __tablename__ = "ip_addresses"

    id = Column(Integer, primary_key=True, index=True)
    address = Column(String, unique=True, nullable=False, index=True)
    subnet = Column(String, nullable=True)
    gateway = Column(String, nullable=True)
    dns_primary = Column(String, nullable=True)
    dns_secondary = Column(String, nullable=True)
    vlan = Column(String, nullable=True)
    status = Column(String, nullable=False, default="available")  # available, assigned, reserved
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    description = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    asset = relationship("Asset", lazy="joined")
