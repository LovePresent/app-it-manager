from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import relationship
from app.database import Base


class ConsumableStock(Base):
    __tablename__ = "consumable_stocks"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    qty_in_stock = Column(Integer, default=0)
    min_stock_level = Column(Integer, default=0)
    unit = Column(String, nullable=True, default="개")
    last_restock_date = Column(Date, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    asset = relationship("Asset", lazy="joined")


class ConsumableTransaction(Base):
    __tablename__ = "consumable_transactions"

    id = Column(Integer, primary_key=True, index=True)
    consumable_id = Column(Integer, ForeignKey("consumable_stocks.id"), nullable=False, index=True)
    qty_change = Column(Integer, nullable=False)  # positive=in, negative=out
    transaction_type = Column(String, nullable=False)  # in, out
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    date = Column(DateTime, server_default=func.now())
    notes = Column(Text, nullable=True)

    consumable = relationship("ConsumableStock", lazy="joined")
    user = relationship("User", lazy="joined")
