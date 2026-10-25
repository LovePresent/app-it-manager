"""Production destination/readiness checks use mock HTTPS and fake PE assets."""
import hashlib
import json
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select

from app.main import app
from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.auto_enrollment_ticket import AutoEnrollmentTicket
from app.models.device_agent import DeviceAgent
from app.services import agent_connection_service as connection
from app.services import agent_installer_service as installers
from tests.test_device_agents import AgentApiFixture

ORIGIN = "https://dev.cqv.kr"
PREFIX = "/manage/it/api/v1/agent"
SERVER_ID = connection.server_id(bytes(range(32)))


class AgentConnectionValidationTest(unittest.TestCase):
    def test_production_accepts_only_explicit_https_nonloopback_origins_and_known_prefixes(self):
        for prefix in ("/api/v1/agent", PREFIX):
            value = connection.validate_connection(ORIGIN, prefix, "production")
            self.assertEqual(value, {"serverUrl": ORIGIN, "apiPrefix": prefix, "deploymentMode": "production"})
        for origin in ("", "http://dev.cqv.kr", "https://localhost", "https://localhost.", "https://api.localhost",
                       "https://127.0.0.1", "https://127.0.0.2", "https://[::1]", "https://[::ffff:127.0.0.1]",
                       "https://0.0.0.0", "https://[::]", "https://127.1", "https://2130706433", "https://0x7f000001", "https://0x7f.0.0.1",
                       "https://user:pass@dev.cqv.kr", ORIGIN + "/manage/it", ORIGIN + "/?x=1", ORIGIN + "/#x"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                connection.validate_connection(origin, PREFIX, "production")
        for prefix in ("", "/", "/api/v1/agent/", "/manage/it/../api/v1/agent", "https://evil.invalid/api"):
            with self.assertRaises(ValueError):
                connection.validate_connection(ORIGIN, prefix, "production")

    def test_production_does_not_fall_back_to_request_host_but_explicit_development_can(self):
        with patch.object(settings, "AGENT_PUBLIC_URL", ""), patch.object(settings, "AGENT_API_PREFIX", "/api/v1/agent"):
            with patch.object(settings, "AGENT_DEPLOYMENT_MODE", "production"), self.assertRaises(HTTPException) as rejected:
                connection.configured_connection(ORIGIN)
            self.assertEqual(rejected.exception.status_code, 503)
            with patch.object(settings, "AGENT_DEPLOYMENT_MODE", "development"):
                value = connection.configured_connection("http://localhost:3000/")
                self.assertEqual(value["serverUrl"], "http://localhost:3000")
                self.assertEqual(value["deploymentMode"], "development")


class ProductionReadinessProbeTest(unittest.IsolatedAsyncioTestCase):
    def config(self):
        return {"serverUrl": ORIGIN, "apiPrefix": PREFIX, "deploymentMode": "production", "expectedServerId": SERVER_ID}

    def payload(self):
        return {"product": "app-it-manager-agent", "protocol": 1, "registrationReady": True,
                "serverTime": "2026-10-25T03:00:00.000Z", "latestAgentVersion": "0.5.0", "serverId": SERVER_ID}

    async def run_probe(self, handler):
        real_client = httpx.AsyncClient
        options = []
        def client(**kwargs):
            options.append(kwargs)
            return real_client(transport=httpx.MockTransport(handler), **kwargs)
        with patch.object(connection.httpx, "AsyncClient", side_effect=client):
            await connection.verify_public_readiness(self.config())
        return options

    async def test_probe_uses_only_configured_ready_url_without_credentials_or_redirects(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=self.payload())
        options = await self.run_probe(handler)
        self.assertEqual(str(requests[0].url), ORIGIN + PREFIX + "/ready")
        self.assertEqual(requests[0].method, "GET")
        self.assertNotIn("authorization", requests[0].headers)
        self.assertFalse(options[0]["follow_redirects"])
        self.assertFalse(options[0]["trust_env"])

    async def test_redirects_wrong_server_identity_old_version_and_unready_responses_are_rejected(self):
        cases = [(302, self.payload()), (503, self.payload())]
        for field, value in (("product", "other-app"), ("protocol", "1"), ("protocol", True),
                             ("registrationReady", False), ("serverId", "0" * 64),
                             ("latestAgentVersion", "0.4.0"), ("serverTime", "not-a-time")):
            cases.append((200, {**self.payload(), field: value}))
        for status, payload in cases:
            with self.subTest(status=status, payload=payload), self.assertRaises(HTTPException) as rejected:
                await self.run_probe(lambda request: httpx.Response(status, json=payload, headers={"Location": "/login"}))
            self.assertEqual(rejected.exception.status_code, 503)
        with self.assertRaises(HTTPException) as rejected:
            await self.run_probe(lambda request: (_ for _ in ()).throw(httpx.ConnectError("private socket diagnostic")))
        self.assertNotIn("private socket diagnostic", rejected.exception.detail)

    async def test_development_never_performs_an_external_probe(self):
        with patch.object(connection.httpx, "AsyncClient", side_effect=AssertionError("Unexpected external request")):
            await connection.verify_public_readiness({"serverUrl": "http://localhost:3000", "apiPrefix": "/api/v1/agent", "deploymentMode": "development"})


class AgentProductionApiTest(AgentApiFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.package_patch = patch("app.services.agent_installer_service.verify_package_ready", return_value=None)
        self.package_ready = self.package_patch.start()

    def tearDown(self):
        self.package_patch.stop()
        super().tearDown()

    def test_public_ready_is_readonly_and_reports_only_protocol_and_nonsecret_identity(self):
        app.dependency_overrides.pop(get_current_user)
        response = self.client.get("/api/v1/agent/ready")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"product": "app-it-manager-agent", "protocol": 1,
            "serverTime": "2026-10-25T03:00:00.000Z", "registrationReady": True,
            "latestAgentVersion": "0.5.0", "serverId": SERVER_ID})
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.builder.call_count, 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(DeviceAgent)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(AutoEnrollmentTicket)), 0)

    def test_unready_database_key_or_package_returns_generic_public_failure(self):
        self.package_ready.side_effect = RuntimeError("private package path")
        response = self.client.get("/api/v1/agent/ready")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["registrationReady"])
        self.assertNotIn("private", response.text)
        self.package_ready.side_effect = None
        self.server_key_path.unlink()
        response = self.client.get("/api/v1/agent/ready")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.server_key_path), response.text)
        self.server_key_path.write_bytes(bytes(range(32)))
        broken = Mock()
        broken.execute.side_effect = RuntimeError("secret database diagnostic")
        app.dependency_overrides[get_db] = lambda: broken
        response = self.client.get("/api/v1/agent/ready")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", response.text)

    def test_invalid_production_configuration_is_blocked_before_packaging_or_ticket_writes(self):
        with patch.object(settings, "AGENT_DEPLOYMENT_MODE", "production"):
            for origin in ("", "http://localhost:3000", "https://localhost", "http://dev.cqv.kr"):
                with patch.object(settings, "AGENT_PUBLIC_URL", origin):
                    self.assertEqual(self.client.post("/api/v1/agents/auto-installer", json={}).status_code, 503)
                    self.assertEqual(self.client.post(f"/api/v1/devices/{self.device.id}/agent/installer", json={}).status_code, 503)
        self.assertEqual(self.builder.call_count, 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(DeviceAgent)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(AutoEnrollmentTicket)), 0)

    def test_production_installers_embed_confirmed_origin_prefix_mode_and_issuer_id(self):
        probe = AsyncMock()
        with patch.object(settings, "AGENT_DEPLOYMENT_MODE", "production"), patch.object(settings, "AGENT_PUBLIC_URL", ORIGIN), patch.object(settings, "AGENT_API_PREFIX", PREFIX), patch.object(connection, "verify_public_readiness", probe):
            bound = self.issue()
            response = self.client.post("/api/v1/agents/auto-installer", json={})
            self.assertEqual(response.status_code, 200, response.text)
            automatic = response.json()
            self.assertEqual(response.headers["x-agent-deployment-mode"], "production")
        for config in (bound, automatic):
            self.assertEqual(config["serverUrl"], ORIGIN)
            self.assertEqual(config["apiPrefix"], PREFIX)
            self.assertEqual(config["deploymentMode"], "production")
            self.assertEqual(config["expectedServerId"], SERVER_ID)
        self.assertEqual(probe.await_count, 2)
        for call in probe.await_args_list:
            self.assertEqual(set(call.args[0]), {"serverUrl", "apiPrefix", "deploymentMode", "expectedServerId"})

    def test_failed_public_probe_preserves_existing_active_credentials_and_creates_no_ticket(self):
        registered = self.enrolled()
        self.db.expire_all()
        agent = self.db.get(DeviceAgent, registered["deviceId"])
        before = (agent.token_hash, agent.enrollment_hash, agent.enrollment_consumed_at)
        self.builder.reset_mock()
        probe = AsyncMock(side_effect=HTTPException(503, "공개 서버 준비 확인 실패"))
        with patch.object(settings, "AGENT_DEPLOYMENT_MODE", "production"), patch.object(settings, "AGENT_PUBLIC_URL", ORIGIN), patch.object(settings, "AGENT_API_PREFIX", PREFIX), patch.object(connection, "verify_public_readiness", probe):
            self.assertEqual(self.client.post(f"/api/v1/devices/{self.device.id}/agent/installer", json={}).status_code, 503)
            self.assertEqual(self.client.post("/api/v1/agents/auto-installer", json={}).status_code, 503)
        self.db.expire_all()
        agent = self.db.get(DeviceAgent, registered["deviceId"])
        self.assertEqual((agent.token_hash, agent.enrollment_hash, agent.enrollment_consumed_at), before)
        self.assertEqual(self.builder.call_count, 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(AutoEnrollmentTicket)), 0)


class AgentPackageReadinessTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="itam-package-test-")
        self.root = Path(self.temp.name)
        self.location = patch.object(installers, "PACKAGE_ROOT", self.root)
        self.location.start()
        pe = bytearray(512)
        pe[:2] = b'MZ'
        pe[0x3c:0x40] = (0x80).to_bytes(4, 'little')
        pe[0x80:0x84] = b'PE\0\0'
        assets = {
            'install.template.ps1': b"$configBytes=[Convert]::FromBase64String('__CONFIG_BASE64__')\n__AGENT_BASE64__\n__UNINSTALL_BASE64__\n__SERVICE_BASE64__\n",
            'agent.ps1': b'# test fixture agent', 'uninstall.ps1': b'# test fixture removal',
            'SecurityPresenceService.exe': bytes(pe), 'SetupTemplate.exe': bytes(pe),
        }
        for name, content in assets.items():
            (self.root / name).write_bytes(content)
        self.manifest = {'version': '0.5.0', 'sha256': {name: hashlib.sha256(content).hexdigest() for name, content in assets.items()}}
        self.write_manifest()

    def tearDown(self):
        self.location.stop()
        self.temp.cleanup()

    def write_manifest(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def test_verified_v05_package_builds_only_an_explicit_production_exe(self):
        installers.verify_package_ready()
        config = {"serverUrl": ORIGIN, "apiPrefix": PREFIX, "deploymentMode": "production", "expectedServerId": SERVER_ID,
                  "registrationMode": "automatic", "ticketId": str(uuid4()), "registrationToken": secrets.token_urlsafe(32), "heartbeatIntervalSeconds": 15}
        filename, content, mime = installers.build_agent_installer(config, 'Test', 'exe')
        self.assertTrue(filename.endswith('-0.5.0.exe'))
        self.assertEqual(content[:2], b'MZ')
        self.assertEqual(content[-8:], b'SPSETUP1')
        self.assertEqual(mime, 'application/vnd.microsoft.portable-executable')
        for key in ("deploymentMode", "expectedServerId"):
            invalid = {name: value for name, value in config.items() if name != key}
            with self.assertRaises(HTTPException) as rejected:
                installers.build_agent_installer(invalid, 'Test')
            self.assertEqual(rejected.exception.status_code, 422)

    def test_old_or_modified_packages_never_report_ready(self):
        self.manifest['version'] = '0.4.0'
        self.write_manifest()
        with self.assertRaises(HTTPException):
            installers.verify_package_ready()
        self.manifest['version'] = '0.5.0'
        self.write_manifest()
        (self.root / 'agent.ps1').write_bytes(b'changed bytes')
        with self.assertRaises(HTTPException):
            installers.verify_package_ready()


if __name__ == '__main__':
    unittest.main()
