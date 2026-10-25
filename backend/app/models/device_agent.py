from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class DeviceAgent(Base):
    __tablename__ = "device_agents"

    id = Column(String(36), primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    hardware_key = Column(String(80), nullable=True, unique=True, index=True)
    token_hash = Column(String(64), nullable=True)
    enrollment_hash = Column(String(64), nullable=True)
    enrollment_expires_at = Column(DateTime, nullable=True)
    enrollment_consumed_at = Column(DateTime, nullable=True)
    uninstall_code_hash = Column(String(64), nullable=True)
    uninstall_code_expires_at = Column(DateTime, nullable=True)
    uninstall_requested_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    enrolled_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    revoked_at = Column(DateTime, nullable=True)
    installation_state = Column(String(16), nullable=False, default="pending", server_default="pending")
    uninstalled_at = Column(DateTime, nullable=True)
    service_state = Column(String(24), nullable=True)
    service_last_seen_at = Column(DateTime, nullable=True)
    completion_hash = Column(String(64), nullable=True)
    completion_expires_at = Column(DateTime, nullable=True)
    hostname = Column(String(255), nullable=True)
    os_version = Column(String(255), nullable=True)
    boot_time = Column(DateTime, nullable=True)
    agent_version = Column(String(32), nullable=True)
    last_seen_at = Column(DateTime, nullable=True, index=True)
    observed_ip = Column(String(80), nullable=True)
    capabilities = Column(JSON, nullable=False, default=list)
    network_adapters = Column(JSON, nullable=False, default=list)
    network_updated_at = Column(DateTime, nullable=True)
    network_monitor = Column(JSON, nullable=True)
    wol = Column(JSON, nullable=True)
    last_wake_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    device = relationship("Device", lazy="joined")
