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


class IPChangeHistory(Base):
    __tablename__ = "ip_change_history"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String, nullable=False, index=True)  # device, ip_address
    source_id = Column(Integer, nullable=False, index=True)
    device_id = Column(Integer, nullable=True, index=True)
    ip_address_id = Column(Integer, nullable=True, index=True)

    old_serial_number = Column(String, nullable=True, index=True)
    new_serial_number = Column(String, nullable=True, index=True)
    user_name = Column(String, nullable=True, index=True)
    employee_number = Column(String, nullable=True, index=True)
    asset_tag = Column(String, nullable=True, index=True)
    asset_name = Column(String, nullable=True, index=True)

    old_ip_address = Column(String, nullable=True, index=True)
    new_ip_address = Column(String, nullable=True, index=True)
    old_mac_address = Column(String, nullable=True, index=True)
    new_mac_address = Column(String, nullable=True, index=True)
    old_status = Column(String, nullable=True)
    new_status = Column(String, nullable=True)

    change_reason = Column(String, nullable=False, default="IP 변경", index=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
