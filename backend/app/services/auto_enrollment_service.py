"""Bounded automatic registration without plaintext credential storage.

An enrollment ticket authorizes a limited number of installations. A persisted
client nonce makes response-loss retries idempotent; it cannot rotate an already
bound agent's credential. Inventory identity never uses an IP or hostname.
"""
import base64
import hmac
import json
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select, update

from app.config import settings
from app.models.audit_log import AuditLog
from app.models.auto_enrollment_claim import AutoEnrollmentClaim
from app.models.auto_enrollment_ticket import AutoEnrollmentTicket
from app.models.device_agent import DeviceAgent
from app.models.device_command import DeviceCommand
from app.models.device_inventory import Device
from app.models.user import User
from app.services import device_agent_service as service


def enrollment_key():
    override = getattr(settings, "AGENT_ENROLLMENT_SECRET", "")
    try:
        key = override.encode("utf-8") if override else Path(
            getattr(settings, "AGENT_ENROLLMENT_SECRET_FILE", "data/agent-enrollment.key")
        ).read_bytes()
    except OSError as exc:
        raise HTTPException(503, "자동 등록용 서버 키가 준비되지 않았습니다. 관리자에게 문의해 주세요.") from exc
    if len(key) < 32:
        raise HTTPException(503, "자동 등록용 서버 키는 32바이트 이상이어야 합니다.")
    return key


def hardware_key(data):
    if data.hardwareUuid is not None:
        return "uuid:" + str(data.hardwareUuid)
    return "serial:" + service.token_hash(data.serialNumber)


def derived_token(key, ticket_id, nonce, agent_id):
    message = json.dumps(["itam-auto-enrollment-v1", ticket_id, nonce, agent_id], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(hmac.digest(key, message, "sha256")).rstrip(b"=").decode("ascii")


def audit_ticket(db, request, ticket, user):
    changes = {"ticket_id": ticket.id, "unlimited": ticket.unlimited, "expires_at": service.iso(ticket.expires_at)}
    if not ticket.unlimited:
        changes["max_uses"] = ticket.max_uses
    db.add(AuditLog(
        entity_type="agent_auto_enrollment", entity_id=0, action="installer_issue",
        changes=changes,
        user_id=user.id, user_name=user.name, ip_address=service.observed_ip(request),
    ))


def result(agent, token, created):
    return {"ok": True, "deviceId": agent.id, "deviceToken": token,
            "inventoryDeviceId": agent.device_id, "created": created,
            "serialNumber": agent.device.serial_number}


def register(db, data, request):
    key = enrollment_key()
    ticket_id = str(data.ticketId)
    ticket = db.get(AutoEnrollmentTicket, ticket_id)
    if ticket is None or not service.matches_token(data.registrationToken, ticket.token_hash):
        raise HTTPException(401, "자동 등록 코드가 일치하지 않습니다.")
    # Serializes quota and same-ticket retries in both SQLite and PostgreSQL.
    db.execute(update(AutoEnrollmentTicket).where(AutoEnrollmentTicket.id == ticket_id)
               .values(updated_at=AutoEnrollmentTicket.updated_at).execution_options(synchronize_session=False))
    db.refresh(ticket)
    if not service.matches_token(data.registrationToken, ticket.token_hash):
        raise HTTPException(401, "자동 등록 코드가 일치하지 않습니다.")
    now = service.utcnow()
    if ticket.expires_at <= now:
        raise HTTPException(409, "자동 등록 설치 파일이 만료되었습니다. 새 EXE를 발급해 주세요.")
    identity = hardware_key(data)
    nonce_hash = service.token_hash(data.clientNonce)
    claim = db.scalar(select(AutoEnrollmentClaim).where(
        AutoEnrollmentClaim.ticket_id == ticket_id, AutoEnrollmentClaim.nonce_hash == nonce_hash,
    ))
    if claim is not None:
        if claim.hardware_key != identity:
            raise HTTPException(409, "등록 재시도의 하드웨어 식별 정보가 일치하지 않습니다.")
        agent = db.get(DeviceAgent, claim.agent_id, populate_existing=True)
        if agent is None:
            raise HTTPException(409, "기존 등록을 복구할 수 없습니다. 관리자에게 문의해 주세요.")
        service.lock_agents(db, [agent.id])
        db.refresh(agent)
        token = derived_token(key, ticket_id, data.clientNonce, agent.id)
        if agent.revoked_at is not None or not service.matches_token(token, agent.token_hash):
            raise HTTPException(409, "기존 인증이 폐기되거나 변경되었습니다. 관리자가 다시 등록해야 합니다.")
        # A completed claim remains recoverable until expiry, even at quota.
        return result(agent, token, claim.created_device)
    if not ticket.unlimited and ticket.used_count >= ticket.max_uses:
        raise HTTPException(409, "이 설치 파일의 등록 가능 대수를 모두 사용했습니다. 새 EXE를 발급해 주세요.")

    prior = db.scalar(select(DeviceAgent).where(DeviceAgent.hardware_key == identity))
    created = False
    if prior is not None:
        device = service.find_device(db, prior.device_id)
    else:
        matches = []
        if data.serialNumber is not None:
            matches = db.scalars(select(Device).where(
                func.upper(func.trim(Device.serial_number)) == data.serialNumber,
            ).limit(2)).all()
        if len(matches) > 1:
            raise HTTPException(409, "시리얼 번호가 같은 장비가 여러 대입니다. 관리자가 장비 대장을 확인해 주세요.")
        if matches:
            device = matches[0]
        else:
            serial = data.serialNumber or ("AUTO-" + str(data.hardwareUuid))
            device = Device(serial_number=serial, device_type=data.deviceType, status="stock",
                            os_version=data.os, notes="Windows 에이전트 설치 중 자동 발견 및 등록")
            db.add(device)
            db.flush()
            created = True

    agent = service.get_or_create_agent(db, device)
    # Pending explicit enrollment is also an administrator's existing binding.
    # An automatic installer must not take it over with a fresh nonce.
    pending_explicit = (agent.enrollment_hash is not None and agent.enrollment_consumed_at is None
                        and agent.enrollment_expires_at is not None and agent.enrollment_expires_at > now)
    if pending_explicit or (agent.revoked_at is None and agent.token_hash is not None):
        raise HTTPException(409, "이미 에이전트가 연결된 장비입니다. 기존 설정으로 업데이트하거나 관리자가 등록을 해제한 후 다시 설치해 주세요.")
    token = derived_token(key, ticket_id, data.clientNonce, agent.id)
    agent.hardware_key = identity
    agent.token_hash = service.token_hash(token)
    agent.enrollment_hash = None
    agent.enrollment_expires_at = None
    agent.enrollment_consumed_at = None
    agent.enrolled_by_id = ticket.issued_by_id
    agent.revoked_at = None
    service.reset_installation_lifecycle(agent)
    agent.uninstall_code_hash = None
    agent.uninstall_code_expires_at = None
    agent.uninstall_requested_by_id = None
    agent.hostname = data.hostname
    agent.os_version = data.os
    agent.last_seen_at = None
    agent.capabilities = []
    agent.network_adapters = []
    agent.network_updated_at = None
    agent.observed_ip = None
    # Re-registration cannot deliver a stale command from an earlier install.
    db.execute(update(DeviceCommand).where(DeviceCommand.executor_agent_id == agent.id,
               DeviceCommand.status.in_(["pending", "delivered"]))
               .values(status="expired", detail="reenrolled", updated_at=now))
    # used_count is the legacy bounded-quota counter; unlimited registrations
    # consume no quota. Durable claims are the exact registration history.
    if not ticket.unlimited:
        ticket.used_count += 1
    claim = AutoEnrollmentClaim(ticket_id=ticket_id, nonce_hash=nonce_hash, hardware_key=identity,
                                agent_id=agent.id, created_device=created, created_at=now, updated_at=now)
    db.add(claim)
    issuer = db.get(User, ticket.issued_by_id) if ticket.issued_by_id else None
    if created:
        db.add(AuditLog(entity_type="device", entity_id=device.id, action="create",
                        changes={"source": "automatic_agent_enrollment", "ticket_id": ticket_id, "serial_number": device.serial_number},
                        user_id=issuer.id if issuer else None, user_name=issuer.name if issuer else "Windows 에이전트",
                        ip_address=service.observed_ip(request)))
    service.audit(db, request, agent, "auto_enroll", {"ticket_id": ticket_id, "created_device": created}, issuer)
    db.flush()  # Enforce unique hardware/nonce identities before returning a token.
    return result(agent, token, created)
