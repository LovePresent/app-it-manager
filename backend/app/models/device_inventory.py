from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.database import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)

    # Current user identity. Employee number is the primary operational key.
    user_name = Column(String, nullable=True, index=True)
    employee_number = Column(String, nullable=True, index=True)

    # Device identity and specification.
    serial_number = Column(String, nullable=False, unique=True, index=True)
    device_type = Column(String, nullable=False, default="desktop", index=True)
    cpu = Column(String, nullable=True)
    memory = Column(String, nullable=True)
    storage = Column(String, nullable=True)
    gpu = Column(String, nullable=True)
    os_version = Column(String, nullable=True)
    ip_address = Column(String, nullable=True, index=True)
    mac_address = Column(String, nullable=True, index=True)

    # Purchase and placement.
    purchase_date = Column(Date, nullable=True)
    manufacture_date = Column(Date, nullable=True)
    location = Column(String, nullable=True, index=True)
    department = Column(String, nullable=True, index=True)
    factory = Column(String, nullable=True, index=True)

    status = Column(String, nullable=False, default="assigned", index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    license_profile = relationship(
        "DeviceLicense",
        back_populates="device",
        uselist=False,
        cascade="all, delete-orphan",
    )
    computer_setting = relationship(
        "ComputerSetting",
        back_populates="device",
        uselist=False,
        cascade="all, delete-orphan",
    )
    usage_history = relationship(
        "DeviceUsageHistory",
        back_populates="device",
        cascade="all, delete-orphan",
        order_by="DeviceUsageHistory.started_at.desc()",
    )


class DeviceLicense(Base):
    __tablename__ = "device_licenses"
    __table_args__ = (UniqueConstraint("device_id", name="uq_device_licenses_device_id"),)

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)

    hangul = Column(Boolean, nullable=False, default=False)
    ms_office = Column(Boolean, nullable=False, default=False)
    cad = Column(Boolean, nullable=False, default=False)
    windows_security = Column(Boolean, nullable=False, default=False)
    pc_manager = Column(Boolean, nullable=False, default=False)
    dlp = Column(Boolean, nullable=False, default=False)
    av = Column(Boolean, nullable=False, default=False)
    edr = Column(Boolean, nullable=False, default=False)

    purchase_date = Column(Date, nullable=True)
    manufacture_date = Column(Date, nullable=True)
    renewal_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    device = relationship("Device", back_populates="license_profile", lazy="joined")


class ComputerSetting(Base):
    __tablename__ = "computer_settings"
    __table_args__ = (UniqueConstraint("device_id", name="uq_computer_settings_device_id"),)

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)

    smart_app_control = Column(Boolean, nullable=False, default=False)
    reputation_based_protection = Column(Boolean, nullable=False, default=False)
    exploit_protection = Column(Boolean, nullable=False, default=False)
    core_isolation = Column(Boolean, nullable=False, default=False)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    device = relationship("Device", back_populates="computer_setting", lazy="joined")


class DeviceUsageHistory(Base):
    __tablename__ = "device_usage_history"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    user_name = Column(String, nullable=True, index=True)
    employee_number = Column(String, nullable=True, index=True)
    serial_number = Column(String, nullable=False, index=True)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    ended_at = Column(DateTime, nullable=True)
    change_reason = Column(String, nullable=False, default="지급", index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    device = relationship("Device", back_populates="usage_history", lazy="joined")
