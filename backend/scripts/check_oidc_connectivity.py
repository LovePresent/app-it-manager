"""Credential-free OIDC connectivity checks with allowlisted output only.

GET responses establish transport reachability, never successful authentication.
No endpoint, response body, cookie, client identifier, code, or token is printed.
"""
import http.client
import json
import logging
import queue
import socket
import ssl
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit


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


def probe(label, url, metadata=False):
    if not url:
        print(json.dumps({"check": label, "result": "not_configured"}), flush=True)
        return None
    results = queue.Queue(maxsize=1)
    def run():
        try:
            results.put(fetch(url, metadata))
        except Exception as error:
            results.put(({"result": failure_code(error)}, None))
    # Bound DNS lookup as well as socket operations; stalled diagnostic threads
    # are daemon-only and cannot keep the diagnostic process alive on exit.
    threading.Thread(target=run, daemon=True).start()
    try:
        result, document = results.get(timeout=7)
    except queue.Empty:
        result, document = {"result": "timeout"}, None
    print(json.dumps({"check": label, **result}), flush=True)
    return document


def main():
    logging.disable(logging.CRITICAL)
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


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"check": "configuration", "result": failure_code(error)}), flush=True)
        sys.exit(1)
