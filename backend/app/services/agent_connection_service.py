"""Explicit public installer destinations and read-only production preflight."""
import ipaddress
import hashlib
import hmac
import re
from datetime import datetime
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from app.config import settings

LATEST_AGENT_VERSION = "0.5.0"
ALLOWED_API_PREFIXES = {"/api/v1/agent", "/manage/it/api/v1/agent"}
INTERNAL_READY_URL = "http://127.0.0.1:8818/api/v1/agent/ready"


def server_id(key):
    return hashlib.sha256(b"itam-agent-server-id-v1\0" + key).hexdigest()


def validated_public_server_id():
    """Check the externally verified pin locally; never performs HTTP.

    Keeping this synchronous gate separate lets /ready reject a changed key or
    missing pin without recursively requesting itself.
    """
    from app.services.auto_enrollment_service import enrollment_key
    pinned = settings.AGENT_PUBLIC_SERVER_ID
    if not isinstance(pinned, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", pinned):
        raise ValueError("Missing or invalid public server identity pin")
    pinned = pinned.lower()
    if not hmac.compare_digest(pinned, server_id(enrollment_key())):
        raise ValueError("Public server identity no longer matches this deployment")
    return pinned


def validate_connection(origin, prefix, mode):
    if mode not in ("production", "development") or prefix not in ALLOWED_API_PREFIXES:
        raise ValueError("Invalid agent deployment mode or API prefix")
    if not isinstance(origin, str) or not origin or re.search(r"[\x00-\x20\\]", origin):
        raise ValueError("An explicit origin is required")
    parsed = urlsplit(origin)
    host = parsed.hostname
    if not host or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Only a credential-free origin is allowed")
    parsed.port
    host = host.lower().rstrip(".")
    loopback = host == "localhost" or host.endswith(".localhost")
    unusable = False
    try:
        address = ipaddress.ip_address(host)
        mapped = getattr(address, "ipv4_mapped", None)
        loopback = loopback or address.is_loopback or bool(mapped and mapped.is_loopback)
        unusable = address.is_unspecified or address.is_multicast or bool(mapped and (mapped.is_unspecified or mapped.is_multicast))
    except ValueError:
        # Reject numeric aliases such as 127.1 / 2130706433 / 0x7f000001.
        if re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*", host):
            raise ValueError("Noncanonical numeric host")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
            raise ValueError("Invalid DNS host")
    if unusable or (mode == "production" and (parsed.scheme != "https" or loopback)):
        raise ValueError("Production requires a non-loopback HTTPS origin")
    if parsed.scheme != "https" and not (mode == "development" and parsed.scheme == "http" and loopback):
        raise ValueError("HTTP is allowed only for explicit local development")
    return {"serverUrl": f"{parsed.scheme}://{parsed.netloc}", "apiPrefix": prefix, "deploymentMode": mode}


def configured_connection(request_origin=None):
    mode = settings.AGENT_DEPLOYMENT_MODE
    origin = settings.AGENT_PUBLIC_URL
    if not origin and mode == "development":
        origin = str(request_origin or "").rstrip("/")
    try:
        connection = validate_connection(origin, settings.AGENT_API_PREFIX, mode)
        if mode == "production" and settings.AGENT_INTERNAL_READY_CHECK:
            validated_public_server_id()
        return connection
    except (ValueError, TypeError) as exc:
        raise HTTPException(503, "에이전트 공개 접속 주소 설정이 올바르지 않습니다. 운영 모드는 명시적인 HTTPS 주소와 API 경로가 필요하며 localhost를 사용할 수 없습니다.") from exc


async def verify_public_readiness(connection):
    """Only administrator-controlled configuration may choose this destination.
    No credentials, tokens or user payloads are sent, and redirects are refused.
    The dedicated-key fingerprint binds issuance to the configured deployment;
    administrators must keep that key private and unique to its database.
    """
    try:
        checked = validate_connection(connection["serverUrl"], connection["apiPrefix"], connection["deploymentMode"])
        if checked["deploymentMode"] != "production":
            return
        expected_server_id = connection.get("expectedServerId")
        if not isinstance(expected_server_id, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_server_id):
            raise ValueError("Missing issuer identity")
        url = checked["serverUrl"] + checked["apiPrefix"] + "/ready"
        if settings.AGENT_INTERNAL_READY_CHECK:
            # Public/native configuration remains the independently checked
            # HTTPS origin. Only this credential-free server-side probe changes.
            if checked != configured_connection() or not hmac.compare_digest(expected_server_id, validated_public_server_id()):
                raise ValueError("Internal probe is not bound to the verified public deployment")
            url = INTERNAL_READY_URL
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False, trust_env=False) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
        if response.status_code != 200:
            raise ValueError("Readiness HTTP failure")
        payload = response.json()
        if (not isinstance(payload, dict) or payload.get("product") != "app-it-manager-agent"
                or type(payload.get("protocol")) is not int or payload["protocol"] != 1
                or payload.get("registrationReady") is not True
                or payload.get("serverId") != expected_server_id
                or payload.get("latestAgentVersion") != LATEST_AGENT_VERSION):
            raise ValueError("Readiness protocol mismatch")
        instant = datetime.fromisoformat(payload["serverTime"].replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("Invalid readiness timestamp")
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(503, "운영 에이전트 등록 주소의 준비 상태를 확인하지 못했습니다. 공개 HTTPS 주소와 프록시 API 경로를 확인해 주세요.") from exc
