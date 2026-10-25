"""Record observed changes without altering the manually maintained inventory.

An agent snapshot proves an observed state, not an attempted Windows setting
change. Ordering-only differences and repeated unchanged samples are ignored.
"""
import ipaddress
import json
import re
from datetime import datetime
from uuid import uuid4

from app.models.notification import Notification
from app.models.ip_address import IPChangeHistory
from app.services import device_agent_service as service


def normalized_adapters(adapters):
    result = []
    for item in adapters or []:
        result.append({**item,
            "ipv4": sorted(item.get("ipv4", []), key=lambda entry: (entry["address"], entry["netmask"])),
            "ipv6": sorted(set(item.get("ipv6", []))),
        })
    return sorted(result, key=lambda item: item["id"])


def observed_changes(agent, data, network, request, now):
    missing_is_current = (agent.service_state == "worker_missing" and agent.service_last_seen_at is not None
                          and 0 <= (now - agent.service_last_seen_at).total_seconds() < service.OFFLINE_SECONDS)
    before = {"hostname": agent.hostname, "os_version": agent.os_version,
        "agent_version": agent.agent_version, "boot_time": service.iso(agent.boot_time),
        "capabilities": sorted(agent.capabilities or []),
        "observed_ip": agent.observed_ip, "connection_state": service.presence(agent, now),
        "installation_state": agent.installation_state,
        "service_state": agent.service_state}
    after = {"hostname": data.hostname, "os_version": data.os,
        "agent_version": data.agentVersion, "boot_time": service.iso(data.bootTime),
        "capabilities": sorted(set(data.capabilities)),
        "observed_ip": service.observed_ip(request), "connection_state": "worker_missing" if missing_is_current else "online",
        "installation_state": "installed",
        "service_state": "running" if agent.service_state == "worker_stopped" else agent.service_state}
    if network is not None:
        before["network_adapters"] = normalized_adapters(agent.network_adapters)
        after["network_adapters"] = network
    return {field: {"old": before[field], "new": value}
            for field, value in after.items() if before[field] != value}


def usable_ipv4(value):
    try:
        address = ipaddress.IPv4Address(value)
        if not (address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified):
            return str(address)
    except (ValueError, TypeError):
        pass
    return None


def expected_inventory_ipv4(value):
    values = re.split(r"[,;\s]+", (value or "").strip())
    result = set()
    for item in values:
        if not item:
            continue
        try:
            normalized = usable_ipv4(str(ipaddress.IPv4Interface(item).ip))
        except ValueError:
            return None
        if normalized is None:
            return None
        result.add(normalized)
    return sorted(result)


def record_ip_history(db, agent, network, now):
    before = {item["id"]: item for item in normalized_adapters(agent.network_adapters)}
    after = {item["id"]: item for item in network}
    for adapter_id in sorted(before.keys() | after.keys()):
        old, new = before.get(adapter_id, {}), after.get(adapter_id, {})
        keys = ("ipv4", "ipv6", "macAddress")
        if all(old.get(key) == new.get(key) for key in keys):
            continue
        def addresses(item):
            return ", ".join([entry["address"] for entry in item.get("ipv4", [])] + item.get("ipv6", [])) or None
        old_ip, new_ip = addresses(old), addresses(new)
        if not any((old_ip, new_ip, old.get("macAddress"), new.get("macAddress"))):
            continue
        device = agent.device
        details = {"adapter_id": adapter_id, "adapter_name": new.get("name") or old.get("name"),
                   "reference_ip": device.ip_address, "before": old, "after": new}
        db.add(IPChangeHistory(source_type="agent", source_id=device.id, device_id=device.id,
            old_serial_number=device.serial_number, new_serial_number=device.serial_number,
            user_name=device.user_name, employee_number=device.employee_number,
            old_ip_address=old_ip, new_ip_address=new_ip,
            old_mac_address=old.get("macAddress"), new_mac_address=new.get("macAddress"),
            change_reason="에이전트 최초 IP/MAC 확인" if not before else "에이전트 IP/MAC 관측 변경",
            notes="장비 관측 기록 (변경 시도·작업자 확인 아님). " + json.dumps(details, ensure_ascii=False),
            created_at=now))


def record_network_observation(db, request, agent, network, now):
    if network is None:
        return
    record_ip_history(db, agent, network, now)
    previous = agent.network_monitor or {}
    actual = sorted({value for adapter in network if adapter.get("physical") is True
                     for entry in adapter.get("ipv4", [])
                     if (value := usable_ipv4(entry.get("address")))})
    baseline = previous.get("baseline_ipv4") or []
    if not baseline and actual:
        baseline = actual
        service.audit(db, request, agent, "ip_baseline_recorded",
                      {"baseline_ipv4": {"old": [], "new": baseline}})
    configured = expected_inventory_ipv4(agent.device.ip_address)
    has_reference = bool((agent.device.ip_address or "").strip())
    invalid_reference = has_reference and configured is None
    expected = (configured or []) if has_reference else baseline
    source = "inventory" if has_reference else "first_seen" if baseline else "unconfigured"
    reference_changed = bool(previous) and (previous.get("expected_ipv4") != expected or previous.get("source") != source)
    if reference_changed:
        service.audit(db, request, agent, "ip_monitoring_reference_changed", {
            "expected_ipv4": {"old": previous.get("expected_ipv4", []), "new": expected},
            "source": {"old": previous.get("source"), "new": source}})
    status = "unknown" if not actual or not expected else (
        "normal" if (set(expected).issubset(actual) if configured else expected == actual) else "mismatch")
    # Missing samples neither prove recovery nor erase an unresolved incident.
    alert_active = bool(previous.get("alert_active"))
    review = previous.get("review")
    incident = previous.get("incident")
    signature = json.dumps([expected, actual, source], separators=(",", ":"))
    if status == "mismatch" and (not alert_active or incident != signature):
        service.audit(db, request, agent, "ip_mismatch_detected", {
            "expected_ipv4": expected, "observed_ipv4": actual, "source": source,
            "evidence": "agent_snapshot",
        })
        db.add(Notification(type="ip_mismatch", entity_type="device", entity_id=agent.device_id,
            title=f"IP 변경 확인 필요: {agent.device.serial_number}",
            message=f"기준 IP {', '.join(expected)} / 확인된 IP {', '.join(actual)}. "
                    "장비의 실제 IP가 기준과 다릅니다. 변경 시도나 작업자를 확인한 것은 아닙니다.",
            created_at=now))
        alert_active = True
        incident = signature
        review = {"incident_id": str(uuid4()), "state": "open", "note": None,
                  "reviewed_by": None, "reviewed_at": None}
    elif status == "normal" and alert_active:
        try:
            incident_expected, _, incident_source = json.loads(incident)
            incident_reference_changed = incident_expected != expected or incident_source != source
        except (ValueError, TypeError):
            incident_reference_changed = True
        event = "ip_reference_resolved" if incident_reference_changed else "ip_restored"
        service.audit(db, request, agent, event, {
            "expected_ipv4": expected, "observed_ipv4": actual, "source": source})
        db.add(Notification(type=event, entity_type="device", entity_id=agent.device_id,
            title=f"{'변경된 기준 IP 일치' if incident_reference_changed else '기준 IP 복구 확인'}: {agent.device.serial_number}",
            message=(f"기준이 변경되어 확인된 IP({', '.join(actual)})와 일치합니다. PC의 IP 복구로 판단하지 않습니다."
                     if incident_reference_changed else f"확인된 IP가 기존 기준 IP({', '.join(expected)})와 다시 일치합니다."),
            created_at=now))
        alert_active = False
        incident = None
    agent.network_monitor = {"status": status, "source": source, "expected_ipv4": expected,
        "observed_ipv4": actual, "baseline_ipv4": baseline, "checked_at": service.iso(now),
        "alert_active": alert_active, "incident": incident, "reference_error": invalid_reference,
        "review": review}


def public_monitor(agent, now=None):
    monitor = agent.network_monitor
    if not monitor:
        return None
    result = {key: value for key, value in monitor.items() if key != "incident"}
    now = now or service.utcnow()
    try:
        checked = datetime.fromisoformat(monitor["checked_at"].replace("Z", "+00:00")).replace(tzinfo=None)
        fresh = 0 <= (now - checked).total_seconds() < service.OFFLINE_SECONDS
    except (KeyError, ValueError, TypeError):
        fresh = False
    configured = expected_inventory_ipv4(agent.device.ip_address)
    has_reference = bool((agent.device.ip_address or "").strip())
    current_expected = (configured or []) if has_reference else monitor.get("baseline_ipv4", [])
    current_source = "inventory" if has_reference else "first_seen" if current_expected else "unconfigured"
    reference_pending = (configured is None or current_expected != monitor.get("expected_ipv4")
                         or current_source != monitor.get("source"))
    result["reference_pending"] = reference_pending
    result["reference_error"] = has_reference and configured is None
    fresh = fresh and not reference_pending
    fresh = fresh and service.presence(agent, now) == "online"
    result["last_status"] = monitor.get("status", "unknown")
    result["stale"] = not fresh
    if not fresh:
        result["status"] = "unknown"
    return result
