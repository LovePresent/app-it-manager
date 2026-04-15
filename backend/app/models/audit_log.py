from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, func
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, nullable=False, index=True)  # asset, license, ip_address, etc.
    entity_id = Column(Integer, nullable=False, index=True)
    action = Column(String, nullable=False)  # create, update, delete
    changes = Column(JSON, nullable=True)  # {field: {old: ..., new: ...}}
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_name = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, server_default=func.now(), index=True)
