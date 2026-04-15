from sqlalchemy import Column, Integer, String, Date, ForeignKey, DateTime, Boolean, func
from sqlalchemy.orm import relationship
from app.database import Base


class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    domain = Column(String, nullable=False, index=True)
    issuer = Column(String, nullable=True)
    issued_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    cert_type = Column(String, nullable=True)  # ssl, wildcard, ev, code_signing, domain_registration
    auto_renew = Column(Boolean, default=False)
    registrar = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    asset = relationship("Asset", lazy="joined")
