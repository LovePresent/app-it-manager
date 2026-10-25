"""Credential-free OIDC connectivity checks with allowlisted output only.

GET responses establish transport reachability, never successful authentication.
No endpoint, response body, cookie, client identifier, code, or token is printed.
"""
import http.client
import ipaddress
import json
import logging
import queue
import socket
import ssl
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

FIXED_AUTH_HOST = "auth.cqv.kr"
FIXED_TOKEN_URL = "https://auth.cqv.kr/application/o/token/"


def failure_code(error):
    for kind, code in (
        (ssl.SSLCertVerificationError, "tls_certificate_error"),
        (ssl.SSLError, "tls_error"),
        (socket.gaierror, "dns_error"),
        (TimeoutError, "timeout"),
        (ConnectionRefusedError, "connection_refused"),
        (http.client.RemoteDisconnected, "remote_disconnected"),
        (ConnectionResetError, "connection_reset"),
        (http.client.HTTPException, "http_protocol_error"),
        (OSError, "connection_error"),
        (ValueError, "configuration_error"),
    ):
        if isinstance(error, kind):
            return code
    return "unexpected_error"


def failure_result(error):
    result = {"result": failure_code(error)}
    if isinstance(error, ssl.SSLCertVerificationError):
        code = getattr(error, "verify_code", None)
        if type(code) is int and 0 <= code <= 65535:
            result["sslverify_code"] = code
    return result


def fetch(url, metadata=False):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or any(ord(char) <= 32 for char in url)):
        raise ValueError("Invalid endpoint")
    connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
        timeout=5, context=ssl.create_default_context())
    try:
        # http.client does not use environment proxies, redirects or cookie jars.
        connection.request("GET", parsed.path or "/", headers={"Accept": "application/json", "Connection": "close"})
        response = connection.getresponse()
        document = None
        if metadata and response.status == 200:
            raw = response.read(65537)
            if len(raw) <= 65536:
                try:
                    document = json.loads(raw)
                except (ValueError, UnicodeError):
                    pass
        return {"result": "http_response", "httpStatus": response.status}, document
    finally:
        connection.close()


def report(label, operation):
    results = queue.Queue(maxsize=1)
    def run():
        try:
            results.put(operation())
        except Exception as error:
            results.put((failure_result(error), None))
    # Bound DNS lookup as well as socket operations; stalled diagnostic threads
    # are daemon-only and cannot keep the diagnostic process alive on exit.
    threading.Thread(target=run, daemon=True).start()
    try:
        result, document = results.get(timeout=7)
    except queue.Empty:
        result, document = {"result": "timeout"}, None
    print(json.dumps({"check": label, **result}), flush=True)
    return document


def probe(label, url, metadata=False):
    if not url:
        print(json.dumps({"check": label, "result": "not_configured"}), flush=True)
        return None
    return report(label, lambda: fetch(url, metadata))


def dns_counts(records):
    addresses = {ipaddress.ip_address(item[4][0].split("%", 1)[0]) for item in records}
    return {"result": "dns_resolved", "ipv4Count": sum(item.version == 4 for item in addresses),
        "ipv6Count": sum(item.version == 6 for item in addresses),
        "privateCount": sum(item.is_private for item in addresses),
        "globalCount": sum(item.is_global for item in addresses),
        "loopbackCount": sum(item.is_loopback for item in addresses),
        "linkLocalCount": sum(item.is_link_local for item in addresses)}


def fixed_dns():
    records = socket.getaddrinfo(FIXED_AUTH_HOST, 443, type=socket.SOCK_STREAM)
    return dns_counts(records), records


def fixed_family_tls(record):
    context = ssl.create_default_context()
    with socket.socket(record[0], socket.SOCK_STREAM) as plain:
        plain.settimeout(5)
        plain.connect(record[4])
        with context.wrap_socket(plain, server_hostname=FIXED_AUTH_HOST):
            return {"result": "tls_verified"}, None


def certificate_flags(der):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    certificate = x509.load_der_x509_certificate(der)
    try:
        names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        names = [item.value for item in certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)]
    names = [name.lower().rstrip(".") for name in names]
    covers = any(name == FIXED_AUTH_HOST or (name.startswith("*.") and FIXED_AUTH_HOST.endswith(name[1:])
        and name.count(".") == FIXED_AUTH_HOST.count(".")) for name in names)
    self_signed = False
    if certificate.subject == certificate.issuer:
        try:
            certificate.verify_directly_issued_by(certificate)
            self_signed = True
        except Exception:
            # No claim of a verified self-signature for an unsupported algorithm.
            self_signed = None
    return {"result": "certificate_metadata", "expired": certificate.not_valid_after_utc < datetime.now(timezone.utc),
        "issuerCloudflare": "cloudflare" in certificate.issuer.rfc4514_string().lower(),
        "selfSigned": self_signed, "hostnameCoversAuth": covers}


def inspect_fixed_peer_certificate():
    # Inspection ONLY: no HTTP request or credentials, no CA import or trust
    # changes. The separate verified probe still fails on an untrusted peer.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((FIXED_AUTH_HOST, 443), timeout=5) as plain:
        with context.wrap_socket(plain, server_hostname=FIXED_AUTH_HOST) as peer:
            return certificate_flags(peer.getpeercert(binary_form=True)), None


def fixed_public_diagnostics():
    records = report("auth_dns_categories", fixed_dns)
    if records is None:
        return
    for family, label in ((socket.AF_INET, "auth_public_ipv4_tls"), (socket.AF_INET6, "auth_public_ipv6_tls")):
        record = next((item for item in records if item[0] == family), None)
        if record is None:
            print(json.dumps({"check": label, "result": "address_family_unavailable"}), flush=True)
        else:
            report(label, lambda record=record: fixed_family_tls(record))


def main():
    logging.disable(logging.CRITICAL)
    if sys.argv[1:] == ["--gateway-tls-only"]:
        probe("docker_host_gateway_tls", FIXED_TOKEN_URL)
        report("docker_host_gateway_certificate", inspect_fixed_peer_certificate)
        return
    if len(sys.argv) != 1:
        raise ValueError("No arguments accepted")
    if not __file__.startswith("<"):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.config import settings
    base = settings.AUTHENTIK_BASE_URL.rstrip("/")
    document = probe("discovery", settings.oidc_discovery_url, metadata=True)
    probe("token_get", settings.AUTHENTIK_TOKEN_URL or base + "/application/o/token/")
    jwks = settings.AUTHENTIK_JWKS_URL
    if not jwks and isinstance(document, dict) and isinstance(document.get("jwks_uri"), str):
        jwks = document["jwks_uri"]
    probe("jwks", jwks)
    probe("authorize_get", settings.AUTHENTIK_AUTHORIZE_URL or base + "/application/o/authorize/")
    probe("userinfo_get", settings.AUTHENTIK_USERINFO_URL)
    fixed_public_diagnostics()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"check": "configuration", **failure_result(error)}), flush=True)
        sys.exit(1)
