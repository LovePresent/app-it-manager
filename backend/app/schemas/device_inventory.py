from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


def _clean_optional_text(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _clean_required_text(value, field_label: str):
    if isinstance(value, str):
        value = value.strip()
    if value is None or value == "":
        raise ValueError(f"{field_label}를 입력하세요.")
    return value


class DeviceLicenseSummary(BaseModel):
    hangul: bool = False
    ms_office: bool = False
    cad: bool = False
    windows_security: bool = False
    pc_manager: bool = False
    dlp: bool = False
    av: bool = False
    edr: bool = False
    renewal_date: date | None = None


class ComputerSettingSummary(BaseModel):
    smart_app_control: bool = False
    reputation_based_protection: bool = False
    exploit_protection: bool = False
    core_isolation: bool = False


class DeviceBase(BaseModel):
    user_name: str | None = None
    employee_number: str | None = None
    serial_number: str
    device_type: str = "desktop"
    cpu: str | None = None
    memory: str | None = None
    storage: str | None = None
    gpu: str | None = None
    os_version: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    purchase_date: date | None = None
    manufacture_date: date | None = None
    location: str | None = None
    department: str | None = None
    factory: str | None = None
    status: str = "assigned"
    notes: str | None = None


class DeviceCreate(DeviceBase):
    initial_reason: str = "신규 구매"

    @field_validator(
        "user_name",
        "employee_number",
        "cpu",
        "memory",
        "storage",
        "gpu",
        "os_version",
        "ip_address",
        "mac_address",
        "location",
        "department",
        "factory",
        "notes",
        mode="before",
    )
    @classmethod
    def clean_optional_text(cls, value):
        return _clean_optional_text(value)

    @field_validator("serial_number", mode="before")
    @classmethod
    def validate_serial_number(cls, value):
        return _clean_required_text(value, "시리얼 번호")

    @field_validator("device_type", mode="before")
    @classmethod
    def validate_device_type(cls, value):
        return _clean_required_text(value, "종류")

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value):
        return _clean_required_text(value, "상태")


class DeviceUpdate(BaseModel):
    user_name: str | None = None
    employee_number: str | None = None
    serial_number: str | None = None
    device_type: str | None = None
    cpu: str | None = None
    memory: str | None = None
    storage: str | None = None
    gpu: str | None = None
    os_version: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    purchase_date: date | None = None
    manufacture_date: date | None = None
    location: str | None = None
    department: str | None = None
    factory: str | None = None
    status: str | None = None
    notes: str | None = None
    assignment_reason: str | None = None

    @field_validator(
        "user_name",
        "employee_number",
        "cpu",
        "memory",
        "storage",
        "gpu",
        "os_version",
        "ip_address",
        "mac_address",
        "location",
        "department",
        "factory",
        "notes",
        "assignment_reason",
        mode="before",
    )
    @classmethod
    def clean_optional_text(cls, value):
        return _clean_optional_text(value)

    @field_validator("serial_number", mode="before")
    @classmethod
    def validate_serial_number(cls, value):
        if value is None:
            return None
        return _clean_required_text(value, "시리얼 번호")

    @field_validator("device_type", mode="before")
    @classmethod
    def validate_device_type(cls, value):
        if value is None:
            return None
        return _clean_required_text(value, "종류")

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value):
        if value is None:
            return None
        return _clean_required_text(value, "상태")


class DeviceBulkUpdateFields(BaseModel):
    device_type: str | None = None
    cpu: str | None = None
    memory: str | None = None
    storage: str | None = None
    gpu: str | None = None
    os_version: str | None = None
    location: str | None = None
    department: str | None = None
    factory: str | None = None
    status: str | None = None
    notes: str | None = None

    @field_validator(
        "cpu",
        "memory",
        "storage",
        "gpu",
        "os_version",
        "location",
        "department",
        "factory",
        "notes",
        mode="before",
    )
    @classmethod
    def clean_optional_text(cls, value):
        return _clean_optional_text(value)

    @field_validator("device_type", mode="before")
    @classmethod
    def validate_device_type(cls, value):
        if value is None:
            return None
        return _clean_required_text(value, "종류")

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value):
        if value is None:
            return None
        return _clean_required_text(value, "상태")


class ComputerSettingBulkUpdate(BaseModel):
    smart_app_control: bool | None = None
    reputation_based_protection: bool | None = None
    exploit_protection: bool | None = None
    core_isolation: bool | None = None
    notes: str | None = None


class DeviceBulkUpdateRequest(BaseModel):
    device_ids: list[int] = Field(min_length=1)
    updates: DeviceBulkUpdateFields = Field(default_factory=DeviceBulkUpdateFields)
    computer_setting: ComputerSettingBulkUpdate | None = None
    reason: str = "일괄 변경"
    notes: str | None = None


class DeviceUserMergeTarget(BaseModel):
    user_name: str | None = None
    employee_number: str | None = None
    location: str | None = None
    department: str | None = None
    factory: str | None = None

    @field_validator("user_name", "employee_number", "location", "department", "factory", mode="before")
    @classmethod
    def clean_optional_text(cls, value):
        return _clean_optional_text(value)


class DeviceUserMergeRequest(BaseModel):
    device_ids: list[int] = Field(min_length=1)
    target: DeviceUserMergeTarget
    reason: str = Field(default="중복 사용자 정보 병합")
    notes: str | None = None

    @field_validator("reason", mode="before")
    @classmethod
    def validate_reason(cls, value):
        return _clean_required_text(value, "변경 사유")

    @field_validator("notes", mode="before")
    @classmethod
    def clean_optional_text(cls, value):
        return _clean_optional_text(value)


class DeviceResponse(DeviceBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    license_summary: DeviceLicenseSummary | None = None
    computer_setting_summary: ComputerSettingSummary | None = None

    model_config = {"from_attributes": True}


class DeviceReassignRequest(BaseModel):
    user_name: str | None = None
    employee_number: str | None = None
    location: str | None = None
    department: str | None = None
    factory: str | None = None
    reason: str = Field(default="사용자 변경")
    notes: str | None = None

    @field_validator("user_name", "employee_number", "location", "department", "factory", "notes", mode="before")
    @classmethod
    def clean_optional_text(cls, value):
        return _clean_optional_text(value)

    @field_validator("reason", mode="before")
    @classmethod
    def validate_reason(cls, value):
        return _clean_required_text(value, "변경 사유")


class DeviceReplaceRequest(DeviceBase):
    replacement_reason: str = "교체"

    @field_validator(
        "user_name",
        "employee_number",
        "cpu",
        "memory",
        "storage",
        "gpu",
        "os_version",
        "ip_address",
        "mac_address",
        "location",
        "department",
        "factory",
        "notes",
        mode="before",
    )
    @classmethod
    def clean_optional_text(cls, value):
        return _clean_optional_text(value)

    @field_validator("serial_number", mode="before")
    @classmethod
    def validate_serial_number(cls, value):
        return _clean_required_text(value, "시리얼 번호")

    @field_validator("device_type", mode="before")
    @classmethod
    def validate_device_type(cls, value):
        return _clean_required_text(value, "종류")

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value):
        return _clean_required_text(value, "상태")


class DeviceUsageHistoryResponse(BaseModel):
    id: int
    device_id: int
    user_name: str | None = None
    employee_number: str | None = None
    serial_number: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    change_reason: str
    notes: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DeviceLicenseBase(BaseModel):
    device_id: int
    hangul: bool = False
    ms_office: bool = False
    cad: bool = False
    windows_security: bool = False
    pc_manager: bool = False
    dlp: bool = False
    av: bool = False
    edr: bool = False
    purchase_date: date | None = None
    manufacture_date: date | None = None
    renewal_date: date | None = None
    notes: str | None = None


class DeviceLicenseCreate(DeviceLicenseBase):
    pass


class DeviceLicenseUpdate(BaseModel):
    device_id: int | None = None
    hangul: bool | None = None
    ms_office: bool | None = None
    cad: bool | None = None
    windows_security: bool | None = None
    pc_manager: bool | None = None
    dlp: bool | None = None
    av: bool | None = None
    edr: bool | None = None
    purchase_date: date | None = None
    manufacture_date: date | None = None
    renewal_date: date | None = None
    notes: str | None = None


class DeviceLicenseResponse(DeviceLicenseBase):
    id: int
    user_name: str | None = None
    employee_number: str | None = None
    serial_number: str | None = None
    device_type: str | None = None
    location: str | None = None
    department: str | None = None
    factory: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ComputerSettingBase(BaseModel):
    device_id: int
    smart_app_control: bool = False
    reputation_based_protection: bool = False
    exploit_protection: bool = False
    core_isolation: bool = False
    notes: str | None = None


class ComputerSettingCreate(ComputerSettingBase):
    pass


class ComputerSettingUpdate(BaseModel):
    device_id: int | None = None
    smart_app_control: bool | None = None
    reputation_based_protection: bool | None = None
    exploit_protection: bool | None = None
    core_isolation: bool | None = None
    notes: str | None = None


class ComputerSettingResponse(ComputerSettingBase):
    id: int
    user_name: str | None = None
    employee_number: str | None = None
    serial_number: str | None = None
    device_type: str | None = None
    location: str | None = None
    department: str | None = None
    factory: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
