"""Lifecycle state tests never install/remove software or run worker commands."""
import json
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.device_agent import DeviceAgent
from app.models.device_command import DeviceCommand
from app.services import device_agent_service as service
from tests.test_device_agents import AgentApiFixture


class AgentLifecycleApiTest(AgentApiFixture, unittest.TestCase):
    def health(self, registration, state, **extra):
        return self.client.post("/api/v1/agent/service-health", headers={
            "Authorization": "Bearer " + registration["deviceToken"],
        }, json={"deviceId": registration["deviceId"], "state": state, **extra})

    def removal_receipt(self, registration, device=None):
        device = device or self.device
        issued = self.client.post(f"/api/v1/devices/{device.id}/agent/uninstall-code", json={"confirmation": device.serial_number})
        self.assertEqual(issued.status_code, 200, issued.text)
        response = self.client.post("/api/v1/agent/uninstall/authorize", json={
            "deviceId": registration["deviceId"], "code": issued.json()["code"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertRegex(response.json()["receipt"], r"^[A-Za-z0-9_-]{43}$")
        return response.json()["receipt"]

    def complete(self, registration, receipt):
        return self.client.post("/api/v1/agent/uninstall/complete", json={"deviceId": registration["deviceId"], "receipt": receipt})

    def test_service_health_is_device_authenticated_and_worker_absence_overrides_pending_without_heartbeat(self):
        registration = self.enrolled()
        other = self.enrolled(self.other)
        self.assertEqual(self.detail()["agent"]["installation_state"], "pending")
        response = self.health(registration, "worker_missing")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("commands", response.json())
        state = self.detail()["agent"]
        self.assertEqual(state["status"], "worker_missing")
        self.assertEqual(state["installation_state"], "pending")
        self.assertIsNone(state["last_seen_at"])
        self.assertEqual(state["service_last_seen_at"], service.iso(self.now))
        self.assertEqual(self.health(other, "running", deviceId=registration["deviceId"]).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/agent/service-health", json={"deviceId": registration["deviceId"], "state": "running"}).status_code, 401)
        self.assertEqual(self.health(registration, "arbitrary_command").status_code, 422)
        self.assertEqual(self.health(registration, "running", command="must-not-run").status_code, 422)

    def test_fresh_service_fault_expires_at_sixty_seconds_and_running_health_does_not_fake_online(self):
        registration = self.enrolled()
        self.online(registration)
        original_seen = self.detail()["agent"]["last_seen_at"]
        self.now += timedelta(seconds=10)
        self.assertEqual(self.health(registration, "worker_stopped").status_code, 200)
        self.now += timedelta(seconds=59, milliseconds=999)
        self.assertEqual(self.detail()["agent"]["status"], "worker_stopped")
        self.now += timedelta(milliseconds=1)
        self.assertEqual(self.detail()["agent"]["status"], "offline")
        self.assertEqual(self.health(registration, "running").status_code, 200)
        state = self.detail()["agent"]
        self.assertEqual(state["status"], "offline")
        self.assertEqual(state["last_seen_at"], original_seen)
        self.assertEqual(state["service_state"], "running")
        self.assertEqual(state["installation_state"], "installed")

    def test_health_is_change_audited_and_real_heartbeat_clears_stopped_without_faking_health_timestamp(self):
        registration = self.enrolled()
        self.online(registration)
        command = self.power().json()["command"]
        self.now += timedelta(seconds=10)
        self.assertEqual(self.health(registration, "worker_stopped").status_code, 200)
        self.now += timedelta(seconds=10)
        self.assertEqual(self.health(registration, "worker_stopped").status_code, 200)
        health_at = self.detail()["agent"]["service_last_seen_at"]
        self.db.expire_all()
        logs = self.db.scalars(select(AuditLog).where(AuditLog.action == "service_state_change")).all()
        self.assertEqual(len(logs), 1)
        self.assertEqual(self.db.get(DeviceCommand, command["id"]).status, "pending")
        self.now += timedelta(seconds=10)
        response = self.heartbeat(registration)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["commands"][0]["id"], command["id"])
        state = self.detail()["agent"]
        self.assertEqual(state["status"], "online")
        self.assertEqual(state["installation_state"], "installed")
        self.assertEqual(state["service_state"], "running")
        self.assertEqual(state["service_last_seen_at"], health_at)
        self.assertEqual(state["last_seen_at"], service.iso(self.now))

    def test_fresh_missing_file_evidence_survives_loaded_worker_heartbeats_until_wrapper_recovers_or_evidence_ages(self):
        registration = self.enrolled()
        self.online(registration)
        self.now += timedelta(seconds=10)
        self.assertEqual(self.health(registration, "worker_missing").status_code, 200)
        self.db.expire_all()
        before_count = len(self.db.scalars(select(AuditLog).where(AuditLog.action == "heartbeat_state_change")).all())
        for _ in range(2):
            self.now += timedelta(seconds=10)
            self.assertEqual(self.heartbeat(registration).status_code, 200)
            state = self.detail()["agent"]
            self.assertEqual(state["status"], "worker_missing")
            self.assertEqual(state["service_state"], "worker_missing")
            self.assertEqual(state["last_seen_at"], service.iso(self.now))
        self.db.expire_all()
        after_count = len(self.db.scalars(select(AuditLog).where(AuditLog.action == "heartbeat_state_change")).all())
        self.assertEqual(after_count, before_count, "unchanged missing evidence must not create heartbeat log noise")
        self.now += timedelta(seconds=5)
        self.assertEqual(self.health(registration, "running").status_code, 200)
        self.assertEqual(self.detail()["agent"]["status"], "online")
        self.now += timedelta(seconds=5)
        self.assertEqual(self.health(registration, "worker_missing").status_code, 200)
        self.now += timedelta(seconds=50)
        self.assertEqual(self.heartbeat(registration).status_code, 200)
        self.assertEqual(self.detail()["agent"]["status"], "worker_missing")
        self.now += timedelta(seconds=10)
        state = self.detail()["agent"]
        self.assertEqual(state["status"], "online")
        self.assertEqual(state["service_state"], "worker_missing", "aged evidence remains historical rather than being overwritten")

    def test_authorization_without_cleanup_confirmation_stays_revoked_not_uninstalled_and_receipt_expires(self):
        registration = self.enrolled()
        self.online(registration)
        receipt = self.removal_receipt(registration)
        state = self.detail()["agent"]
        self.assertEqual(state["status"], "revoked")
        self.assertEqual(state["installation_state"], "installed")
        self.assertIsNone(state["uninstalled_at"])
        self.assertEqual(self.heartbeat(registration).status_code, 401)
        self.db.expire_all()
        self.assertEqual(self.db.get(DeviceAgent, registration["deviceId"]).completion_hash, service.token_hash(receipt))
        self.now += timedelta(minutes=10)
        self.assertEqual(self.complete(registration, receipt).status_code, 409)
        self.assertEqual(self.detail()["agent"]["status"], "revoked")
        self.assertIsNone(self.detail()["agent"]["uninstalled_at"])
        logs = self.db.scalars(select(AuditLog)).all()
        self.assertNotIn(receipt, json.dumps([item.changes for item in logs]))
        self.assertNotIn(receipt, self.client.get("/api/v1/agents").text)

    def test_completion_is_bound_atomic_idempotent_and_confirmed_uninstalled_overrides_revoked(self):
        registration = self.enrolled()
        other = self.enrolled(self.other)
        self.online(registration)
        receipt = self.removal_receipt(registration)
        self.assertEqual(self.complete(other, receipt).status_code, 401)
        self.assertEqual(self.complete(registration, secrets.token_urlsafe(32)).status_code, 401)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.complete(registration, receipt), range(2)))
        self.assertEqual([item.status_code for item in responses], [200, 200])
        self.assertTrue(all(item.headers["cache-control"] == "no-store" for item in responses))
        state = self.detail()["agent"]
        self.assertEqual(state["status"], "uninstalled")
        self.assertEqual(state["installation_state"], "uninstalled")
        self.assertEqual(state["uninstalled_at"], service.iso(self.now))
        self.assertIsNotNone(state["revoked_at"])
        self.assertEqual(self.health(registration, "running").status_code, 401)
        self.now += timedelta(minutes=11)
        self.assertEqual(self.complete(registration, receipt).status_code, 200)
        self.assertEqual(self.detail()["agent"]["uninstalled_at"], state["uninstalled_at"])
        self.db.expire_all()
        logs = self.db.scalars(select(AuditLog).where(AuditLog.action == "uninstall_complete")).all()
        self.assertEqual(len(logs), 1)

    def test_new_explicit_enrollment_clears_uninstalled_state_and_invalidates_old_receipt(self):
        registration = self.enrolled()
        self.online(registration)
        receipt = self.removal_receipt(registration)
        self.assertEqual(self.complete(registration, receipt).status_code, 200)
        replacement = self.enrolled()
        self.assertEqual(replacement["deviceId"], registration["deviceId"])
        state = self.detail()["agent"]
        self.assertEqual(state["status"], "pending")
        self.assertEqual(state["installation_state"], "pending")
        self.assertIsNone(state["uninstalled_at"])
        self.assertIsNone(state["service_state"])
        self.assertIsNone(state["service_last_seen_at"])
        self.assertEqual(self.complete(registration, receipt).status_code, 401)
        self.online(replacement)
        self.assertEqual(self.detail()["agent"]["installation_state"], "installed")
        old_code = self.client.post(f"/api/v1/devices/{self.device.id}/agent/uninstall-code", json={"confirmation": self.device.serial_number}).json()["code"]
        newest = self.enrolled()
        old_authorization = self.client.post("/api/v1/agent/uninstall/authorize", json={"deviceId": newest["deviceId"], "code": old_code})
        self.assertEqual(old_authorization.status_code, 401)
        self.assertEqual(self.heartbeat(newest).status_code, 200)

    def test_new_automatic_enrollment_also_invalidates_old_removal_receipt(self):
        registration = self.enrolled()
        receipt = self.removal_receipt(registration)
        self.assertEqual(self.complete(registration, receipt).status_code, 200)
        with patch("app.services.auto_enrollment_service.enrollment_key", return_value=b"test-only-enrollment-key-32-bytes!"):
            issued = self.client.post("/api/v1/agents/auto-installer", json={})
            self.assertEqual(issued.status_code, 200, issued.text)
            config = issued.json()
            response = self.client.post("/api/v1/agent/auto-enroll", json={
                "ticketId": config["ticketId"], "registrationToken": config["registrationToken"],
                "clientNonce": secrets.token_urlsafe(32), "hardwareUuid": str(uuid4()),
                "serialNumber": self.device.serial_number, "hostname": "REINSTALLED-PC", "deviceType": "desktop", "os": "Windows 11",
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["deviceId"], registration["deviceId"])
        self.assertEqual(self.detail()["agent"]["installation_state"], "pending")
        self.assertEqual(self.complete(registration, receipt).status_code, 401)


if __name__ == "__main__":
    unittest.main()
