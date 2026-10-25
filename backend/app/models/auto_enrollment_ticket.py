from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, false, func

from app.database import Base


class AutoEnrollmentTicket(Base):
    __tablename__ = "auto_enrollment_tickets"
    __table_args__ = (
        CheckConstraint("max_uses >= 1 AND max_uses <= 1000", name="ck_auto_ticket_max_uses"),
        CheckConstraint("used_count >= 0 AND used_count <= max_uses", name="ck_auto_ticket_used_count"),
    )

    id = Column(String(36), primary_key=True)
    token_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    max_uses = Column(Integer, nullable=False)
    unlimited = Column(Boolean, nullable=False, default=False, server_default=false())
    used_count = Column(Integer, nullable=False, default=0)
    issued_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
