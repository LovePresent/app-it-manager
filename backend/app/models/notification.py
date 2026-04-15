from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, ForeignKey, func
from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)  # license_expiry, warranty_expiry, cert_expiry, low_stock, maintenance_due
    entity_type = Column(String, nullable=True)
    entity_id = Column(Integer, nullable=True)
    title = Column(String, nullable=False)
    message = Column(String, nullable=True)
    due_date = Column(Date, nullable=True)
    is_read = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
