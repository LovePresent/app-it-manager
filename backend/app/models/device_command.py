from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, func

from app.database import Base


class DeviceCommand(Base):
    __tablename__ = "device_commands"

    id = Column(String(36), primary_key=True)
    executor_agent_id = Column(String(36), ForeignKey("device_agents.id", ondelete="CASCADE"), nullable=False, index=True)
    target_device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    type = Column(String(16), nullable=False)
    status = Column(String(24), nullable=False, index=True)
    detail = Column(String(32), nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime, nullable=False, index=True)
    delivered_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
