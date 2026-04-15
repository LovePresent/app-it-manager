from sqlalchemy import Column, Integer, String, JSON, DateTime, func
from app.database import Base


class AssetCategory(Base):
    __tablename__ = "asset_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    slug = Column(String, nullable=False, unique=True, index=True)
    icon = Column(String, nullable=True)
    description = Column(String, nullable=True)
    custom_field_schema = Column(JSON, nullable=True, default=list)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
