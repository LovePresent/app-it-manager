"""Agent state and command transitions. UTC timestamps are stored naive so the
same schema and comparisons work in SQLite and PostgreSQL; the wire uses UTC Z.
Write locks are database row updates, not process-local mutexes. SQLite obtains
its writer lock and PostgreSQL its row lock before checking mutable state.
"""
import hashlib
import ipaddress
import re
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.device_agent import DeviceAgent
from app.models.device_command import DeviceCommand
from app.models.device_inventory import Device
from app.models.user import User

HEARTBEAT_SECONDS = 15
OFFLINE_SECONDS = 60
COMMAND_SECONDS = 60
ENROLLMENT_SECONDS = 900
INSTALLER_FORMATS = ["exe"]


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(value):
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(timespec="milliseconds") + "Z"


def token_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def matches_token(value, expected):
    return isinstance(value, str) and isinstance(expected, str) and secrets.compare_digest(token_hash(value), expected)


@contextmanager
def transaction(db):
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def find_device(db, device_id):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "디바이스를 찾을 수 없습니다.")
    return device


def find_agent(db, device_id):
    return db.scalar(select(DeviceAgent).where(DeviceAgent.device_id == device_id).execution_options(populate_existing=True))


def lock_device(db, device_id):
    # Preserve inventory timestamps while serializing first registration.
    result = db.execute(update(Device).where(Device.id == device_id).values(updated_at=Device.updated_at))
    if result.rowcount != 1:
        raise HTTPException(404, "디바이스를 찾을 수 없습니다.")


def lock_agents(db, agent_ids):
    for agent_id in sorted(set(agent_ids)):
        result = db.execute(update(DeviceAgent).where(DeviceAgent.id == agent_id)
                            .values(updated_at=DeviceAgent.updated_at).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise HTTPException(404, "에이전트를 찾을 수 없습니다.")


def get_or_create_agent(db, device, agent_id=None):
    lock_device(db, device.id)
    agent = find_agent(db, device.id)
    if agent is None:
        agent = DeviceAgent(id=agent_id or str(uuid4()), device_id=device.id, capabilities=[], network_adapters=[])
        db.add(agent)
        db.flush()
    lock_agents(db, [agent.id])
    return find_agent(db, device.id)


def authenticated_agent(db, agent_id, authorization, *, lock=True):
    match = re.fullmatch(r"Bearer ([A-Za-z0-9_-]{43})", authorization or "")
    token = match.group(1) if match else None
    agent = db.get(DeviceAgent, str(agent_id), populate_existing=True)
    if agent is None or agent.revoked_at is not None or not matches_token(token, agent.token_hash):
        raise HTTPException(401, "기기 인증에 실패했습니다.")
    if lock:
        lock_agents(db, [agent.id])
        agent = db.get(DeviceAgent, agent.id, populate_existing=True)
        if agent.revoked_at is not None or not matches_token(token, agent.token_hash):
            raise HTTPException(401, "기기 인증에 실패했습니다.")
    return agent


def observed_ip(request):
    # Never trust a JSON field or an arbitrary forwarded header. The deployment
    # may configure trusted proxy handling separately at the ASGI boundary.
    value = request.client.host if request.client else None
    if value and value.lower().startswith("::ffff:"):
        value = value[7:]
    return value


def audit(db, request, agent, action, changes=None, user=None, command=None):
    safe = {"agent_id": agent.id, **(changes or {})}
    if command is not None:
        safe["command_id"] = command.id
    db.add(AuditLog(
        entity_type="device_command" if command is not None else "device_agent",
        entity_id=command.target_device_id if command is not None else agent.device_id,
        action=action, changes=safe,
        user_id=user.id if user is not None else None,
        user_name=user.name if user is not None else "Windows 에이전트",
        ip_address=observed_ip(request),
    ))


def presence(agent, time=None):
    time = time or utcnow()
    if agent.installation_state == "uninstalled" and agent.uninstalled_at is not None:
        return "uninstalled"
    if agent.revoked_at is not None:
        return "revoked"
    if agent.service_state in ("worker_stopped", "worker_missing") and agent.service_last_seen_at is not None:
        age = (time - agent.service_last_seen_at).total_seconds()
        if 0 <= age < OFFLINE_SECONDS:
            return agent.service_state
    if agent.last_seen_at is None or agent.token_hash is None:
        return "pending"
    age = (time - agent.last_seen_at).total_seconds()
    return "online" if 0 <= age < OFFLINE_SECONDS else "offline"


def agent_summary(agent, time=None):
    from app.services.device_agent_observation_service import public_monitor
    return {
        "id": agent.id, "device_id": agent.device_id,
        "name": agent.device.serial_number, "serial_number": agent.device.serial_number,
        "status": presence(agent, time), "last_seen_at": iso(agent.last_seen_at),
        "installation_state": agent.installation_state or "pending", "uninstalled_at": iso(agent.uninstalled_at),
        "service_state": agent.service_state, "service_last_seen_at": iso(agent.service_last_seen_at),
        "hostname": agent.hostname, "os_version": agent.os_version,
        "boot_time": iso(agent.boot_time), "agent_version": agent.agent_version,
        "network_adapters": agent.network_adapters or [], "network_updated_at": iso(agent.network_updated_at),
        "network_monitor": public_monitor(agent, time),
        "observed_ip": agent.observed_ip, "capabilities": agent.capabilities or [], "wol": agent.wol,
        "enrollment_expires_at": iso(agent.enrollment_expires_at) if agent.enrollment_consumed_at is None else None,
        "revoked_at": iso(agent.revoked_at),
    }


def effective_status(command, time=None):
    if command.expires_at <= (time or utcnow()):
        if command.status == "pending":
            return "expired"
        if command.status == "delivered":
            return "unconfirmed"
    return command.status


def command_summary(command, time=None):
    return {
        "id": command.id, "type": command.type, "status": effective_status(command, time),
        "detail": command.detail, "target_device_id": command.target_device_id,
        "executor_agent_id": command.executor_agent_id, "requested_by_id": command.requested_by_id,
        **{field: iso(getattr(command, field)) for field in (
            "created_at", "expires_at", "delivered_at", "acknowledged_at", "finished_at")},
    }


def expire_commands(db, agent_id, time):
    for old, new in (("pending", "expired"), ("delivered", "unconfirmed")):
        db.execute(update(DeviceCommand).where(
            DeviceCommand.executor_agent_id == agent_id,
            DeviceCommand.status == old, DeviceCommand.expires_at <= time,
        ).values(status=new, updated_at=time))


def command_wire(command):
    value = {"id": command.id, "type": command.type, "createdAt": iso(command.created_at), "expiresAt": iso(command.expires_at)}
    if command.type == "wake":
        value["payload"] = command.payload
    return value


def claim_command(db, agent, time):
    expire_commands(db, agent.id, time)
    supported = []
    if "power-control-v1" in (agent.capabilities or []):
        supported.extend(["restart", "shutdown"])
    if "wol-relay-v1" in (agent.capabilities or []):
        supported.append("wake")
    if not supported:
        return None
    command = db.scalar(select(DeviceCommand).where(
        DeviceCommand.executor_agent_id == agent.id, DeviceCommand.status == "pending",
        DeviceCommand.type.in_(supported), DeviceCommand.expires_at > time,
    ).order_by(DeviceCommand.created_at, DeviceCommand.id).limit(1))
    if command is None:
        return None
    # Conditional claim remains safe across workers and DB engines. Never
    # redeliver a delivered record even when an HTTP response is lost.
    result = db.execute(update(DeviceCommand).where(
        DeviceCommand.id == command.id, DeviceCommand.status == "pending",
        DeviceCommand.expires_at > time,
    ).values(status="delivered", delivered_at=time, updated_at=time))
    if result.rowcount != 1:
        return None
    db.refresh(command)
    return command


def require_confirmation(confirmation, device):
    if confirmation != device.serial_number:
        raise HTTPException(400, "대상 PC의 시리얼 번호를 정확하게 입력해 주세요.")


def require_online(agent, capability, time):
    if agent is None or presence(agent, time) != "online":
        raise HTTPException(409, "온라인 상태의 에이전트가 필요합니다.")
    if capability not in (agent.capabilities or []):
        raise HTTPException(409, "이 기능을 지원하는 최신 에이전트로 업데이트해 주세요.")


def new_command(agent, target_device_id, kind, user, time, payload=None):
    return DeviceCommand(
        id=str(uuid4()), executor_agent_id=agent.id, target_device_id=target_device_id,
        requested_by_id=user.id, type=kind, status="pending", payload=payload,
        created_at=time, updated_at=time, expires_at=time + timedelta(seconds=COMMAND_SECONDS),
    )


def relay_source(agent, source_address):
    for adapter in agent.network_adapters or []:
        for entry in adapter.get("ipv4", []):
            if entry.get("address") != source_address:
                continue
            try:
                source = ipaddress.IPv4Address(source_address)
                network = ipaddress.IPv4Network(f"{source_address}/{entry['netmask']}", strict=False)
                if source.is_loopback or source.is_multicast or source.is_unspecified or not 1 <= network.prefixlen <= 30:
                    break
                return str(network.broadcast_address)
            except (ValueError, KeyError):
                break
    raise HTTPException(400, "중계 PC의 유효한 IPv4 LAN 인터페이스를 선택해 주세요.")


def revoke_agent(db, agent, time):
    agent.token_hash = None
    agent.enrollment_hash = None
    agent.enrollment_expires_at = None
    agent.revoked_at = time
    agent.capabilities = []
    # Revoke both commands executed by this agent and pending relay requests
    # targeting its inventory device; the inventory itself remains untouched.
    condition = or_(DeviceCommand.executor_agent_id == agent.id, DeviceCommand.target_device_id == agent.device_id)
    for old, new in (("pending", "expired"), ("delivered", "unconfirmed")):
        db.execute(update(DeviceCommand).where(condition, DeviceCommand.status == old)
                   .values(status=new, detail="revoked", updated_at=time))


def reset_installation_lifecycle(agent):
    # A successful new enrollment invalidates receipts from an older install.
    agent.installation_state = "pending"
    agent.uninstalled_at = None
    agent.service_state = None
    agent.service_last_seen_at = None
    agent.completion_hash = None
    agent.completion_expires_at = None
    agent.uninstall_code_hash = None
    agent.uninstall_code_expires_at = None
    agent.uninstall_requested_by_id = None


def public_origin(value):
    try:
        parsed = urlsplit(str(value))
        host = parsed.hostname
        if not host or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError()
        parsed.port  # Validate malformed/out-of-range ports.
        loopback = host.lower() == "localhost"
        try:
            loopback = loopback or ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise ValueError()
        return f"{parsed.scheme}://{parsed.netloc}"
    except ValueError:
        raise HTTPException(400, "AGENT_PUBLIC_URL은 HTTPS 주소여야 합니다. HTTP는 localhost에서만 허용됩니다.")
