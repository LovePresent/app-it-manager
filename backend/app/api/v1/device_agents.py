from datetime import datetime, timedelta, timezone
import secrets
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import String, and_, cast, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.config import settings
from app.database import get_db
from app.models.device_agent import DeviceAgent
from app.models.device_command import DeviceCommand
from app.models.auto_enrollment_ticket import AutoEnrollmentTicket
from app.models.auto_enrollment_claim import AutoEnrollmentClaim
from app.models.user import User
from app.models.audit_log import AuditLog
from app.schemas.device_agent import (
    AckRequest, AgentDetailResponse, AgentListResponse, AgentSummary, EnrollmentRequest,
    AutoEnrollmentRequest, AutoInstallerRequest,
    HeartbeatRequest, InstallerRequest, PowerRequest, UninstallAuthorizationRequest,
    UninstallCompletionRequest, ServiceHealthRequest,
    WakeRequest, WolRequest, IpReviewRequest,
)
from app.services import device_agent_service as service
from app.services import auto_enrollment_service as automatic
from app.services import device_agent_observation_service as observations
from app.services import agent_connection_service as connection_service

def prevent_caching(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"


router = APIRouter(dependencies=[Depends(prevent_caching)])


@router.get("/agent/ready")
def agent_ready(request: Request, db: Session = Depends(get_db)):
    from app.services.agent_installer_service import verify_package_ready
    ready = True
    server_id = None
    try:
        connection_service.configured_connection(request.base_url)
        # LIMIT 0 validates registration schema access without returning records.
        for model in (DeviceAgent, DeviceCommand, AutoEnrollmentTicket, AutoEnrollmentClaim, AuditLog):
            db.execute(select(model).limit(0))
        server_id = connection_service.server_id(automatic.enrollment_key())
        verify_package_ready()
    except Exception:
        db.rollback()
        ready = False
    return JSONResponse(status_code=200 if ready else 503, content={
        "product": "app-it-manager-agent", "protocol": 1,
        "serverTime": service.iso(service.utcnow()), "registrationReady": ready,
        "latestAgentVersion": connection_service.LATEST_AGENT_VERSION,
        "serverId": server_id,
    }, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/devices/{device_id}/logs")
def device_logs(device_id: int, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    service.find_device(db, device_id)
    direct = and_(AuditLog.entity_type.in_(["device", "device_agent", "device_command"]),
                  AuditLog.entity_id == device_id)
    # Numeric child IDs may be reused after deletion in SQLite. Only explicit
    # recorded device associations can prove which PC owned a historical row.
    related = and_(AuditLog.entity_type.in_(["computer_setting", "device_license"]),
                   or_(cast(AuditLog.changes["device_id"].as_string(), String) == str(device_id),
                       cast(AuditLog.changes["previous_device_id"].as_string(), String) == str(device_id)))
    query = db.query(AuditLog).filter(or_(direct, related))
    creation_id = db.scalar(select(func.max(AuditLog.id)).where(
        AuditLog.entity_type == "device", AuditLog.entity_id == device_id, AuditLog.action == "create"))
    if creation_id is not None:
        # A new inventory record with a recycled ID must not inherit a former
        # PC's log history. Legacy unscoped records remain in the global audit.
        query = query.filter(AuditLog.id >= creation_id)
    total = query.count()
    entries = query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).offset((page - 1) * size).limit(size).all()
    items = [{"id": entry.id, "entity_type": entry.entity_type, "entity_id": entry.entity_id,
              "action": entry.action, "changes": entry.changes, "user_id": entry.user_id,
              "user_name": entry.user_name, "ip_address": entry.ip_address,
              "timestamp": service.iso(entry.timestamp)} for entry in entries]
    return {"items": items, "total": total, "page": page, "size": size, "pages": (total + size - 1) // size}


@router.post("/agents/auto-installer")
async def download_auto_installer(data: AutoInstallerRequest, request: Request,
                                  db: Session = Depends(get_db), user: User = Depends(require_admin)):
    from app.services.agent_installer_service import build_agent_installer
    issuer_id = connection_service.server_id(automatic.enrollment_key())
    ticket_id = str(uuid4())
    bootstrap = secrets.token_urlsafe(32)
    connection = connection_service.configured_connection(request.base_url)
    connection["expectedServerId"] = issuer_id
    config = {**connection, "registrationMode": "automatic",
              "ticketId": ticket_id, "registrationToken": bootstrap,
              "heartbeatIntervalSeconds": service.HEARTBEAT_SECONDS}
    db.rollback()
    await connection_service.verify_public_readiness(connection)
    try:
        filename, content, mime = await run_in_threadpool(
            build_agent_installer, config=config, device_name="자동 등록", format="exe")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "자동 등록 EXE를 생성하지 못했습니다. 서버의 설치 파일 구성을 확인해 주세요.") from exc
    with service.transaction(db):
        now = service.utcnow()
        ticket = AutoEnrollmentTicket(id=ticket_id, token_hash=service.token_hash(bootstrap),
                    expires_at=now + timedelta(hours=data.expires_hours), max_uses=data.max_uses or 1,
                    unlimited=data.max_uses is None,
                    used_count=0, issued_by_id=user.id, created_at=now, updated_at=now)
        db.add(ticket)
        automatic.audit_ticket(db, request, ticket, user)
        expires = service.iso(ticket.expires_at)
    response_headers = {
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "X-Enrollment-Expires-At": expires, "X-Enrollment-Unlimited": str(data.max_uses is None).lower(),
        "X-Agent-Deployment-Mode": connection["deploymentMode"],
    }
    if data.max_uses is not None:
        response_headers["X-Enrollment-Max-Uses"] = str(data.max_uses)
    return Response(content=content, media_type=mime, headers=response_headers)


@router.post("/agent/auto-enroll")
def auto_enroll(data: AutoEnrollmentRequest, request: Request, db: Session = Depends(get_db)):
    try:
        with service.transaction(db):
            result = automatic.register(db, data, request)
        return result
    except IntegrityError as exc:
        # Concurrent tickets can race for an as-yet-unseen identity. Unique
        # constraints roll back the entire device+agent+quota transaction.
        raise HTTPException(409, "같은 장비가 다른 요청에서 등록되었습니다. 기존 설정으로 업데이트하거나 관리자에게 문의해 주세요.") from exc


@router.get("/agents", response_model=AgentListResponse)
def list_agents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = service.utcnow()
    agents = db.scalars(select(DeviceAgent).order_by(DeviceAgent.created_at.desc())).all()
    return {"items": [service.agent_summary(agent, now) for agent in agents], "total": len(agents),
            "server_time": service.iso(now), "installer_formats": service.INSTALLER_FORMATS}


@router.get("/devices/{device_id}/agent", response_model=AgentDetailResponse)
def agent_detail(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    service.find_device(db, device_id)
    agent = service.find_agent(db, device_id)
    now = service.utcnow()
    commands = db.scalars(select(DeviceCommand).where(DeviceCommand.target_device_id == device_id)
                          .order_by(DeviceCommand.created_at.desc(), DeviceCommand.id.desc()).limit(20)).all()
    relays = [item for item in db.scalars(select(DeviceAgent)).all()
              if service.presence(item, now) == "online" and "wol-relay-v1" in (item.capabilities or [])]
    return {"agent": service.agent_summary(agent, now) if agent else None,
            "commands": [service.command_summary(command, now) for command in commands],
            "relay_devices": [service.agent_summary(item, now) for item in relays],
            "server_time": service.iso(now), "installer_formats": service.INSTALLER_FORMATS}


@router.post("/devices/{device_id}/agent/installer")
async def download_installer(device_id: int, data: InstallerRequest, request: Request,
                             db: Session = Depends(get_db), user: User = Depends(require_admin)):
    from app.services.agent_installer_service import build_agent_installer
    device = service.find_device(db, device_id)
    existing = service.find_agent(db, device_id)
    agent_id = existing.id if existing else str(uuid4())
    serial = device.serial_number
    bootstrap = secrets.token_urlsafe(32)
    connection = connection_service.configured_connection(request.base_url)
    connection["expectedServerId"] = connection_service.server_id(automatic.enrollment_key())
    config = {**connection, "deviceId": agent_id,
              "enrollmentToken": bootstrap, "heartbeatIntervalSeconds": service.HEARTBEAT_SECONDS}
    # Do not keep a database write lock while packaging, and never revoke the
    # current credential merely because another installer was downloaded.
    db.rollback()
    await connection_service.verify_public_readiness(connection)
    try:
        filename, content, mime = await run_in_threadpool(build_agent_installer, config=config, device_name=serial, format=data.format)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "설치 파일을 생성하지 못했습니다. 서버의 설치 파일 구성을 확인해 주세요.") from exc
    with service.transaction(db):
        device = service.find_device(db, device_id)
        agent = service.get_or_create_agent(db, device, agent_id)
        if agent.id != agent_id:
            raise HTTPException(409, "동시에 다른 등록이 생성되었습니다. 설치 파일을 다시 발급해 주세요.")
        now = service.utcnow()
        agent.enrollment_hash = service.token_hash(bootstrap)
        agent.enrollment_expires_at = now + timedelta(seconds=service.ENROLLMENT_SECONDS)
        agent.enrollment_consumed_at = None
        agent.enrolled_by_id = user.id
        service.audit(db, request, agent, "installer_issue", {"format": data.format}, user)
    return Response(content=content, media_type=mime, headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "X-Agent-Deployment-Mode": connection["deploymentMode"],
    })


@router.post("/agent/enroll")
def enroll(data: EnrollmentRequest, request: Request, db: Session = Depends(get_db)):
    with service.transaction(db):
        agent = db.get(DeviceAgent, str(data.deviceId))
        if agent is None or not service.matches_token(data.enrollmentToken, agent.enrollment_hash):
            raise HTTPException(401, "등록 코드가 일치하지 않습니다.")
        service.lock_agents(db, [agent.id])
        db.refresh(agent)
        if not service.matches_token(data.enrollmentToken, agent.enrollment_hash):
            raise HTTPException(401, "등록 코드가 일치하지 않습니다.")
        if agent.enrollment_consumed_at is not None:
            raise HTTPException(409, "등록 코드가 사용되었습니다. 새 설치 파일을 발급해 주세요.")
        now = service.utcnow()
        if agent.enrollment_expires_at is None or agent.enrollment_expires_at <= now:
            raise HTTPException(409, "등록 코드가 만료되었습니다. 새 설치 파일을 발급해 주세요.")
        token = secrets.token_urlsafe(32)
        agent.token_hash = service.token_hash(token)
        agent.enrollment_consumed_at = now
        agent.revoked_at = None
        service.reset_installation_lifecycle(agent)
        agent.last_seen_at = None
        agent.capabilities = []
        # Commands issued to the previous installation must not run under a new
        # enrollment, even though its stable agent identifier is retained.
        db.execute(update(DeviceCommand).where(DeviceCommand.executor_agent_id == agent.id,
                   DeviceCommand.status.in_(["pending", "delivered"]))
                   .values(status="expired", detail="reenrolled", updated_at=now))
        service.audit(db, request, agent, "enroll")
    return {"ok": True, "deviceId": agent.id, "deviceToken": token}


@router.post("/agent/heartbeat")
def heartbeat(data: HeartbeatRequest, request: Request, authorization: str | None = Header(default=None),
              db: Session = Depends(get_db)):
    with service.transaction(db):
        agent = service.authenticated_agent(db, data.deviceId, authorization)
        now = service.utcnow()
        # Heartbeat samples refresh live state every 15 seconds, but audit rows
        # describe changes/reconnections rather than every identical sample.
        network = observations.normalized_adapters([item.model_dump(mode="json") for item in data.networkAdapters]) if data.networkAdapters is not None else None
        changes = observations.observed_changes(agent, data, network, request, now)
        observations.record_network_observation(db, request, agent, network, now)
        agent.hostname = data.hostname
        agent.os_version = data.os
        agent.agent_version = data.agentVersion
        agent.boot_time = data.bootTime
        agent.last_seen_at = now
        agent.installation_state = "installed"
        agent.uninstalled_at = None
        # A heartbeat proves that a loaded worker is alive, not that its script
        # still exists on disk. Only the wrapper can clear worker_missing.
        if agent.service_state == "worker_stopped":
            agent.service_state = "running"
        agent.observed_ip = service.observed_ip(request)
        # Missing capabilities deliberately disable commands for an older or
        # downgraded agent. Missing network inventory retains its last snapshot.
        agent.capabilities = list(dict.fromkeys(data.capabilities))
        if data.networkAdapters is not None:
            agent.network_adapters = network
            agent.network_updated_at = now
        command = service.claim_command(db, agent, now)
        outgoing = [service.command_wire(command)] if command is not None else []
        if changes:
            service.audit(db, request, agent, "heartbeat_state_change", changes)
        if command is not None:
            service.audit(db, request, agent, "delivered", {"type": command.type}, command=command)
    return {"ok": True, "serverTime": service.iso(now), "heartbeatIntervalSeconds": service.HEARTBEAT_SECONDS, "commands": outgoing}


@router.post("/agent/service-health")
def service_health(data: ServiceHealthRequest, request: Request,
                   authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    with service.transaction(db):
        agent = service.authenticated_agent(db, data.deviceId, authorization)
        now = service.utcnow()
        prior_state = agent.service_state
        changed = prior_state != data.state
        agent.service_state = data.state
        agent.service_last_seen_at = now
        # The wrapper's health is independent of a successful worker heartbeat.
        # Do not refresh last_seen_at or deliver any executable command here.
        if changed:
            service.audit(db, request, agent, "service_state_change", {"service_state": {"old": prior_state, "new": data.state}})
    return {"ok": True, "serverTime": service.iso(now)}


@router.post("/agent/commands/{command_id}/ack")
def acknowledge(command_id: str, data: AckRequest, request: Request,
                authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    with service.transaction(db):
        agent = service.authenticated_agent(db, data.deviceId, authorization)
        now = service.utcnow()
        service.expire_commands(db, agent.id, now)
        command = db.get(DeviceCommand, command_id, populate_existing=True)
        if command is None or command.executor_agent_id != agent.id:
            raise HTTPException(404, "명령을 찾을 수 없습니다.")
        if command.expires_at <= now:
            raise HTTPException(409, "명령이 만료되었습니다.")
        if data.status == "accepted" and data.detail != "accepted":
            raise HTTPException(400, "수신 확인 값이 올바르지 않습니다.")
        if data.status == "failed" and data.detail in ("accepted", "packet_sent"):
            raise HTTPException(400, "실패 결과가 올바르지 않습니다.")
        if data.status == "succeeded" and (command.type != "wake" or data.detail != "packet_sent"):
            raise HTTPException(400, "WOL 패킷 전송 결과만 완료 확인할 수 있습니다.")
        result_status = "sent" if data.status == "succeeded" else data.status
        if command.status == result_status and command.detail == data.detail:
            return {"ok": True}
        if command.status not in ("delivered", "accepted"):
            raise HTTPException(409, "아직 전달되지 않았거나 이미 처리된 명령입니다.")
        if command.status == "accepted" and data.status == "accepted":
            raise HTTPException(409, "이미 수신한 명령입니다.")
        if data.status == "succeeded" and command.status != "accepted":
            raise HTTPException(409, "먼저 명령 수신을 확인해 주세요.")
        command.status = result_status
        command.detail = data.detail
        command.acknowledged_at = now
        if result_status in ("sent", "failed"):
            command.finished_at = now
        service.audit(db, request, agent, "acknowledge", {"status": result_status, "detail": data.detail}, command=command)
    return {"ok": True}


@router.post("/devices/{device_id}/agent/ip-review", response_model=AgentSummary)
def review_ip_incident(device_id: int, data: IpReviewRequest, request: Request,
                       db: Session = Depends(get_db), user: User = Depends(require_admin)):
    with service.transaction(db):
        # A fixed-IP edit and review resolution must have a defined order. Use
        # the same Device -> Agent lock order as registration and deletion.
        service.lock_device(db, device_id)
        device = service.find_device(db, device_id)
        db.refresh(device)
        agent = service.find_agent(db, device_id)
        if agent is None:
            raise HTTPException(404, "에이전트를 찾을 수 없습니다.")
        service.lock_agents(db, [agent.id])
        db.refresh(agent)
        monitor = agent.network_monitor or {}
        previous = monitor.get("review")
        if not isinstance(previous, dict) or previous.get("incident_id") != str(data.incidentId):
            raise HTTPException(409, "현재 IP 점검 건이 변경되었습니다. 최신 상태를 확인한 뒤 다시 시도해 주세요.")
        if previous.get("state") not in ("open", "reviewing"):
            raise HTTPException(409, "이미 조치 완료된 점검 건입니다.")
        now = service.utcnow()
        if data.action == "resolve":
            public_monitor = service.agent_summary(agent, now).get("network_monitor") or {}
            fresh = False
            try:
                checked = datetime.fromisoformat(monitor["checked_at"].replace("Z", "+00:00"))
                if checked.tzinfo is not None:
                    checked = checked.astimezone(timezone.utc).replace(tzinfo=None)
                    fresh = 0 <= (now - checked).total_seconds() < service.OFFLINE_SECONDS
            except (KeyError, TypeError, ValueError, AttributeError):
                pass
            if (not fresh or service.presence(agent, now) != "online" or monitor.get("status") != "normal"
                    or monitor.get("alert_active") or public_monitor.get("status") != "normal"
                    or public_monitor.get("stale", True) or public_monitor.get("reference_pending", False)):
                raise HTTPException(409, "온라인 PC의 최신 IP가 기준과 일치한 것을 확인한 후 조치 완료할 수 있습니다.")
        reviewed = {**previous, "state": "reviewing" if data.action == "start" else "resolved",
                    "note": data.note, "reviewed_by": user.name, "reviewed_at": service.iso(now)}
        agent.network_monitor = {**monitor, "review": reviewed}
        service.audit(db, request, agent, "ip_review_started" if data.action == "start" else "ip_review_resolved",
                      {"incident_id": str(data.incidentId), "review": {"old": previous, "new": reviewed}}, user)
    return service.agent_summary(agent, now)


@router.post("/devices/{device_id}/agent/power", status_code=202)
def power(device_id: int, data: PowerRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    with service.transaction(db):
        device = service.find_device(db, device_id)
        service.require_confirmation(data.confirmation, device)
        agent = service.find_agent(db, device_id)
        if agent is None:
            raise HTTPException(409, "먼저 에이전트를 설치해 주세요.")
        service.lock_agents(db, [agent.id])
        db.refresh(agent)
        now = service.utcnow()
        service.require_online(agent, "power-control-v1", now)
        active = db.scalar(select(DeviceCommand.id).where(
            DeviceCommand.executor_agent_id == agent.id, DeviceCommand.type.in_(["restart", "shutdown"]),
            DeviceCommand.status.in_(["pending", "delivered", "accepted"]), DeviceCommand.expires_at > now).limit(1))
        if active:
            raise HTTPException(409, "이미 처리 중인 전원 명령이 있습니다.")
        command = service.new_command(agent, device_id, data.action, user, now)
        db.add(command)
        service.audit(db, request, agent, "request", {"type": data.action}, user, command)
    return {"command": service.command_summary(command, now)}


@router.put("/devices/{device_id}/agent/wol")
def configure_wol(device_id: int, data: WolRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    with service.transaction(db):
        device = service.find_device(db, device_id)
        relay = service.find_agent(db, data.relayDeviceId)
        service.require_online(relay, "wol-relay-v1", service.utcnow())
        broadcast = service.relay_source(relay, data.sourceAddress)
        target = service.get_or_create_agent(db, device)
        target.wol = {"macAddress": data.macAddress, "relayDeviceId": data.relayDeviceId,
                      "sourceAddress": data.sourceAddress, "broadcastAddress": broadcast, "port": 9}
        service.audit(db, request, target, "wol_update", {"wol": target.wol}, user)
    return {"wol": target.wol}


@router.post("/devices/{device_id}/agent/wake", status_code=202)
def wake(device_id: int, data: WakeRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    with service.transaction(db):
        device = service.find_device(db, device_id)
        service.require_confirmation(data.confirmation, device)
        target = service.find_agent(db, device_id)
        if target is None or not target.wol:
            raise HTTPException(409, "먼저 대상 MAC과 중계 PC를 설정해 주세요.")
        relay = service.find_agent(db, target.wol["relayDeviceId"])
        if relay is None:
            raise HTTPException(409, "중계 PC를 다시 설정해 주세요.")
        relay_id = relay.id
        service.lock_agents(db, [target.id, relay_id])
        db.refresh(target)
        db.refresh(relay)
        if not target.wol or target.wol["relayDeviceId"] != relay.device_id:
            raise HTTPException(409, "WOL 설정이 변경되었습니다. 다시 시도해 주세요.")
        now = service.utcnow()
        service.require_online(relay, "wol-relay-v1", now)
        broadcast = service.relay_source(relay, target.wol["sourceAddress"])
        if broadcast != target.wol["broadcastAddress"]:
            raise HTTPException(409, "중계 PC 네트워크가 변경되었습니다. WOL 설정을 다시 저장해 주세요.")
        if target.last_wake_at is not None and (now - target.last_wake_at).total_seconds() < 20:
            raise HTTPException(429, "WOL 요청 후 20초가 지나야 다시 시도할 수 있습니다.")
        payload = {key: target.wol[key] for key in ("macAddress", "sourceAddress", "broadcastAddress", "port")}
        command = service.new_command(relay, device_id, "wake", user, now, payload)
        db.add(command)
        target.last_wake_at = now
        service.audit(db, request, target, "request", {"type": "wake", "relay_device_id": relay.device_id}, user, command)
    return {"command": service.command_summary(command, now)}


@router.delete("/devices/{device_id}/agent")
def revoke(device_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    with service.transaction(db):
        service.find_device(db, device_id)
        agent = service.find_agent(db, device_id)
        if agent is None:
            raise HTTPException(404, "에이전트를 찾을 수 없습니다.")
        service.lock_agents(db, [agent.id])
        db.refresh(agent)
        service.revoke_agent(db, agent, service.utcnow())
        service.audit(db, request, agent, "revoke", user=user)
    return {"ok": True}


@router.post("/devices/{device_id}/agent/uninstall-code")
def issue_uninstall_code(device_id: int, data: WakeRequest, request: Request,
                         db: Session = Depends(get_db), user: User = Depends(require_admin)):
    with service.transaction(db):
        device = service.find_device(db, device_id)
        service.require_confirmation(data.confirmation, device)
        agent = service.find_agent(db, device_id)
        if agent is None:
            raise HTTPException(404, "에이전트를 찾을 수 없습니다.")
        service.lock_agents(db, [agent.id])
        db.refresh(agent)
        code = secrets.token_urlsafe(32)
        agent.uninstall_code_hash = service.token_hash(code)
        agent.uninstall_code_expires_at = service.utcnow() + timedelta(seconds=900)
        agent.uninstall_requested_by_id = user.id
        expires_at = service.iso(agent.uninstall_code_expires_at)
        service.audit(db, request, agent, "uninstall_code_issue", {"expires_at": expires_at}, user)
    return {"code": code, "expires_at": expires_at}


@router.post("/agent/uninstall/authorize")
def authorize_uninstall(data: UninstallAuthorizationRequest, request: Request, db: Session = Depends(get_db)):
    with service.transaction(db):
        agent = db.get(DeviceAgent, str(data.deviceId))
        if agent is None or not service.matches_token(data.code, agent.uninstall_code_hash):
            raise HTTPException(401, "제거 승인 코드가 일치하지 않거나 이미 사용되었습니다.")
        service.lock_agents(db, [agent.id])
        db.refresh(agent)
        if not service.matches_token(data.code, agent.uninstall_code_hash):
            raise HTTPException(409, "제거 승인 코드가 이미 사용되었습니다. 새 코드를 발급해 주세요.")
        now = service.utcnow()
        if agent.uninstall_code_expires_at is None or agent.uninstall_code_expires_at <= now:
            raise HTTPException(409, "제거 승인 코드가 만료되었습니다. 새 코드를 발급해 주세요.")
        issuer = db.get(User, agent.uninstall_requested_by_id) if agent.uninstall_requested_by_id else None
        agent.uninstall_code_hash = None
        agent.uninstall_code_expires_at = None
        service.revoke_agent(db, agent, now)
        receipt = secrets.token_urlsafe(32)
        agent.completion_hash = service.token_hash(receipt)
        agent.completion_expires_at = now + timedelta(minutes=10)
        service.audit(db, request, agent, "uninstall_authorize", user=issuer)
    return {"ok": True, "receipt": receipt}


@router.post("/agent/uninstall/complete")
def complete_uninstall(data: UninstallCompletionRequest, request: Request, db: Session = Depends(get_db)):
    with service.transaction(db):
        agent = db.get(DeviceAgent, str(data.deviceId))
        if agent is None or not service.matches_token(data.receipt, agent.completion_hash):
            raise HTTPException(401, "제거 완료 확인 정보가 일치하지 않습니다.")
        service.lock_agents(db, [agent.id])
        db.refresh(agent)
        if not service.matches_token(data.receipt, agent.completion_hash):
            raise HTTPException(401, "제거 완료 확인 정보가 변경되었습니다.")
        if agent.installation_state == "uninstalled" and agent.uninstalled_at is not None:
            return {"ok": True}
        now = service.utcnow()
        if agent.completion_expires_at is None or agent.completion_expires_at <= now:
            raise HTTPException(409, "제거 완료 확인 정보가 만료되었습니다. 관리자에게 문의해 주세요.")
        agent.installation_state = "uninstalled"
        agent.uninstalled_at = now
        issuer = db.get(User, agent.uninstall_requested_by_id) if agent.uninstall_requested_by_id else None
        service.audit(db, request, agent, "uninstall_complete", user=issuer)
        # Keep only the hash to acknowledge a lost response idempotently. New
        # enrollment clears it, so an old receipt cannot remove a new install.
    return {"ok": True}
