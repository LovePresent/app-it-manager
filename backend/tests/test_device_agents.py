"""Isolated API tests: fake packaging, temporary SQLite, no power or UDP calls.
Production migrations and smoke checks are performed separately on the preserved
application database; these fixtures never replace that database.
"""
import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.api.deps import get_current_user
from app.config import settings
from app.database import Base, get_db
from app.models.audit_log import AuditLog
from app.models.device_agent import DeviceAgent
from app.models.device_command import DeviceCommand
from app.models.device_inventory import Device
from app.models.user import User
from app.services import device_agent_service as service

CAPS = ["power-control-v1", "network-info-v1", "wol-relay-v1"]
ADAPTERS = [{"id": "ethernet-1", "name": "Test Ethernet", "macAddress": "02:11:22:33:44:55",
             "ipv4": [{"address": "192.0.2.10", "netmask": "255.255.255.0"}],
             "ipv6": ["2001:db8::10"], "physical": True}]


class AgentApiFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="itam-agent-test-")
        database_file = Path(self.temporary.name) / "test.db"
        self.engine = create_engine(f"sqlite:///{database_file.as_posix()}", connect_args={"check_same_thread": False, "timeout": 15})
        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.sessions()
        self.actor = User(email="agent-admin@example.test", name="Agent test admin", role="admin", is_active=True)
        self.device = Device(serial_number="TEST-PC-001", device_type="desktop", status="assigned",
                             ip_address="198.51.100.1", mac_address="02:AA:BB:CC:DD:01")
        self.other = Device(serial_number="TEST-PC-002", device_type="desktop", status="stock")
        self.db.add_all([self.actor, self.device, self.other])
        self.db.commit()
        self.actor.id, self.device.id, self.other.id  # Load before request sessions run.
        self.now = datetime(2026, 10, 25, 3, 0, 0)
        self.clock = patch.object(service, "utcnow", side_effect=lambda: self.now)
        self.clock.start()
        self.public_url = patch.object(settings, "AGENT_PUBLIC_URL", "https://presence.example.test")
        self.public_url.start()
        self.deployment_mode = patch.object(settings, "AGENT_DEPLOYMENT_MODE", "development")
        self.api_prefix = patch.object(settings, "AGENT_API_PREFIX", "/api/v1/agent")
        self.deployment_mode.start()
        self.api_prefix.start()
        self.server_key_path = Path(self.temporary.name) / "agent-server-test.key"
        self.server_key_path.write_bytes(bytes(range(32)))
        self.server_key_file = patch.object(settings, "AGENT_ENROLLMENT_SECRET_FILE", str(self.server_key_path))
        self.server_key_env = patch.object(settings, "AGENT_ENROLLMENT_SECRET", "")
        self.server_key_file.start()
        self.server_key_env.start()
        self.packager = patch("app.services.agent_installer_service.build_agent_installer", side_effect=self.fake_installer)
        self.builder = self.packager.start()
        self.original_overrides = app.dependency_overrides.copy()
        def request_db():
            with self.sessions() as session:
                yield session
        app.dependency_overrides[get_db] = request_db
        app.dependency_overrides[get_current_user] = lambda: self.actor
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides = self.original_overrides
        self.packager.stop()
        self.public_url.stop()
        self.api_prefix.stop()
        self.deployment_mode.stop()
        self.server_key_env.stop()
        self.server_key_file.stop()
        self.clock.stop()
        self.db.close()
        self.engine.dispose()
        self.temporary.cleanup()

    @staticmethod
    def fake_installer(config, device_name, format):
        return f"SecurityAgent-Setup.{format}", json.dumps(config).encode(), "application/octet-stream"

    def issue(self, device=None):
        device = device or self.device
        response = self.client.post(f"/api/v1/devices/{device.id}/agent/installer", json={"format": "exe"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        return response.json()

    def enrolled(self, device=None):
        config = self.issue(device)
        response = self.client.post("/api/v1/agent/enroll", json={key: config[key] for key in ("deviceId", "enrollmentToken")})
        self.assertEqual(response.status_code, 200, response.text)
        return {**config, **response.json()}

    def heartbeat(self, registration, **overrides):
        headers = overrides.pop("headers", {})
        return self.client.post("/api/v1/agent/heartbeat", headers={
            "Authorization": "Bearer " + registration["deviceToken"], **headers,
        }, json={"deviceId": registration["deviceId"], "hostname": "TEST-PC", "os": "Microsoft Windows 11",
                 "agentVersion": "0.3.0", "bootTime": "2026-10-25T01:00:00Z",
                 "capabilities": CAPS, **overrides})

    def online(self, registration):
        response = self.heartbeat(registration, networkAdapters=ADAPTERS)
        self.assertEqual(response.status_code, 200, response.text)

    def detail(self, device=None):
        device = device or self.device
        response = self.client.get(f"/api/v1/devices/{device.id}/agent")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def power(self, action="restart", device=None):
        device = device or self.device
        return self.client.post(f"/api/v1/devices/{device.id}/agent/power", json={"action": action, "confirmation": device.serial_number})

    def ack(self, registration, command_id, status="accepted", detail="accepted", **body):
        return self.client.post(f"/api/v1/agent/commands/{command_id}/ack",
            headers={"Authorization": "Bearer " + registration["deviceToken"]},
            json={"deviceId": registration["deviceId"], "status": status, "detail": detail, **body})

class DeviceAgentApiTest(AgentApiFixture, unittest.TestCase):
    def test_enrollment_single_use_expiry_hash_only_and_reissue_preserves_active_token(self):
        registration = self.enrolled()
        self.online(registration)
        duplicate = self.client.post("/api/v1/agent/enroll", json={key: registration[key] for key in ("deviceId", "enrollmentToken")})
        self.assertEqual(duplicate.status_code, 409)
        self.db.expire_all()
        agent = self.db.get(DeviceAgent, registration["deviceId"])
        self.assertEqual(agent.token_hash, hashlib.sha256(registration["deviceToken"].encode()).hexdigest())
        new_config = self.issue()
        self.assertEqual(new_config["deviceId"], registration["deviceId"])
        self.assertEqual(self.heartbeat(registration).status_code, 200)
        self.now += timedelta(seconds=900)
        expired = self.client.post("/api/v1/agent/enroll", json={key: new_config[key] for key in ("deviceId", "enrollmentToken")})
        self.assertEqual(expired.status_code, 409)
        self.db.expire_all()
        logs = self.db.scalars(select(AuditLog)).all()
        persisted = json.dumps([row.changes for row in logs])
        for secret in (registration["deviceToken"], registration["enrollmentToken"], new_config["enrollmentToken"]):
            self.assertNotIn(secret, persisted)
            self.assertNotIn(secret, self.client.get("/api/v1/agents").text)
        replacement = self.enrolled()
        self.assertEqual(replacement["deviceId"], registration["deviceId"])
        self.assertEqual(self.heartbeat(registration).status_code, 401)
        self.assertEqual(self.heartbeat(replacement).status_code, 200)

    def test_telemetry_audits_changes_and_reconnections_not_identical_samples_and_secrets_are_not_cached(self):
        config = self.issue()
        response = self.client.post("/api/v1/agent/enroll", json={key: config[key] for key in ("deviceId", "enrollmentToken")})
        self.assertEqual(response.headers["cache-control"], "no-store")
        registration = {**config, **response.json()}
        self.online(registration)
        self.now += timedelta(seconds=15)
        self.online(registration)
        self.db.expire_all()
        logs = self.db.scalars(select(AuditLog).where(AuditLog.action == "heartbeat_state_change")).all()
        self.assertEqual(len(logs), 1)
        self.now += timedelta(seconds=60)
        self.online(registration)
        self.db.expire_all()
        logs = self.db.scalars(select(AuditLog).where(AuditLog.action == "heartbeat_state_change")).all()
        self.assertEqual(len(logs), 2)
        code = self.client.post(f"/api/v1/devices/{self.device.id}/agent/uninstall-code", json={"confirmation": self.device.serial_number})
        self.assertEqual(code.status_code, 200)
        self.assertEqual(code.headers["cache-control"], "no-store")

    def test_failed_packaging_never_creates_agent_or_rotates_registration(self):
        self.builder.side_effect = RuntimeError("private compiler diagnostic")
        response = self.client.post(f"/api/v1/devices/{self.device.id}/agent/installer", json={"format": "exe"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private compiler diagnostic", response.text)
        self.assertIsNone(self.db.scalar(select(DeviceAgent)))
        self.builder.side_effect = self.fake_installer
        registration = self.enrolled()
        self.db.expire_all()
        token_before = self.db.get(DeviceAgent, registration["deviceId"]).token_hash
        self.builder.side_effect = RuntimeError("failed")
        response = self.client.post(f"/api/v1/devices/{self.device.id}/agent/installer", json={"format": "exe"})
        self.assertEqual(response.status_code, 503)
        self.db.expire_all()
        self.assertEqual(self.db.get(DeviceAgent, registration["deviceId"]).token_hash, token_before)

    def test_enrollment_concurrent_consumption_has_one_winner(self):
        config = self.issue()
        body = {key: config[key] for key in ("deviceId", "enrollmentToken")}
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.client.post("/api/v1/agent/enroll", json=body), range(2)))
        self.assertEqual(sorted(item.status_code for item in responses), [200, 409])

    def test_presence_server_clock_inventory_validation_and_manual_fields_unchanged(self):
        registration = self.enrolled()
        response = self.heartbeat(registration, networkAdapters=ADAPTERS, observedIp="203.0.113.99", lastSeenAt="2099-01-01T00:00:00Z",
                                  headers={"X-Forwarded-For": "203.0.113.88"})
        self.assertEqual(response.status_code, 200)
        state = self.detail()["agent"]
        self.assertEqual(state["observed_ip"], "testclient")
        self.assertEqual(state["last_seen_at"], service.iso(self.now))
        self.assertEqual(state["network_adapters"], ADAPTERS)
        self.now += timedelta(seconds=15)
        bad = [{**ADAPTERS[0], "ipv4": [{"address": "999.0.0.1", "netmask": "255.255.255.0"}]}]
        self.assertEqual(self.heartbeat(registration, networkAdapters=bad).status_code, 422)
        self.assertEqual(self.detail()["agent"]["last_seen_at"], state["last_seen_at"])
        self.assertEqual(self.heartbeat(registration, networkAdapters=None).status_code, 422)
        self.assertEqual(self.heartbeat(registration, networkAdapters=ADAPTERS * 17).status_code, 422)
        self.assertEqual(self.heartbeat(registration, capabilities=[]).status_code, 200)
        retained = self.detail()["agent"]
        self.assertEqual(retained["network_updated_at"], state["network_updated_at"])
        self.assertEqual(retained["network_adapters"], ADAPTERS)
        self.assertEqual(retained["capabilities"], [])
        self.now += timedelta(seconds=60)
        self.assertEqual(self.detail()["agent"]["status"], "offline")
        self.db.expire_all()
        self.assertEqual(self.db.get(Device, self.device.id).ip_address, "198.51.100.1")
        self.assertEqual(self.db.get(Device, self.device.id).status, "assigned")

    def test_inventory_auth_and_admin_only_controls_preserve_manager_workflows(self):
        registration = self.enrolled()
        app.dependency_overrides.pop(get_current_user)
        for url in ("/api/v1/agents", "/api/v1/devices", "/api/v1/ip-addresses"):
            self.assertEqual(self.client.get(url).status_code, 401)
        with patch("app.api.deps.verify_token", new=AsyncMock(side_effect=HTTPException(401, "not a user token"))):
            self.assertEqual(self.client.get("/api/v1/agents", headers={"Authorization": "Bearer " + registration["deviceToken"]}).status_code, 401)
        app.dependency_overrides[get_current_user] = lambda: self.actor
        self.actor.role = "user"
        self.assertEqual(self.client.get("/api/v1/devices").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/devices", json={"serial_number": "NO-PERMISSION"}).status_code, 403)
        self.assertEqual(self.power().status_code, 403)
        self.actor.role = "manager"
        response = self.client.post("/api/v1/devices", json={"serial_number": "MANAGER-CREATED", "device_type": "desktop"})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.power().status_code, 403)

    def test_power_confirm_capability_atomic_delivery_ack_binding_and_no_replay(self):
        registration = self.enrolled()
        other = self.enrolled(self.other)
        self.assertEqual(self.power().status_code, 409)
        self.online(registration)
        self.assertEqual(self.client.post(f"/api/v1/devices/{self.device.id}/agent/power", json={"action": "exec", "confirmation": self.device.serial_number}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/v1/devices/{self.device.id}/agent/power", json={"action": "restart", "confirmation": "wrong"}).status_code, 400)
        response = self.power()
        self.assertEqual(response.status_code, 202, response.text)
        command = response.json()["command"]
        self.assertEqual(self.ack(registration, command["id"]).status_code, 409)
        self.assertEqual(self.power().status_code, 409)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.heartbeat(registration), range(2)))
        self.assertTrue(all(item.status_code == 200 for item in responses))
        outgoing = [item for response in responses for item in response.json()["commands"]]
        self.assertEqual([item["id"] for item in outgoing], [command["id"]])
        self.db.expire_all()
        self.assertEqual(self.db.get(DeviceCommand, command["id"]).status, "delivered")
        self.assertEqual(self.ack(other, command["id"]).status_code, 404)
        self.assertEqual(self.ack(other, command["id"], deviceId=registration["deviceId"]).status_code, 401)
        self.assertEqual(self.ack(registration, command["id"]).status_code, 200)
        self.assertEqual(self.ack(registration, command["id"]).status_code, 200)
        self.assertEqual(self.ack(registration, command["id"], "succeeded", "packet_sent").status_code, 400)
        self.assertEqual(self.heartbeat(registration).json()["commands"], [])
        self.assertEqual(self.ack(registration, command["id"], "failed", "execution_failed").status_code, 200)
        self.assertEqual(self.ack(registration, command["id"]).status_code, 409)

    def test_exact_expiry_and_missing_capability_never_deliver_commands(self):
        registration = self.enrolled()
        self.online(registration)
        pending = self.power().json()["command"]
        self.assertEqual(self.heartbeat(registration, capabilities=[]).json()["commands"], [])
        self.now += timedelta(seconds=60)
        self.assertEqual(self.heartbeat(registration).json()["commands"], [])
        self.assertEqual(self.detail()["commands"][0]["status"], "expired")
        self.assertEqual(self.ack(registration, pending["id"]).status_code, 409)
        delivered = self.power().json()["command"]
        self.assertEqual(len(self.heartbeat(registration).json()["commands"]), 1)
        self.now += timedelta(seconds=60)
        states = {item["id"]: item["status"] for item in self.detail()["commands"]}
        self.assertEqual(states[delivered["id"]], "unconfirmed")
        self.assertEqual(self.ack(registration, delivered["id"]).status_code, 409)

    def test_wol_queues_on_online_relay_target_history_and_success_means_packet_sent(self):
        target = self.enrolled()
        relay = self.enrolled(self.other)
        self.online(relay)
        url = f"/api/v1/devices/{self.device.id}/agent"
        self.assertEqual(self.client.post(url + "/wake", json={"confirmation": self.device.serial_number}).status_code, 409)
        setting = {"macAddress": "02:AA:BB:CC:DD:01", "relayDeviceId": self.other.id, "sourceAddress": "192.0.2.10"}
        self.assertEqual(self.client.put(url + "/wol", json={**setting, "sourceAddress": "203.0.113.10"}).status_code, 400)
        configured = self.client.put(url + "/wol", json=setting)
        self.assertEqual(configured.status_code, 200, configured.text)
        self.assertEqual(configured.json()["wol"]["broadcastAddress"], "192.0.2.255")
        response = self.client.post(url + "/wake", json={"confirmation": self.device.serial_number})
        self.assertEqual(response.status_code, 202, response.text)
        command = response.json()["command"]
        self.assertEqual(command["executor_agent_id"], relay["deviceId"])
        self.assertEqual(command["target_device_id"], self.device.id)
        self.assertEqual(self.heartbeat(target).json()["commands"], [])
        delivery = self.heartbeat(relay).json()["commands"]
        self.assertEqual(delivery[0]["id"], command["id"])
        self.assertEqual(delivery[0]["payload"], {"macAddress": setting["macAddress"], "sourceAddress": "192.0.2.10", "broadcastAddress": "192.0.2.255", "port": 9})
        self.assertEqual(self.ack(target, command["id"]).status_code, 404)
        self.assertEqual(self.ack(relay, command["id"], "succeeded", "packet_sent").status_code, 409)
        self.assertEqual(self.ack(relay, command["id"]).status_code, 200)
        self.assertEqual(self.ack(relay, command["id"], "succeeded", "packet_sent").status_code, 200)
        self.assertEqual(self.detail()["commands"][0]["status"], "sent")
        self.assertEqual(self.client.post(url + "/wake", json={"confirmation": self.device.serial_number}).status_code, 429)
        self.now += timedelta(seconds=20)
        self.assertEqual(self.client.post(url + "/wake", json={"confirmation": self.device.serial_number}).status_code, 202)
        self.now += timedelta(seconds=60)
        self.assertEqual(self.client.post(url + "/wake", json={"confirmation": self.device.serial_number}).status_code, 409)

    def test_revoke_keeps_inventory_and_prevents_old_token_and_pending_commands(self):
        registration = self.enrolled()
        self.online(registration)
        command = self.power().json()["command"]
        self.assertEqual(self.client.delete(f"/api/v1/devices/{self.device.id}/agent").status_code, 200)
        self.assertEqual(self.heartbeat(registration).status_code, 401)
        self.assertEqual(self.detail()["agent"]["status"], "revoked")
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Device, self.device.id))
        self.assertEqual(self.db.get(DeviceCommand, command["id"]).status, "expired")

    def test_managed_inventory_cannot_be_deleted_even_after_revocation_but_unmanaged_delete_still_works(self):
        registration = self.enrolled()
        self.online(registration)
        url = f"/api/v1/devices/{self.device.id}"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 409)
        self.assertIn("퇴역", response.json()["detail"])
        self.assertEqual(self.client.delete(url + "/agent").status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 409)
        self.assertEqual(self.client.put(url, json={"status": "retired"}).status_code, 200)
        unmanaged_id = self.other.id
        self.assertEqual(self.client.delete(f"/api/v1/devices/{unmanaged_id}").status_code, 200)
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(DeviceAgent, registration["deviceId"]))
        self.assertEqual(self.db.get(Device, self.device.id).status, "retired")
        self.assertIsNone(self.db.get(Device, unmanaged_id))

    def test_uninstall_code_is_admin_only_expiring_single_use_and_works_after_revocation(self):
        registration = self.enrolled()
        self.online(registration)
        url = f"/api/v1/devices/{self.device.id}/agent"
        self.actor.role = "manager"
        self.assertEqual(self.client.post(url + "/uninstall-code", json={"confirmation": self.device.serial_number}).status_code, 403)
        self.actor.role = "admin"
        self.assertEqual(self.client.delete(url).status_code, 200)
        response = self.client.post(url + "/uninstall-code", json={"confirmation": self.device.serial_number})
        self.assertEqual(response.status_code, 200, response.text)
        code = response.json()["code"]
        body = {"deviceId": registration["deviceId"], "code": code}
        self.now += timedelta(seconds=900)
        self.assertEqual(self.client.post("/api/v1/agent/uninstall/authorize", json=body).status_code, 409)
        body["code"] = self.client.post(url + "/uninstall-code", json={"confirmation": self.device.serial_number}).json()["code"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.client.post("/api/v1/agent/uninstall/authorize", json=body), range(2)))
        self.assertEqual(sum(item.status_code == 200 for item in responses), 1)
        self.assertTrue(all(item.status_code in (200, 401, 409) for item in responses))
        self.assertEqual(self.heartbeat(registration).status_code, 401)
        self.db.expire_all()
        self.assertIsNone(self.db.get(DeviceAgent, registration["deviceId"]).uninstall_code_hash)
        logs = self.db.scalars(select(AuditLog)).all()
        self.assertNotIn(body["code"], json.dumps([item.changes for item in logs]))
        issues = [item for item in logs if item.action == "uninstall_code_issue"]
        self.assertTrue(all(item.user_id == self.actor.id and item.user_name == self.actor.name for item in issues))


if __name__ == "__main__":
    unittest.main()
