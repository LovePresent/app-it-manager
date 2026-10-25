from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func

from app.database import Base


class AutoEnrollmentClaim(Base):
    __tablename__ = "auto_enrollment_claims"
    __table_args__ = (UniqueConstraint("ticket_id", "nonce_hash", name="uq_auto_claim_ticket_nonce"),)

    id = Column(Integer, primary_key=True)
    ticket_id = Column(String(36), ForeignKey("auto_enrollment_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    nonce_hash = Column(String(64), nullable=False)
    hardware_key = Column(String(80), nullable=False, index=True)
    agent_id = Column(String(36), ForeignKey("device_agents.id", ondelete="CASCADE"), nullable=False, index=True)
    created_device = Column(Boolean, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
