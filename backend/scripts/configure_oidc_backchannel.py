"""Verify and manage a private, backend-only OIDC DNS override.

Only fixed HTTPS SNI/Host auth.cqv.kr is used. Candidate addresses and credentials
never enter output. No database, application authentication setting, or trust
store is modified. Deployment rollback owns the narrow override lifecycle.
"""
import base64
import hashlib
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

OWNER = "AppITManagerOidcBackchannel/1"
HOST = "auth.cqv.kr"
OVERRIDE = "docker-compose.override.yml"
ALTERNATE_OVERRIDES = ("compose.override.yaml", "compose.override.yml", "docker-compose.override.yaml")
ACTIVE = ".agent-oidc-backchannel-active"
LIMIT = 32768
STATE_LIMIT = 65536  # Base64 of a full-size override plus bounded JSON metadata.


class Rejected(Exception):
    def __init__(self, code):
        self.code = code


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise Rejected("invalid_managed_state")
        value[key] = item
    return value


def candidate_address(value):
    try:
        address = ipaddress.IPv4Address(value)
        if not any(address in ipaddress.IPv4Network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
            raise ValueError()
        return str(address)
    except (ValueError, TypeError):
        raise Rejected("candidate_must_be_private_ipv4") from None


def read_regular(path, missing=True, limit=LIMIT):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing:
            return None
        raise Rejected("managed_state_missing") from None
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise Rejected("unexpected_file_type_or_size")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        result = stream.read(limit + 1)
    if len(result) > limit:
        raise Rejected("unexpected_file_type_or_size")
    return result


def read_candidate(root, environment=None):
    environment = os.environ if environment is None else environment
    value = environment.get("ITAM_SSO_CANDIDATE_IP", "").strip()
    if not value:
        raw = read_regular(root / ".env")
        values = []
        for line in raw.decode("utf-8-sig").splitlines() if raw else []:
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, item = line.partition("=")
            if separator and key.strip() == "AUTHENTIK_BACKCHANNEL_IP":
                item = item.strip()
                if item[:1] in ("'", '"'):
                    if len(item) < 2 or item[-1:] != item[:1]:
                        raise Rejected("candidate_setting_invalid")
                    item = item[1:-1]
                else:
                    item = item.split("#", 1)[0].strip()
                values.append(item)
        if len(values) > 1:
            raise Rejected("candidate_setting_ambiguous")
        value = values[0] if values else ""
    return candidate_address(value) if value else None


def override_bytes(candidate):
    return (json.dumps({"x-itam-oidc-backchannel": OWNER,
        "services": {"backend": {"extra_hosts": {HOST: candidate_address(candidate)}}}},
        sort_keys=True, indent=2) + "\n").encode()


def owned_override(raw):
    if raw is None:
        return None
    try:
        value = json.loads(raw, object_pairs_hook=unique_object)
        if (set(value) != {"x-itam-oidc-backchannel", "services"}
                or value["x-itam-oidc-backchannel"] != OWNER
                or set(value["services"]) != {"backend"}
                or set(value["services"]["backend"]) != {"extra_hosts"}
                or set(value["services"]["backend"]["extra_hosts"]) != {HOST}):
            raise ValueError()
        return candidate_address(value["services"]["backend"]["extra_hosts"][HOST])
    except Exception:
        raise Rejected("unrecognized_compose_override_preserved") from None


def ensure_override_scope(root):
    for name in ALTERNATE_OVERRIDES:
        path = root / name
        if path.exists() or path.is_symlink():
            raise Rejected("alternate_compose_override_preserved")


PROBE_SOURCE = r'''
import http.client, ipaddress, json, socket, ssl, sys
from urllib.parse import urlsplit
HOST = 'auth.cqv.kr'
NORMAL_DNS = False
def endpoint(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.hostname != HOST or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or any(ord(char) <= 32 for char in value)):
        raise ValueError('endpoint_configuration')
    return parsed.path or '/'
def get(value, candidate, document=False):
    path = endpoint(value)
    context = ssl.create_default_context()
    connection = http.client.HTTPSConnection(HOST, 443, timeout=5, context=context)
    try:
        if NORMAL_DNS:
            addresses = {item[4][0] for item in socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)}
            if addresses != {candidate}:
                raise ValueError('running_route_mismatch')
        else:
            plain = socket.create_connection((candidate, 443), timeout=5)
            try:
                connection.sock = context.wrap_socket(plain, server_hostname=HOST)
            except Exception:
                plain.close()
                raise
        connection.request('GET', path, headers={'Host':HOST,'Accept':'application/json','Connection':'close'})
        response = connection.getresponse()
        body = None
        if document and response.status == 200:
            raw = response.read(65537)
            if len(raw) > 65536: raise ValueError('response_too_large')
            body = json.loads(raw)
        return response.status, body
    finally:
        connection.close()
try:
    from app.config import settings
    parameters = json.load(sys.stdin)
    candidate = str(ipaddress.IPv4Address(parameters['candidate']))
    NORMAL_DNS = parameters.get('verify_running') is True
    token = settings.AUTHENTIK_TOKEN_URL or settings.AUTHENTIK_BASE_URL.rstrip('/') + '/application/o/token/'
    status, _ = get(token, candidate)
    if status not in (400, 405): raise ValueError('token_endpoint_status')
    jwks = settings.AUTHENTIK_JWKS_URL
    if not jwks:
        status, metadata = get(settings.oidc_discovery_url, candidate, True)
        if status != 200 or not isinstance(metadata, dict) or not isinstance(metadata.get('jwks_uri'), str):
            raise ValueError('discovery_response')
        jwks = metadata['jwks_uri']
    status, keys = get(jwks, candidate, True)
    if (status != 200 or not isinstance(keys, dict) or not isinstance(keys.get('keys'), list)
            or not keys['keys'] or len(keys['keys']) > 100
            or not any(isinstance(key, dict) and key.get('kty') == 'RSA'
                and all(isinstance(key.get(field), str) and 0 < len(key[field]) <= 8192 for field in ('kid','n','e'))
                for key in keys['keys'])):
        raise ValueError('jwks_response')
    print(json.dumps({'ok':True,'result':'tls_token_jwks_verified'}))
except Exception as error:
    result = 'tls_certificate_error' if isinstance(error, ssl.SSLCertVerificationError) else 'tls_error' if isinstance(error, ssl.SSLError) else 'timeout' if isinstance(error, TimeoutError) else 'connection_error' if isinstance(error, OSError) else 'running_route_mismatch' if isinstance(error, ValueError) and error.args == ('running_route_mismatch',) else 'endpoint_check_failed'
    print(json.dumps({'ok':False,'result':result}))
    sys.exit(1)
'''


def probe_candidate(root, candidate, run=subprocess.run, normal_dns=False):
    try:
        selected = run(["docker", "compose", "ps", "-q", "backend"], cwd=root,
            capture_output=True, text=True, timeout=10)
        container = selected.stdout.strip()
        if selected.returncode or not re.fullmatch(r"[0-9a-f]{12,64}", container):
            raise Rejected("running_backend_required")
        checked = run(["docker", "exec", "-i", "-w", "/app", container, "python", "-c", PROBE_SOURCE],
            input=json.dumps({"candidate": candidate, "verify_running": normal_dns}), cwd=root, capture_output=True, text=True, timeout=25)
        if len(checked.stdout) > 4096:
            raise Rejected("invalid_probe_result")
        result = json.loads(checked.stdout)
        if checked.returncode or result != {"ok": True, "result": "tls_token_jwks_verified"}:
            reason = result.get("result") if isinstance(result, dict) else None
            allowed = {"tls_certificate_error", "tls_error", "timeout", "connection_error", "endpoint_check_failed", "running_route_mismatch"}
            raise Rejected(reason if reason in allowed else "invalid_probe_result")
    except subprocess.TimeoutExpired:
        raise Rejected("probe_timeout") from None
    except Rejected:
        raise
    except Exception:
        raise Rejected("probe_unavailable") from None


def run_identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,30}(?:-[0-9]{1,6})?", value):
        raise Rejected("deployment_run_id_required")
    return value


def checksum(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_unlink(path):
    path.unlink()
    sync_directory(path.parent)


def private_write(path, raw, replace=False, limit=LIMIT):
    if len(raw) > limit:
        raise Rejected("managed_state_too_large")
    # A killed process may leave its private temporary file. A fresh exclusive
    # name avoids blocking recovery and never reuses or deletes that stale file.
    descriptor, temporary_name = tempfile.mkstemp(prefix=".itam-oidc-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if not replace and path.exists():
            raise Rejected("managed_state_already_exists")
        read_regular(path, limit=limit)
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if temporary.exists() and not temporary.is_symlink():
            durable_unlink(temporary)


@contextmanager
def operation_lock(root):
    import fcntl
    backups = root / "backups"
    if backups.exists() and (backups.is_symlink() or not backups.is_dir()):
        raise Rejected("unsafe_backup_directory")
    backups.mkdir(mode=0o700, exist_ok=True)
    # Persist a newly created backup directory before any backup/marker/override.
    sync_directory(root)
    descriptor = os.open(backups / ".oidc-backchannel.lock", os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield backups
    finally:
        os.close(descriptor)


def read_state(root, run_id):
    raw = read_regular(root / ACTIVE)
    if raw is None:
        return None
    try:
        marker = json.loads(raw, object_pairs_hook=unique_object)
        if marker != {"owner": OWNER, "run_id": run_id}:
            raise Rejected("another_backchannel_operation_active")
        path = root / "backups" / ("oidc-backchannel-" + run_id + ".json")
        state = json.loads(read_regular(path, missing=False, limit=STATE_LIMIT), object_pairs_hook=unique_object)
        if (set(state) != {"owner", "run_id", "before", "after_sha256"} or state["owner"] != OWNER
                or state["run_id"] != run_id or not re.fullmatch(r"[a-f0-9]{64}", state["after_sha256"])):
            raise ValueError()
        previous = base64.b64decode(state["before"], validate=True) if state["before"] is not None else None
        if previous is not None and len(previous) > LIMIT:
            raise ValueError()
        owned_override(previous)
        return state, previous
    except Rejected:
        raise
    except Exception:
        raise Rejected("invalid_managed_state") from None


def check(root, candidate, probe=probe_candidate):
    if candidate is None:
        return "no_candidate_unchanged"
    ensure_override_scope(root)
    owned_override(read_regular(root / OVERRIDE))
    probe(root, candidate)
    return "verified"


def apply(root, candidate, run_id, probe=probe_candidate):
    if candidate is None:
        return "no_candidate_unchanged"
    ensure_override_scope(root)
    run_id = run_identifier(run_id)
    candidate = candidate_address(candidate)
    with operation_lock(root) as backups:
        current = read_regular(root / OVERRIDE)
        owned_override(current)
        intended = override_bytes(candidate)
        active = read_state(root, run_id)
        if active is not None:
            state, previous = active
            if state["after_sha256"] != checksum(intended) or checksum(current) not in {checksum(previous), checksum(intended)}:
                raise Rejected("managed_override_changed")
            probe(root, candidate)
            if checksum(current) != checksum(intended):
                private_write(root / OVERRIDE, intended, replace=current is not None)
            return "already_applied"
        probe(root, candidate)
        if current is not None and owned_override(current) == candidate:
            return "verified_existing_route_unchanged"
        state_path = backups / ("oidc-backchannel-" + run_id + ".json")
        state = {"owner": OWNER, "run_id": run_id, "before": base64.b64encode(current).decode() if current is not None else None,
                 "after_sha256": checksum(intended)}
        state_bytes = (json.dumps(state) + "\n").encode()
        if len(state_bytes) > STATE_LIMIT:
            raise Rejected("managed_state_too_large")
        prior_backup = read_regular(state_path, limit=STATE_LIMIT)
        if prior_backup is not None:
            if json.loads(prior_backup, object_pairs_hook=unique_object) != state:
                raise Rejected("deployment_run_backup_conflict")
        else:
            private_write(state_path, state_bytes, limit=STATE_LIMIT)
        private_write(root / ACTIVE, (json.dumps({"owner": OWNER, "run_id": run_id}) + "\n").encode())
        private_write(root / OVERRIDE, intended, replace=current is not None)
        return "applied"


def restore(root, run_id):
    run_id = run_identifier(run_id)
    if read_regular(root / ACTIVE) is None:
        return "no_managed_change"
    with operation_lock(root):
        state, previous = read_state(root, run_id)
        current = read_regular(root / OVERRIDE)
        owned_override(current)
        if checksum(current) == checksum(previous):
            durable_unlink(root / ACTIVE)
            return "already_restored"
        if checksum(current) != state["after_sha256"]:
            raise Rejected("managed_override_changed")
        if previous is None:
            durable_unlink(root / OVERRIDE)
        else:
            private_write(root / OVERRIDE, previous, replace=True)
        durable_unlink(root / ACTIVE)
        return "restored"


def finalize(root, run_id):
    run_id = run_identifier(run_id)
    if read_regular(root / ACTIVE) is None:
        return "no_managed_change"
    with operation_lock(root):
        state, _ = read_state(root, run_id)
        current = read_regular(root / OVERRIDE)
        owned_override(current)
        if checksum(current) != state["after_sha256"]:
            raise Rejected("managed_override_changed")
        durable_unlink(root / ACTIVE)
        return "finalized_backup_preserved"


def verify_running(root, candidate, probe=probe_candidate):
    if candidate is None:
        try:
            candidate = owned_override(read_regular(root / OVERRIDE))
        except Rejected:
            return "no_managed_route_unchanged"
    if candidate is None:
        return "no_candidate_unchanged"
    ensure_override_scope(root)
    probe(root, candidate, normal_dns=True)
    return "running_route_verified"


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"--check", "--apply", "--restore", "--finalize", "--verify-running"}:
        raise Rejected("invalid_operation")
    root = Path(__file__).resolve().parents[2]
    mode = sys.argv[1]
    if mode in {"--check", "--apply", "--verify-running"}:
        candidate = read_candidate(root)
        result = check(root, candidate) if mode == "--check" else verify_running(root, candidate) if mode == "--verify-running" else apply(root, candidate, os.environ.get("DEPLOY_RUN_ID"))
    else:
        result = restore(root, os.environ.get("DEPLOY_RUN_ID")) if mode == "--restore" else finalize(root, os.environ.get("DEPLOY_RUN_ID"))
    print(json.dumps({"operation": mode[2:], "result": result}))


if __name__ == "__main__":
    try:
        main()
    except Rejected as error:
        print(json.dumps({"result": "rejected", "reason": error.code}))
        sys.exit(1)
    except Exception:
        print(json.dumps({"result": "rejected", "reason": "operation_failed"}))
        sys.exit(1)
