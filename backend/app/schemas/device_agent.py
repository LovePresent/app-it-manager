"""Native ITAM agent API. Admin/read fields are snake_case; the Windows wire
protocol and NIC/WOL payloads retain camelCase. Installation responses are files.
GET /agents -> items,total,server_time,installer_formats,timing/version metadata.
GET /devices/{id}/agent -> agent,commands,relay_devices,server_time,installer_formats.
No response schema ever includes an enrollment or device credential hash.
"""
import ipaddress
import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


def normalize_mac(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9a-fA-F]{12}|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}|(?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2})", value):
        raise ValueError("MAC 주소가 올바르지 않습니다.")
    raw = bytes.fromhex(value.replace(":", "").replace("-", ""))
    if raw == bytes(6) or raw[0] & 1:
        raise ValueError("개별 어댑터의 MAC 주소가 필요합니다.")
    return ":".join(f"{part:02X}" for part in raw)


def safe_text(value: str) -> str:
    if not value.strip() or re.search(r"[\x00-\x1f\x7f]", value):
        raise ValueError("비어 있거나 제어 문자가 포함된 값입니다.")
    return value.strip()


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IPv4Entry(StrictRequest):
    address: str = Field(max_length=15)
    netmask: str = Field(max_length=15)

    @field_validator("address")
    @classmethod
    def valid_address(cls, value):
        return str(ipaddress.IPv4Address(value))

    @field_validator("netmask")
    @classmethod
    def valid_mask(cls, value):
        ipaddress.IPv4Address(value)
        network = ipaddress.IPv4Network(f"0.0.0.0/{value}")
        if network.prefixlen == 0:
            raise ValueError("유효한 서브넷 마스크가 필요합니다.")
        return str(network.netmask)


class NetworkAdapter(StrictRequest):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    macAddress: str | None = None
    ipv4: list[IPv4Entry] = Field(max_length=8)
    ipv6: list[str] = Field(max_length=8)
    physical: StrictBool

    _text = field_validator("id", "name")(safe_text)

    @field_validator("macAddress")
    @classmethod
    def valid_mac(cls, value):
        return normalize_mac(value) if value is not None else None

    @field_validator("ipv6")
    @classmethod
    def valid_ipv6(cls, values):
        result = []
        for value in values:
            if len(value) > 80 or not re.fullmatch(r"[0-9a-fA-F:.]+(?:%[A-Za-z0-9_.-]{1,20})?", value):
                raise ValueError("IPv6 주소가 올바르지 않습니다.")
            normalized = str(ipaddress.IPv6Address(value)).lower()
            if normalized not in result:
                result.append(normalized)
        return result


Capability = Literal["power-control-v1", "network-info-v1", "wol-relay-v1"]


class HeartbeatRequest(BaseModel):
    # Unknown observedIp/lastSeenAt fields cannot affect server-side observations.
    model_config = ConfigDict(extra="ignore")
    deviceId: UUID
    hostname: str = Field(min_length=1, max_length=255)
    os: str = Field(min_length=1, max_length=255)
    agentVersion: str = Field(min_length=1, max_length=32)
    bootTime: datetime
    capabilities: list[Capability] = Field(default_factory=list, max_length=3)
    networkAdapters: list[NetworkAdapter] | None = Field(default=None, max_length=16)

    _text = field_validator("hostname", "os", "agentVersion")(safe_text)

    @model_validator(mode="before")
    @classmethod
    def supplied_inventory_is_array(cls, value):
        if isinstance(value, dict) and "networkAdapters" in value and not isinstance(value["networkAdapters"], list):
            raise ValueError("네트워크 어댑터 목록이 필요합니다.")
        if isinstance(value, dict) and not isinstance(value.get("bootTime"), str):
            raise ValueError("부팅 시각 문자열이 필요합니다.")
        return value

    @field_validator("bootTime")
    @classmethod
    def valid_boot_time(cls, value):
        if value.tzinfo is None or value.timestamp() < 0:
            raise ValueError("시간대가 있는 부팅 시각이 필요합니다.")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @field_validator("networkAdapters")
    @classmethod
    def unique_adapters(cls, value):
        if value is not None and len({adapter.id for adapter in value}) != len(value):
            raise ValueError("중복 어댑터 ID입니다.")
        return value


class EnrollmentRequest(StrictRequest):
    deviceId: UUID
    enrollmentToken: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class UninstallAuthorizationRequest(StrictRequest):
    deviceId: UUID
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class UninstallCompletionRequest(StrictRequest):
    deviceId: UUID
    receipt: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class ServiceHealthRequest(StrictRequest):
    deviceId: UUID
    state: Literal["running", "worker_stopped", "worker_missing"]


class InstallerRequest(StrictRequest):
    format: Literal["exe"] = "exe"


class AutoInstallerRequest(StrictRequest):
    # New installers have no PC-count limit. Explicit counts remain accepted
    # only for compatibility with previously issued bounded-ticket workflows.
    max_uses: int | None = Field(default=None, ge=1, le=1000, strict=True)
    expires_hours: int = Field(default=24, ge=1, le=168, strict=True)


def usable_serial(value):
    if value is None:
        return None
    value = value.strip().upper()
    if re.search(r"[\x00-\x1f\x7f]", value):
        raise ValueError("시리얼 번호에 제어 문자를 사용할 수 없습니다.")
    compact = re.sub(r"[^A-Z0-9]", "", value)
    placeholders = {
        "TOBEFILLEDBYOEM", "TOBEFILLED", "DEFAULTSTRING", "DEFAULT", "OEM",
        "SYSTEMSERIALNUMBER", "SERIALNUMBER", "UNKNOWN", "NONE", "NOTSPECIFIED",
        "NOTAPPLICABLE", "NA", "INVALID", "123456789", "0123456789", "1234567890",
    }
    if len(compact) < 3 or compact in placeholders or set(compact) <= {"0"} or set(compact) <= {"F"} or set(compact) <= {"X"}:
        return None
    if not re.fullmatch(r"[A-Z0-9 ._:/-]+", value):
        return None
    return value


class AutoEnrollmentRequest(StrictRequest):
    ticketId: UUID
    registrationToken: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    clientNonce: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    hardwareUuid: UUID | None = None
    serialNumber: str | None = Field(default=None, max_length=128)
    hostname: str = Field(min_length=1, max_length=255)
    deviceType: Literal["desktop", "laptop"]
    os: str = Field(min_length=1, max_length=255)

    _text = field_validator("hostname", "os")(safe_text)
    _serial = field_validator("serialNumber")(usable_serial)

    @field_validator("hardwareUuid")
    @classmethod
    def usable_uuid(cls, value):
        if value is not None and (value.int in (0, (1 << 128) - 1) or str(value) == "03000200-0400-0500-0006-000700080009"):
            return None
        return value

    @model_validator(mode="after")
    def require_hardware_identity(self):
        if self.hardwareUuid is None and self.serialNumber is None:
            raise ValueError("유효한 하드웨어 UUID 또는 BIOS 시리얼 번호를 확인할 수 없습니다. 관리자가 기존 장비에서 전용 설치 파일을 발급해 주세요.")
        return self


class PowerRequest(StrictRequest):
    action: Literal["restart", "shutdown"]
    confirmation: str = Field(max_length=512)


class WakeRequest(StrictRequest):
    confirmation: str = Field(max_length=512)


class IpReviewRequest(StrictRequest):
    incidentId: UUID
    action: Literal["start", "resolve"]
    note: str = Field(min_length=1, max_length=1000)

    @field_validator("note")
    @classmethod
    def meaningful_note(cls, value):
        value = value.strip()
        if not value or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
            raise ValueError("점검 또는 조치 내용을 1~1000자로 입력해 주세요.")
        return value


class WolRequest(StrictRequest):
    macAddress: str
    relayDeviceId: int = Field(gt=0, strict=True)
    sourceAddress: str

    _mac = field_validator("macAddress")(normalize_mac)

    @field_validator("sourceAddress")
    @classmethod
    def valid_source(cls, value):
        return str(ipaddress.IPv4Address(value))


class AckRequest(StrictRequest):
    deviceId: UUID
    status: Literal["accepted", "failed", "succeeded"]
    detail: Literal["accepted", "expired", "duplicate", "execution_failed", "invalid_command", "packet_sent", "send_failed"]


class AgentSummary(BaseModel):
    id: str
    device_id: int
    name: str
    serial_number: str
    status: Literal["pending", "online", "offline", "revoked", "uninstalled", "worker_stopped", "worker_missing"]
    installation_state: Literal["pending", "installed", "uninstalled"]
    uninstalled_at: str | None
    service_state: Literal["running", "worker_stopped", "worker_missing"] | None
    service_last_seen_at: str | None
    last_seen_at: str | None
    hostname: str | None
    os_version: str | None
    boot_time: str | None
    agent_version: str | None
    network_adapters: list[NetworkAdapter]
    network_updated_at: str | None
    network_monitor: dict | None
    observed_ip: str | None
    capabilities: list[str]
    wol: dict | None
    enrollment_expires_at: str | None
    revoked_at: str | None


class CommandSummary(BaseModel):
    id: str
    type: str
    status: str
    detail: str | None
    target_device_id: int
    executor_agent_id: str
    requested_by_id: int | None
    created_at: str
    expires_at: str
    delivered_at: str | None
    acknowledged_at: str | None
    finished_at: str | None


class AgentListResponse(BaseModel):
    items: list[AgentSummary]
    total: int
    server_time: str
    installer_formats: list[str]
    latest_agent_version: str = "0.5.0"
    heartbeat_interval_seconds: int = 15
    offline_after_seconds: int = 60


class AgentDetailResponse(BaseModel):
    agent: AgentSummary | None
    commands: list[CommandSummary]
    relay_devices: list[AgentSummary]
    server_time: str
    installer_formats: list[str]
    latest_agent_version: str = "0.5.0"
