"""Automatic registration tests use fake EXE packaging and isolated databases.
They never register real hardware or execute any Windows installation/control.
"""
import json
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import func, select

from app.config import settings
from app.models.audit_log import AuditLog
from app.models.auto_enrollment_claim import AutoEnrollmentClaim
from app.models.auto_enrollment_ticket import AutoEnrollmentTicket
from app.models.device_agent import DeviceAgent
from app.models.device_inventory import Device
from app.services import device_agent_service as service
from tests.test_device_agents import AgentApiFixture


class AutoEnrollmentApiTest(AgentApiFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.key_path = Path(self.temporary.name) / "auto-enrollment-test.key"
        self.key_path.write_bytes(bytes(range(32)))
        self.key_file_override = patch.object(settings, "AGENT_ENROLLMENT_SECRET_FILE", str(self.key_path))
        self.key_environment_override = patch.object(settings, "AGENT_ENROLLMENT_SECRET", "")
        self.key_file_override.start()
        self.key_environment_override.start()

    def tearDown(self):
        self.key_environment_override.stop()
        self.key_file_override.stop()
        super().tearDown()

    def issue_auto(self, max_uses=1, expires_hours=24):
        response = self.client.post("/api/v1/agents/auto-installer", json={"max_uses": max_uses, "expires_hours": expires_hours})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn(".exe", response.headers["content-disposition"])
        return response.json()

    def payload(self, config, **changes):
        identity = str(uuid4())
        return {"ticketId": config["ticketId"], "registrationToken": config["registrationToken"],
                "clientNonce": secrets.token_urlsafe(32), "hardwareUuid": identity,
                "serialNumber": "AUTO-TEST-" + identity[:8], "hostname": "TEST-PC",
                "deviceType": "desktop", "os": "Windows 11", **changes}

    def register(self, payload):
        return self.client.post("/api/v1/agent/auto-enroll", json=payload)

    def count(self, model):
        self.db.expire_all()
        return self.db.scalar(select(func.count()).select_from(model))

    def ticket(self, config):
        self.db.expire_all()
        return self.db.get(AutoEnrollmentTicket, config["ticketId"])

    def test_admin_exe_only_issuance_defaults_to_unlimited_without_creating_inventory(self):
        self.actor.role = "manager"
        self.assertEqual(self.client.post("/api/v1/agents/auto-installer", json={}).status_code, 403)
        self.actor.role = "admin"
        for body in ({"max_uses": 0}, {"max_uses": 1001}, {"max_uses": True}, {"expires_hours": 0}, {"expires_hours": 169}, {"format": "ps1"}):
            self.assertEqual(self.client.post("/api/v1/agents/auto-installer", json=body).status_code, 422)
        response = self.client.post("/api/v1/agents/auto-installer", json={})
        self.assertEqual(response.status_code, 200)
        config = response.json()
        self.assertEqual(config["registrationMode"], "automatic")
        self.assertEqual(config["apiPrefix"], "/api/v1/agent")
        self.assertNotIn("deviceId", config)
        self.assertNotIn("deviceToken", config)
        self.assertEqual(response.headers["x-enrollment-unlimited"], "true")
        self.assertNotIn("x-enrollment-max-uses", response.headers)
        self.assertEqual(response.headers["x-enrollment-expires-at"], service.iso(self.now + timedelta(hours=24)))
        self.assertEqual(self.count(Device), 2)
        self.assertEqual(self.count(DeviceAgent), 0)
        self.assertEqual(self.ticket(config).used_count, 0)
        self.assertTrue(self.ticket(config).unlimited)
        self.assertEqual(self.ticket(config).token_hash, service.token_hash(config["registrationToken"]))
        self.assertEqual(self.client.get("/api/v1/agents").json()["installer_formats"], ["exe"])
        self.assertEqual(self.client.post(f"/api/v1/devices/{self.device.id}/agent/installer", json={"format": "ps1"}).status_code, 422)
        self.assertTrue(all(call.kwargs["format"] == "exe" for call in self.builder.call_args_list))

    def test_default_unlimited_ticket_registers_multiple_pcs_and_retains_exact_claim_history(self):
        response = self.client.post("/api/v1/agents/auto-installer", json={"expires_hours": 24})
        self.assertEqual(response.status_code, 200, response.text)
        config = response.json()
        bodies = [self.payload(config) for _ in range(3)]
        with ThreadPoolExecutor(max_workers=3) as pool:
            registered = list(pool.map(self.register, bodies))
        self.assertTrue(all(item.status_code == 200 for item in registered))
        self.assertEqual(len({item.json()["inventoryDeviceId"] for item in registered}), 3)
        self.assertEqual(self.count(Device), 5)
        self.assertEqual(self.count(AutoEnrollmentClaim), 3)
        self.assertTrue(self.ticket(config).unlimited)
        self.assertEqual(self.ticket(config).used_count, 0)
        self.assertEqual(self.register(bodies[0]).json(), registered[0].json())
        self.assertEqual(self.count(AutoEnrollmentClaim), 3)

    def test_explicit_legacy_ticket_retains_its_original_quota(self):
        config = self.issue_auto(max_uses=1)
        self.assertFalse(self.ticket(config).unlimited)
        self.assertEqual(self.register(self.payload(config)).status_code, 200)
        self.assertEqual(self.register(self.payload(config)).status_code, 409)
        self.assertEqual(self.ticket(config).used_count, 1)

    def test_missing_or_short_dedicated_key_and_failed_packaging_do_not_create_tickets(self):
        self.key_path.unlink()
        self.assertEqual(self.client.post("/api/v1/agents/auto-installer", json={}).status_code, 503)
        self.key_path.write_bytes(b"too-short")
        self.assertEqual(self.client.post("/api/v1/agents/auto-installer", json={}).status_code, 503)
        self.assertEqual(self.count(AutoEnrollmentTicket), 0)
        self.assertEqual(self.builder.call_count, 0)
        self.key_path.write_bytes(bytes(range(32)))
        self.builder.side_effect = RuntimeError("private diagnostic")
        response = self.client.post("/api/v1/agents/auto-installer", json={})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private diagnostic", response.text)
        self.assertEqual(self.count(AutoEnrollmentTicket), 0)
        self.assertEqual(self.count(Device), 2)

    def test_new_inventory_is_created_only_after_registration_and_only_hashes_are_persisted(self):
        config = self.issue_auto()
        body = self.payload(config, serialNumber="  serial-auto-555  ", deviceType="laptop")
        response = self.register(body)
        self.assertEqual(response.status_code, 200, response.text)
        registered = response.json()
        self.assertTrue(registered["created"])
        self.assertEqual(registered["serialNumber"], "SERIAL-AUTO-555")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.db.expire_all()
        device = self.db.get(Device, registered["inventoryDeviceId"])
        self.assertEqual((device.status, device.device_type, device.os_version), ("stock", "laptop", "Windows 11"))
        self.assertIsNone(device.user_name)
        agent = self.db.get(DeviceAgent, registered["deviceId"])
        self.assertEqual(agent.hardware_key, "uuid:" + body["hardwareUuid"])
        self.assertEqual(agent.token_hash, service.token_hash(registered["deviceToken"]))
        self.assertEqual(self.ticket(config).used_count, 1)
        self.assertEqual(self.count(AutoEnrollmentClaim), 1)
        self.assertEqual(self.heartbeat(registered).status_code, 200)
        logs = self.db.scalars(select(AuditLog)).all()
        safe = json.dumps([entry.changes for entry in logs])
        claim = self.db.scalar(select(AutoEnrollmentClaim))
        self.assertEqual(claim.nonce_hash, service.token_hash(body["clientNonce"]))
        for secret in (config["registrationToken"], body["clientNonce"], registered["deviceToken"]):
            self.assertNotIn(secret, safe)
            self.assertNotIn(secret, self.client.get("/api/v1/agents").text)

    def test_unique_serial_matches_existing_inventory_without_overwriting_business_fields(self):
        self.device.user_name = "Existing user"
        self.device.employee_number = "EXISTING-EMPLOYEE"
        self.device.department = "Existing department"
        self.device.notes = "Keep these notes"
        self.device.os_version = "Manually verified OS"
        self.db.commit()
        before = {column.name: getattr(self.device, column.name) for column in Device.__table__.columns}
        config = self.issue_auto()
        body = self.payload(config, serialNumber=" test-pc-001 ", hostname="NEW-HOSTNAME", deviceType="laptop")
        response = self.register(body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["created"])
        self.assertEqual(response.json()["inventoryDeviceId"], self.device.id)
        self.db.expire_all()
        after = self.db.get(Device, self.device.id)
        self.assertEqual({column.name: getattr(after, column.name) for column in Device.__table__.columns}, before)
        self.assertEqual(self.count(Device), 2)

    def test_placeholder_identities_fall_back_and_both_unusable_are_rejected(self):
        config = self.issue_auto(max_uses=4)
        for hardware, serial in [("00000000-0000-0000-0000-000000000000", "To be filled by O.E.M."),
                                 ("ffffffff-ffff-ffff-ffff-ffffffffffff", "000000000000"),
                                 (None, "DEFAULT STRING"), (None, None)]:
            self.assertEqual(self.register(self.payload(config, hardwareUuid=hardware, serialNumber=serial)).status_code, 422)
        self.assertEqual(self.ticket(config).used_count, 0)
        hardware = str(uuid4())
        response = self.register(self.payload(config, hardwareUuid=hardware, serialNumber="System Serial Number"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["serialNumber"], "AUTO-" + hardware)
        response = self.register(self.payload(config, hardwareUuid="00000000-0000-0000-0000-000000000000", serialNumber="VALID-BIOS-6789"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["serialNumber"], "VALID-BIOS-6789")
        self.assertEqual(self.ticket(config).used_count, 2)

    def test_retry_recovers_same_token_at_quota_without_reusing_nonce_for_other_hardware(self):
        config = self.issue_auto()
        body = self.payload(config)
        first = self.register(body)
        self.assertEqual(first.status_code, 200, first.text)
        again = self.register(body)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json(), first.json())
        self.assertEqual(self.ticket(config).used_count, 1)
        self.assertEqual(self.count(Device), 3)
        self.assertEqual(self.count(AutoEnrollmentClaim), 1)
        self.assertEqual(self.register({**body, "hardwareUuid": str(uuid4())}).status_code, 409)
        self.now += timedelta(hours=24)
        self.assertEqual(self.register(body).status_code, 409)
        self.assertEqual(self.heartbeat(first.json()).status_code, 200)

    def test_active_binding_rejects_fresh_nonce_and_revoked_binding_requires_new_approved_claim(self):
        config = self.issue_auto(max_uses=3)
        body = self.payload(config)
        initial = self.register(body).json()
        fresh = {**body, "clientNonce": secrets.token_urlsafe(32)}
        self.assertEqual(self.register(fresh).status_code, 409)
        self.assertEqual(self.ticket(config).used_count, 1)
        self.assertEqual(self.heartbeat(initial).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1/devices/{initial['inventoryDeviceId']}/agent").status_code, 200)
        self.assertEqual(self.register(body).status_code, 409)
        replacement = self.register(fresh)
        self.assertEqual(replacement.status_code, 200, replacement.text)
        self.assertEqual(replacement.json()["deviceId"], initial["deviceId"])
        self.assertFalse(replacement.json()["created"])
        self.assertNotEqual(replacement.json()["deviceToken"], initial["deviceToken"])
        self.assertEqual(self.heartbeat(initial).status_code, 401)
        self.assertEqual(self.register(body).status_code, 409)
        self.assertEqual(self.ticket(config).used_count, 2)
        self.assertEqual(self.count(Device), 3)

    def test_existing_explicit_binding_and_ambiguous_serial_are_not_taken_over(self):
        existing = self.enrolled()
        config = self.issue_auto(max_uses=3)
        self.assertEqual(self.register(self.payload(config, serialNumber=self.device.serial_number)).status_code, 409)
        self.assertEqual(self.heartbeat(existing).status_code, 200)
        duplicate = Device(serial_number=" test-pc-002 ", device_type="desktop", status="stock")
        self.db.add(duplicate)
        self.db.commit()
        self.assertEqual(self.register(self.payload(config, serialNumber=self.other.serial_number)).status_code, 409)
        self.assertEqual(self.ticket(config).used_count, 0)

    def test_pending_dedicated_enrollment_after_revocation_cannot_be_replaced_automatically(self):
        existing = self.enrolled()
        self.assertEqual(self.client.delete(f"/api/v1/devices/{self.device.id}/agent").status_code, 200)
        dedicated = self.issue()
        config = self.issue_auto()
        response = self.register(self.payload(config, serialNumber=self.device.serial_number))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.ticket(config).used_count, 0)
        enrolled = self.client.post("/api/v1/agent/enroll", json={key: dedicated[key] for key in ("deviceId", "enrollmentToken")})
        self.assertEqual(enrolled.status_code, 200, enrolled.text)
        self.assertEqual(enrolled.json()["deviceId"], existing["deviceId"])

    def test_concurrent_same_nonce_is_idempotent_and_distinct_nonces_respect_quota(self):
        config = self.issue_auto()
        body = self.payload(config)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.register(body), range(2)))
        self.assertEqual([item.status_code for item in responses], [200, 200])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(self.ticket(config).used_count, 1)
        second = self.issue_auto()
        requests = [self.payload(second), self.payload(second)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(self.register, requests))
        self.assertEqual(sorted(item.status_code for item in responses), [200, 409])
        self.assertEqual(self.ticket(second).used_count, 1)
        self.assertEqual(self.count(Device), 4)

    def test_cross_ticket_same_hardware_never_creates_duplicate_inventory(self):
        first = self.issue_auto()
        second = self.issue_auto()
        identity = str(uuid4())
        requests = [self.payload(first, hardwareUuid=identity, serialNumber="RACE-SERIAL-A"),
                    self.payload(second, hardwareUuid=identity, serialNumber="RACE-SERIAL-B")]
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(self.register, requests))
        self.assertEqual(sorted(item.status_code for item in responses), [200, 409])
        self.assertEqual(self.count(Device), 3)
        self.assertEqual(self.count(DeviceAgent), 1)
        self.assertEqual(self.ticket(first).used_count + self.ticket(second).used_count, 1)

    def test_shared_ticket_does_not_merge_by_hostname_and_rejects_invalid_or_expired_ticket(self):
        config = self.issue_auto(max_uses=2, expires_hours=1)
        wrong = self.payload(config, registrationToken=secrets.token_urlsafe(32))
        self.assertEqual(self.register(wrong).status_code, 401)
        first = self.register(self.payload(config, hostname="SAME-HOST"))
        second = self.register(self.payload(config, hostname="SAME-HOST"))
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertNotEqual(first.json()["inventoryDeviceId"], second.json()["inventoryDeviceId"])
        self.assertEqual(self.register(self.payload(config)).status_code, 409)
        self.assertEqual(self.ticket(config).used_count, 2)
        unexpired = self.issue_auto(expires_hours=1)
        self.now += timedelta(hours=1)
        self.assertEqual(self.register(self.payload(unexpired)).status_code, 409)
        self.assertEqual(self.ticket(unexpired).used_count, 0)


if __name__ == "__main__":
    unittest.main()
