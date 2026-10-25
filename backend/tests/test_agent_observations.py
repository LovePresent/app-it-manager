"""Observed telemetry must never overwrite the maintained inventory IP.

API-level regression cases use AgentApiFixture's isolated temporary database and
fake installer. They do not touch the running DB, power controls or real agents.
"""
import copy
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import select

from app.api.deps import get_current_user
from app.main import app
from app.models.audit_log import AuditLog
from app.models.device_inventory import Device
from app.models.notification import Notification
from app.services import device_agent_service as service
from tests.test_device_agents import AgentApiFixture, CAPS


def adapter(addresses=(), *, adapter_id="ethernet-1", physical=True, ipv6=()):
    return {
        "id": adapter_id,
        "name": f"Test {adapter_id}",
        "macAddress": "02:11:22:33:44:55",
        "ipv4": [{"address": address, "netmask": "255.255.255.0"} for address in addresses],
        "ipv6": list(ipv6),
        "physical": physical,
    }


class AgentObservationApiTest(AgentApiFixture, unittest.TestCase):
    def report(self, registration, adapters, **overrides):
        response = self.heartbeat(registration, networkAdapters=copy.deepcopy(adapters), **overrides)
        self.assertEqual(response.status_code, 200, response.text)
        self.db.expire_all()
        self.now += timedelta(seconds=15)
        return response

    def audit_rows(self, action=None, device=None):
        device = device or self.device
        self.db.expire_all()
        query = select(AuditLog).where(
            AuditLog.entity_type == "device_agent", AuditLog.entity_id == device.id,
        ).order_by(AuditLog.id)
        if action:
            query = query.where(AuditLog.action == action)
        return self.db.scalars(query).all()

    def alerts(self, kind=None, device=None):
        device = device or self.device
        self.db.expire_all()
        query = select(Notification).where(
            Notification.entity_type == "device", Notification.entity_id == device.id,
        ).order_by(Notification.id)
        if kind:
            query = query.where(Notification.type == kind)
        return self.db.scalars(query).all()

    def monitor(self, device=None):
        return self.detail(device)["agent"]["network_monitor"]

    def ip_history(self, device=None):
        device = device or self.device
        response = self.client.get("/api/v1/ip-change-history", params={
            "device_id": device.id, "source_type": "agent", "size": 100,
        })
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total"], len(body["items"]))
        return sorted(body["items"], key=lambda row: row["id"])

    def test_fixed_inventory_ip_is_preserved_and_initial_mismatch_creates_one_alert(self):
        registration = self.enrolled()
        configured_ip = self.device.ip_address
        configured_mac = self.device.mac_address
        self.report(registration, [adapter(["192.0.2.10"])])

        maintained = self.db.get(Device, self.device.id)
        self.assertEqual(maintained.ip_address, configured_ip)
        self.assertEqual(maintained.mac_address, configured_mac)
        self.assertEqual(maintained.status, "assigned")
        monitor = self.monitor()
        self.assertEqual(monitor["source"], "inventory")
        self.assertEqual(monitor["status"], "mismatch")
        self.assertEqual(monitor["expected_ipv4"], [configured_ip])
        self.assertEqual(monitor["observed_ipv4"], ["192.0.2.10"])
        self.assertTrue(monitor["alert_active"])
        self.assertNotIn("incident", monitor)
        self.assertEqual(len(self.alerts("ip_mismatch")), 1)
        mismatch = self.audit_rows("ip_mismatch_detected")
        self.assertEqual(len(mismatch), 1)
        self.assertEqual(mismatch[0].changes["evidence"], "agent_snapshot")
        self.assertEqual(mismatch[0].changes["expected_ipv4"], [configured_ip])
        self.assertEqual(mismatch[0].changes["observed_ipv4"], ["192.0.2.10"])
        self.assertIsNone(mismatch[0].user_id)
        self.assertEqual(mismatch[0].user_name, "Windows 에이전트")
        self.assertIn("변경 시도나 작업자를 확인한 것은 아닙니다", self.alerts("ip_mismatch")[0].message)

    def test_agent_ip_and_mac_changes_accumulate_in_existing_ip_history_without_duplicates(self):
        registration = self.enrolled()
        initial = [
            adapter(["192.0.2.11", "192.0.2.10"], ipv6=["2001:db8::11", "2001:db8::10"]),
            adapter(["203.0.113.20"], adapter_id="wifi-2"),
        ]
        self.report(registration, initial)
        history = self.ip_history()
        self.assertEqual(len(history), 2)
        self.assertTrue(all(row["old_ip_address"] is None and row["old_mac_address"] is None for row in history))
        self.assertTrue(all("최초 IP/MAC 확인" in row["change_reason"] for row in history))
        self.assertTrue(all(row["source_id"] == self.device.id and row["device_id"] == self.device.id for row in history))
        first_ids = {row["id"] for row in history}
        reordered = copy.deepcopy(initial[::-1])
        for item in reordered:
            item["ipv4"].reverse()
            item["ipv6"].reverse()
        self.report(registration, reordered)
        self.assertEqual({row["id"] for row in self.ip_history()}, first_ids)

        changed_ip = copy.deepcopy(initial)
        changed_ip[0]["ipv4"] = [{"address": "192.0.2.30", "netmask": "255.255.255.0"}]
        self.report(registration, changed_ip)
        history = self.ip_history()
        self.assertEqual(len(history), 3)
        ip_delta = history[-1]
        self.assertEqual(set(ip_delta["old_ip_address"].split(", ")), {
            "192.0.2.10", "192.0.2.11", "2001:db8::10", "2001:db8::11",
        })
        self.assertEqual(set(ip_delta["new_ip_address"].split(", ")), {
            "192.0.2.30", "2001:db8::10", "2001:db8::11",
        })
        self.assertEqual(ip_delta["old_mac_address"], ip_delta["new_mac_address"])
        details = json.loads(ip_delta["notes"][ip_delta["notes"].index("{"):])
        self.assertEqual(details["adapter_id"], "ethernet-1")
        self.assertEqual(details["reference_ip"], "198.51.100.1")
        self.assertEqual(details["after"]["ipv4"], changed_ip[0]["ipv4"])
        self.assertIn("변경 시도·작업자 확인 아님", ip_delta["notes"])

        changed_mac = copy.deepcopy(changed_ip)
        changed_mac[0]["macAddress"] = "02:22:33:44:55:66"
        self.report(registration, changed_mac)
        self.report(registration, changed_mac)
        history = self.ip_history()
        self.assertEqual(len(history), 4)
        mac_delta = history[-1]
        self.assertEqual(mac_delta["old_ip_address"], mac_delta["new_ip_address"])
        self.assertEqual(mac_delta["old_mac_address"], "02:11:22:33:44:55")
        self.assertEqual(mac_delta["new_mac_address"], "02:22:33:44:55:66")
        foreign = self.enrolled(self.other)
        self.report(foreign, [adapter(["198.51.100.80"])])
        self.assertEqual([row["id"] for row in self.ip_history()], [row["id"] for row in history])
        self.assertEqual(self.db.get(Device, self.device.id).ip_address, "198.51.100.1")
        self.assertEqual(self.db.get(Device, self.device.id).mac_address, "02:AA:BB:CC:DD:01")
        serialized = json.dumps(history)
        self.assertNotIn(registration["deviceToken"], serialized)
        self.assertNotIn(registration["enrollmentToken"], serialized)

    def test_cidr_manual_references_match_addresses_without_rewriting_the_inventory_text(self):
        configured = "192.0.2.10/24; 198.51.100.20/25"
        self.device.ip_address = configured
        self.db.commit()
        registration = self.enrolled()
        self.report(registration, [adapter(["198.51.100.20", "192.0.2.10", "203.0.113.5"])])
        monitor = self.monitor()
        self.assertEqual(monitor["status"], "normal")
        self.assertEqual(monitor["source"], "inventory")
        self.assertEqual(monitor["expected_ipv4"], ["192.0.2.10", "198.51.100.20"])
        self.assertFalse(monitor["reference_error"])
        self.assertEqual(self.db.get(Device, self.device.id).ip_address, configured)
        self.assertEqual(self.alerts(), [])

    def test_invalid_manual_reference_never_falls_back_to_a_normal_first_seen_baseline(self):
        self.device.ip_address = None
        self.db.commit()
        registration = self.enrolled()
        observed = [adapter(["192.0.2.10"])]
        self.report(registration, observed)
        self.assertEqual(self.monitor()["status"], "normal")
        self.assertEqual(self.monitor()["source"], "first_seen")
        for invalid in ("not-an-ip", "192.0.2.10, not-an-ip", "192.0.2.10/99"):
            with self.subTest(reference=invalid):
                self.device.ip_address = invalid
                self.db.commit()
                self.report(registration, observed)
                monitor = self.monitor()
                self.assertEqual(monitor["source"], "inventory")
                self.assertEqual(monitor["status"], "unknown")
                self.assertTrue(monitor["reference_error"])
                self.assertEqual(monitor["expected_ipv4"], [])
                self.assertEqual(monitor["baseline_ipv4"], ["192.0.2.10"])
                self.assertEqual(self.db.get(Device, self.device.id).ip_address, invalid)
                self.assertEqual(self.alerts(), [])

    def test_stable_samples_and_adapter_address_reordering_do_not_duplicate_logs_or_alerts(self):
        registration = self.enrolled()
        original = [
            adapter(["192.0.2.11", "192.0.2.10"], ipv6=["2001:db8::11", "2001:db8::10"]),
            adapter(["203.0.113.5"], adapter_id="wifi-2"),
        ]
        self.report(registration, original)
        initial_log_ids = [row.id for row in self.audit_rows()]
        initial_alert_ids = [row.id for row in self.alerts()]
        checked_at = self.monitor()["checked_at"]
        for _ in range(3):
            self.report(registration, original)
        reordered = copy.deepcopy(original[::-1])
        for item in reordered:
            item["ipv4"].reverse()
            item["ipv6"].reverse()
        self.report(registration, reordered, capabilities=CAPS[::-1])

        self.assertEqual([row.id for row in self.audit_rows()], initial_log_ids)
        self.assertEqual([row.id for row in self.alerts()], initial_alert_ids)
        self.assertNotEqual(self.monitor()["checked_at"], checked_at)
        self.assertEqual(self.detail()["agent"]["status"], "online")

    def test_ip_changes_record_old_and_new_snapshots_and_alert_each_distinct_mismatch_once(self):
        registration = self.enrolled()
        before = [adapter(["192.0.2.10"])]
        after = [adapter(["192.0.2.20"])]
        self.report(registration, before)
        self.report(registration, after)
        self.report(registration, after)

        changed = self.audit_rows("heartbeat_state_change")
        self.assertEqual(len(changed), 2)
        delta = changed[-1].changes["network_adapters"]
        self.assertEqual(delta["old"], before)
        self.assertEqual(delta["new"], after)
        self.assertEqual(len(self.audit_rows("ip_mismatch_detected")), 2)
        self.assertEqual(len(self.alerts("ip_mismatch")), 2)
        self.assertEqual(self.db.get(Device, self.device.id).ip_address, "198.51.100.1")

    def test_return_to_configured_ip_emits_a_single_recovery_and_preserves_the_fixed_value(self):
        registration = self.enrolled()
        self.report(registration, [adapter(["192.0.2.10"])])
        # Extra physical addresses are legitimate when every configured IP is
        # present; a secondary interface must not create another incident.
        restored = [adapter([self.device.ip_address, "192.0.2.50"])]
        self.report(registration, restored)
        self.report(registration, restored)

        monitor = self.monitor()
        self.assertEqual(monitor["status"], "normal")
        self.assertFalse(monitor["alert_active"])
        self.assertEqual(len(self.audit_rows("ip_restored")), 1)
        self.assertEqual(len(self.alerts("ip_restored")), 1)
        self.assertEqual(len(self.alerts("ip_mismatch")), 1)
        self.assertEqual(self.db.get(Device, self.device.id).ip_address, "198.51.100.1")

    def test_manual_reference_change_does_not_claim_the_pc_restored_its_ip(self):
        registration = self.enrolled()
        unchanged_observation = [adapter(["192.0.2.10"])]
        self.report(registration, unchanged_observation)
        self.assertEqual(self.monitor()["status"], "mismatch")
        response = self.client.put(
            f"/api/v1/devices/{self.device.id}", json={"ip_address": "192.0.2.10"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.report(registration, unchanged_observation)
        self.report(registration, unchanged_observation)

        monitor = self.monitor()
        self.assertEqual(monitor["status"], "normal")
        self.assertFalse(monitor["alert_active"])
        self.assertEqual(monitor["expected_ipv4"], ["192.0.2.10"])
        self.assertEqual(monitor["observed_ipv4"], ["192.0.2.10"])
        self.assertEqual(self.db.get(Device, self.device.id).ip_address, "192.0.2.10")
        self.assertEqual(len(self.audit_rows("ip_monitoring_reference_changed")), 1)
        self.assertEqual(len(self.alerts("ip_reference_resolved")), 1)
        self.assertEqual(self.audit_rows("ip_restored"), [])
        self.assertEqual(self.alerts("ip_restored"), [])
        self.assertEqual(len(self.alerts("ip_mismatch")), 1)

    def test_reference_change_during_unknown_samples_still_resolves_the_original_incident_honestly(self):
        registration = self.enrolled()
        unchanged_observation = [adapter(["192.0.2.10"])]
        self.report(registration, unchanged_observation)
        response = self.client.put(
            f"/api/v1/devices/{self.device.id}", json={"ip_address": "192.0.2.10"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.report(registration, [])
        self.assertEqual(self.monitor()["status"], "unknown")
        self.assertTrue(self.monitor()["alert_active"])
        self.report(registration, unchanged_observation)
        self.report(registration, unchanged_observation)

        self.assertEqual(self.monitor()["status"], "normal")
        self.assertFalse(self.monitor()["alert_active"])
        self.assertEqual(len(self.alerts("ip_reference_resolved")), 1)
        self.assertEqual(self.alerts("ip_restored"), [])
        self.assertEqual(self.audit_rows("ip_restored"), [])

    def test_unconfigured_device_uses_a_separate_first_seen_baseline_without_writing_inventory(self):
        self.device.ip_address = None
        self.db.commit()
        registration = self.enrolled()
        self.report(registration, [adapter(["192.0.2.10"])])
        initial = self.monitor()
        self.assertEqual(initial["source"], "first_seen")
        self.assertEqual(initial["status"], "normal")
        self.assertEqual(initial["baseline_ipv4"], ["192.0.2.10"])
        self.assertIsNone(self.db.get(Device, self.device.id).ip_address)
        self.assertEqual(len(self.audit_rows("ip_baseline_recorded")), 1)
        self.assertEqual(self.alerts(), [])

        self.report(registration, [adapter(["192.0.2.20"])])
        changed = self.monitor()
        self.assertEqual(changed["status"], "mismatch")
        self.assertEqual(changed["expected_ipv4"], ["192.0.2.10"])
        self.assertEqual(changed["baseline_ipv4"], ["192.0.2.10"])
        self.report(registration, [adapter(["192.0.2.10"])])
        self.assertEqual(self.monitor()["status"], "normal")
        self.assertEqual(len(self.audit_rows("ip_baseline_recorded")), 1)
        self.assertEqual(len(self.alerts("ip_mismatch")), 1)
        self.assertEqual(len(self.alerts("ip_restored")), 1)
        self.assertIsNone(self.db.get(Device, self.device.id).ip_address)

    def test_empty_virtual_or_unusable_samples_are_unknown_and_never_falsely_recover_an_incident(self):
        registration = self.enrolled()
        self.report(registration, [adapter(["192.0.2.10"])])
        for sample in (
            [],
            [adapter([], ipv6=["2001:db8::10"])],
            [adapter([self.device.ip_address], adapter_id="vpn-1", physical=False)],
            [adapter(["127.0.0.1", "169.254.10.20", "0.0.0.0"])],
        ):
            with self.subTest(sample=sample):
                self.report(registration, sample)
                monitor = self.monitor()
                self.assertEqual(monitor["status"], "unknown")
                self.assertEqual(monitor["observed_ipv4"], [])
                self.assertTrue(monitor["alert_active"])
                self.assertEqual(len(self.alerts("ip_mismatch")), 1)
                self.assertEqual(self.alerts("ip_restored"), [])
                self.assertEqual(self.audit_rows("ip_restored"), [])

        # Returning to the same unresolved mismatch must not duplicate its
        # alert merely because intervening samples had no usable physical IP.
        self.report(registration, [adapter(["192.0.2.10"])])
        self.assertEqual(len(self.alerts("ip_mismatch")), 1)
        self.assertEqual(self.monitor()["status"], "mismatch")

    def test_omitted_inventory_keeps_prior_monitor_and_first_virtual_sample_cannot_set_a_baseline(self):
        self.device.ip_address = None
        self.db.commit()
        registration = self.enrolled()
        self.report(registration, [adapter(["192.0.2.10"], physical=False)])
        monitor = self.monitor()
        self.assertEqual(monitor["status"], "unknown")
        self.assertEqual(monitor["source"], "unconfigured")
        self.assertEqual(monitor["baseline_ipv4"], [])
        self.assertEqual(self.audit_rows("ip_baseline_recorded"), [])

        self.report(registration, [adapter(["192.0.2.20"])])
        known = self.detail()["agent"]
        response = self.heartbeat(registration)
        self.assertEqual(response.status_code, 200, response.text)
        retained = self.detail()["agent"]
        self.assertEqual(retained["network_monitor"], known["network_monitor"])
        self.assertEqual(retained["network_updated_at"], known["network_updated_at"])
        self.assertEqual(retained["network_adapters"], known["network_adapters"])
        self.assertEqual(self.alerts(), [])

    def test_hostname_os_agent_version_and_boot_changes_have_old_new_values_once(self):
        registration = self.enrolled()
        network = [adapter([self.device.ip_address])]
        self.report(registration, network)
        overrides = {
            "hostname": "RENAMED-PC", "os": "Microsoft Windows 11 Updated",
            "agentVersion": "0.5.0", "bootTime": "2026-10-25T02:00:00Z",
        }
        self.report(registration, network, **overrides)
        self.report(registration, network, **overrides)
        rows = self.audit_rows("heartbeat_state_change")
        self.assertEqual(len(rows), 2)
        changes = rows[-1].changes
        self.assertEqual(changes["hostname"], {"old": "TEST-PC", "new": "RENAMED-PC"})
        self.assertEqual(changes["os_version"], {"old": "Microsoft Windows 11", "new": overrides["os"]})
        self.assertEqual(changes["agent_version"], {"old": "0.3.0", "new": "0.5.0"})
        self.assertEqual(changes["boot_time"], {
            "old": service.iso(datetime(2026, 10, 25, 1)),
            "new": service.iso(datetime(2026, 10, 25, 2)),
        })
        self.assertNotIn("network_adapters", changes)
        self.assertEqual(self.alerts(), [])

    def test_stale_network_sample_is_unknown_even_when_heartbeat_stays_online(self):
        registration = self.enrolled()
        self.report(registration, [adapter(["192.0.2.10"])])
        initial_checked_at = self.monitor()["checked_at"]
        initial_logs = [row.id for row in self.audit_rows()]
        for _ in range(4):
            response = self.heartbeat(registration)
            self.assertEqual(response.status_code, 200, response.text)
            self.now += timedelta(seconds=15)
        state = self.detail()["agent"]
        monitor = state["network_monitor"]
        self.assertEqual(state["status"], "online")
        self.assertEqual(monitor["status"], "unknown")
        self.assertEqual(monitor["last_status"], "mismatch")
        self.assertTrue(monitor["stale"])
        self.assertTrue(monitor["alert_active"])
        self.assertEqual(monitor["checked_at"], initial_checked_at)
        self.assertEqual([row.id for row in self.audit_rows()], initial_logs)
        self.assertEqual(len(self.alerts("ip_mismatch")), 1)
        self.assertEqual(self.alerts("ip_restored"), [])

    def test_device_logs_are_authenticated_paginated_scoped_and_do_not_expose_credentials(self):
        registration = self.enrolled()
        self.report(registration, [adapter(["192.0.2.10"])])
        self.db.add_all([
            AuditLog(entity_type="device", entity_id=self.device.id, action="manual_note", changes={"label": "local-device"}),
            AuditLog(entity_type="device_agent", entity_id=self.other.id, action="foreign_agent", changes={"label": "other-device"}),
            AuditLog(entity_type="license", entity_id=self.device.id, action="foreign_entity", changes={"label": "unrelated-license"}),
        ])
        self.db.commit()
        url = f"/api/v1/devices/{self.device.id}/logs"
        app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.get(url).status_code, 401)
        with patch("app.api.deps.verify_token", new=AsyncMock(side_effect=HTTPException(401, "not a user token"))):
            self.assertEqual(self.client.get(url, headers={"Authorization": "Bearer " + registration["deviceToken"]}).status_code, 401)
        app.dependency_overrides[get_current_user] = lambda: self.actor
        self.actor.role = "user"
        response = self.client.get(url, params={"page": 1, "size": 2})
        self.assertEqual(response.status_code, 200, response.text)
        page = response.json()
        self.assertEqual(page["page"], 1)
        self.assertEqual(page["size"], 2)
        self.assertEqual(len(page["items"]), 2)
        self.assertGreater(page["total"], 2)
        self.assertGreater(page["pages"], 1)
        next_response = self.client.get(url, params={"page": 2, "size": 2})
        self.assertEqual(next_response.status_code, 200, next_response.text)
        self.assertTrue({item["id"] for item in page["items"]}.isdisjoint(item["id"] for item in next_response.json()["items"]))
        all_response = self.client.get(url, params={"size": 100})
        self.assertEqual(all_response.status_code, 200, all_response.text)
        items = all_response.json()["items"]
        actions = {item["action"] for item in items}
        self.assertIn("heartbeat_state_change", actions)
        self.assertIn("ip_mismatch_detected", actions)
        self.assertIn("manual_note", actions)
        self.assertNotIn("foreign_agent", actions)
        self.assertNotIn("foreign_entity", actions)
        for item in items:
            self.assertEqual(item["entity_id"], self.device.id)
            parsed = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
            self.assertIsNotNone(parsed.tzinfo)
            self.assertEqual(parsed.utcoffset(), timedelta(0))
        serialized = json.dumps(items)
        self.assertNotIn(registration["deviceToken"], serialized)
        self.assertNotIn(registration["enrollmentToken"], serialized)
        self.assertEqual(self.client.get("/api/v1/devices/999999/logs").status_code, 404)

    def test_recycled_setting_and_license_ids_use_recorded_device_associations_only(self):
        old_ids = set()
        current_ids = set()
        legacy_ids = set()
        for endpoint, entity_type in (
            ("computer-settings", "computer_setting"),
            ("device-licenses", "device_license"),
        ):
            with self.subTest(entity_type=entity_type):
                old = self.client.post(f"/api/v1/{endpoint}", json={"device_id": self.other.id})
                self.assertEqual(old.status_code, 201, old.text)
                child_id = old.json()["id"]
                changed = self.client.put(f"/api/v1/{endpoint}/{child_id}", json={"notes": "Former PC setting"})
                self.assertEqual(changed.status_code, 200, changed.text)
                # Older releases logged only a child ID, with no durable device
                # association. Such a row must remain global-only after reuse.
                legacy = AuditLog(entity_type=entity_type, entity_id=child_id,
                                  action="legacy_unscoped", changes={"notes": "Unproven historical owner"})
                self.db.add(legacy)
                self.db.commit()
                legacy_ids.add(legacy.id)
                removed = self.client.delete(f"/api/v1/{endpoint}/{child_id}")
                self.assertEqual(removed.status_code, 200, removed.text)
                self.db.expire_all()
                previous_rows = self.db.scalars(select(AuditLog).where(AuditLog.entity_type == entity_type)).all()
                previous_ids = {row.id for row in previous_rows}
                old_ids.update(previous_ids)

                created = self.client.post(f"/api/v1/{endpoint}", json={"device_id": self.device.id})
                self.assertEqual(created.status_code, 201, created.text)
                self.assertEqual(created.json()["id"], child_id, "The SQLite fixture must actually recycle the child ID.")
                changed = self.client.put(f"/api/v1/{endpoint}/{child_id}", json={"notes": "Current PC setting"})
                self.assertEqual(changed.status_code, 200, changed.text)
                removed = self.client.delete(f"/api/v1/{endpoint}/{child_id}")
                self.assertEqual(removed.status_code, 200, removed.text)
                self.db.expire_all()
                rows = self.db.scalars(select(AuditLog).where(AuditLog.entity_type == entity_type)).all()
                new_rows = [row for row in rows if row.id not in previous_ids]
                self.assertEqual({row.action for row in new_rows}, {"create", "update", "delete"})
                self.assertTrue(all(row.changes["device_id"] == self.device.id for row in new_rows))
                current_ids.update(row.id for row in new_rows)

        # Both child records have now been deleted; their proven history still
        # belongs to this PC, without needing a join to a current child row.
        current = self.client.get(f"/api/v1/devices/{self.device.id}/logs", params={"size": 100})
        self.assertEqual(current.status_code, 200, current.text)
        visible = {row["id"] for row in current.json()["items"]}
        self.assertTrue(current_ids.issubset(visible))
        self.assertTrue(old_ids.isdisjoint(visible))
        former = self.client.get(f"/api/v1/devices/{self.other.id}/logs", params={"size": 100})
        self.assertEqual(former.status_code, 200, former.text)
        former_visible = {row["id"] for row in former.json()["items"]}
        self.assertTrue((old_ids - legacy_ids).issubset(former_visible))
        self.assertTrue(current_ids.isdisjoint(former_visible))
        self.assertTrue(legacy_ids.isdisjoint(visible | former_visible))
        self.assertEqual(set(self.db.scalars(select(AuditLog.id).where(AuditLog.id.in_(legacy_ids)))), legacy_ids)

    def test_recycled_device_id_does_not_inherit_the_former_pc_agent_or_command_history(self):
        old = self.client.post("/api/v1/devices", json={"serial_number": "REUSED-OLD-PC", "device_type": "desktop"})
        self.assertEqual(old.status_code, 201, old.text)
        recycled_id = old.json()["id"]
        self.db.add_all([
            AuditLog(entity_type=entity_type, entity_id=recycled_id, action=f"former_{entity_type}",
                     changes={"label": "Former PC history"}, timestamp=datetime(2099, 1, 1))
            for entity_type in ("device", "device_agent", "device_command")
        ])
        self.db.commit()
        removed = self.client.delete(f"/api/v1/devices/{recycled_id}")
        self.assertEqual(removed.status_code, 200, removed.text)
        self.db.expire_all()
        previous_ids = set(self.db.scalars(select(AuditLog.id).where(
            AuditLog.entity_id == recycled_id,
            AuditLog.entity_type.in_(["device", "device_agent", "device_command"]),
        )))

        new = self.client.post("/api/v1/devices", json={"serial_number": "REUSED-NEW-PC", "device_type": "desktop"})
        self.assertEqual(new.status_code, 201, new.text)
        self.assertEqual(new.json()["id"], recycled_id, "The SQLite fixture must actually recycle the device ID.")
        self.db.expire_all()
        creation = self.db.scalars(select(AuditLog).where(
            AuditLog.entity_type == "device", AuditLog.entity_id == recycled_id, AuditLog.action == "create",
        ).order_by(AuditLog.id.desc())).first()
        self.assertIsNotNone(creation)
        new_creation_id = creation.id
        self.assertNotIn(new_creation_id, previous_ids)
        current_device = self.db.get(Device, recycled_id)
        registration = self.enrolled(current_device)
        self.report(registration, [adapter(["192.0.2.80"])])
        response = self.client.get(f"/api/v1/devices/{recycled_id}/logs", params={"size": 100})
        self.assertEqual(response.status_code, 200, response.text)
        items = response.json()["items"]
        visible = {row["id"] for row in items}
        self.assertIn(new_creation_id, visible)
        self.assertTrue(previous_ids.isdisjoint(visible))
        self.assertTrue(all(row["id"] >= new_creation_id for row in items))
        self.assertIn("heartbeat_state_change", {row["action"] for row in items})
        self.assertTrue(any(row["changes"].get("agent_id") == registration["deviceId"] for row in items))
        self.assertEqual(current_device.serial_number, "REUSED-NEW-PC")
        self.assertEqual(set(self.db.scalars(select(AuditLog.id).where(AuditLog.id.in_(previous_ids)))), previous_ids)


if __name__ == "__main__":
    unittest.main()
