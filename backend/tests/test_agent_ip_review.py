import copy
import unittest
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.main import app
from app.api.deps import get_current_user
from app.models.audit_log import AuditLog
from app.models.device_agent import DeviceAgent
from app.models.device_inventory import Device
from app.services import device_agent_service as service
from tests.test_device_agents import AgentApiFixture
from tests.test_device_agents import ADAPTERS


class AgentIpReviewApiTest(AgentApiFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.registration = self.enrolled()
        self.online(self.registration)
        self.incident_id = str(uuid4())
        self.url = f"/api/v1/devices/{self.device.id}/agent/ip-review"
        self.monitor = {
            "status": "mismatch", "source": "inventory", "expected_ipv4": ["198.51.100.1"],
            "observed_ipv4": ["192.0.2.10"], "baseline_ipv4": ["192.0.2.10"],
            "checked_at": service.iso(self.now), "alert_active": True,
            "incident": "test-only-incident-signature",
            "review": {"incident_id": self.incident_id, "state": "open", "note": None,
                       "reviewed_by": None, "reviewed_at": None},
        }
        self.save_monitor(self.monitor)

    def save_monitor(self, value):
        self.db.expire_all()
        agent = self.db.get(DeviceAgent, self.registration["deviceId"])
        agent.network_monitor = copy.deepcopy(value)
        self.db.commit()

    def review(self, action="start", note="현장 담당자와 네트워크 설정을 확인합니다.", **changes):
        return self.client.post(self.url, json={"incidentId": self.incident_id, "action": action, "note": note, **changes})

    def test_admin_only_nonempty_note_and_start_audits_actor_without_changing_manual_ip(self):
        app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.review().status_code, 401)
        app.dependency_overrides[get_current_user] = lambda: self.actor
        for role in ("user", "manager"):
            self.actor.role = role
            self.assertEqual(self.review().status_code, 403)
        self.actor.role = "admin"
        for note in ("", "   ", "x" * 1001, "bad\x00note"):
            self.assertEqual(self.review(note=note).status_code, 422)
        response = self.review(note=" 현장 확인 시작\n담당자에게 연락함 ")
        self.assertEqual(response.status_code, 200, response.text)
        reviewed = response.json()["network_monitor"]["review"]
        self.assertEqual(reviewed["state"], "reviewing")
        self.assertEqual(reviewed["note"], "현장 확인 시작\n담당자에게 연락함")
        self.assertEqual(reviewed["reviewed_by"], self.actor.name)
        self.assertEqual(reviewed["reviewed_at"], service.iso(self.now))
        self.db.expire_all()
        self.assertEqual(self.db.get(Device, self.device.id).ip_address, "198.51.100.1")
        log = self.db.scalar(select(AuditLog).where(AuditLog.action == "ip_review_started"))
        self.assertEqual(log.user_id, self.actor.id)
        self.assertEqual(log.changes["review"]["old"]["state"], "open")
        self.assertEqual(log.changes["review"]["new"]["note"], reviewed["note"])

    def test_stale_incident_is_rejected_without_overwriting_current_review(self):
        changed = copy.deepcopy(self.monitor)
        changed["review"]["incident_id"] = str(uuid4())
        self.save_monitor(changed)
        self.assertEqual(self.review().status_code, 409)
        self.db.expire_all()
        self.assertEqual(self.db.get(DeviceAgent, self.registration["deviceId"]).network_monitor, changed)
        self.assertEqual(self.review(incidentId=changed["review"]["incident_id"]).status_code, 200)

    def test_resolve_requires_fresh_normal_observation_no_alert_and_online_worker(self):
        self.assertEqual(self.review(action="resolve").status_code, 409)
        normal = copy.deepcopy(self.monitor)
        normal["status"] = "normal"
        normal["observed_ipv4"] = normal["expected_ipv4"]
        self.save_monitor(normal)
        self.assertEqual(self.review(action="resolve").status_code, 409, "active alert must block resolution")
        normal["alert_active"] = False
        normal["checked_at"] = service.iso(self.now - timedelta(seconds=60))
        self.save_monitor(normal)
        self.assertEqual(self.review(action="resolve").status_code, 409)
        normal["checked_at"] = service.iso(self.now + timedelta(seconds=1))
        self.save_monitor(normal)
        self.assertEqual(self.review(action="resolve").status_code, 409)
        normal["checked_at"] = service.iso(self.now)
        self.save_monitor(normal)
        self.db.get(DeviceAgent, self.registration["deviceId"]).last_seen_at = self.now - timedelta(seconds=60)
        self.db.commit()
        self.assertEqual(self.review(action="resolve").status_code, 409)

    def test_normal_recovery_can_be_resolved_with_note_and_history_keeps_prior_review(self):
        start = self.review(note="스위치 포트와 고정 IP를 점검 중입니다.")
        self.assertEqual(start.status_code, 200)
        normal = copy.deepcopy(self.monitor)
        normal.update(status="normal", alert_active=False, observed_ipv4=["198.51.100.1"], incident=None)
        normal["review"] = start.json()["network_monitor"]["review"]
        self.save_monitor(normal)
        self.assertEqual(self.detail()["agent"]["network_monitor"]["review"]["state"], "reviewing")
        response = self.review(action="resolve", note="고정 IP 설정을 확인했고 최신 수신 값이 일치합니다.")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["network_monitor"]["review"]["state"], "resolved")
        self.assertEqual(self.review().status_code, 409)
        self.assertEqual(self.review(action="resolve").status_code, 409)
        self.db.expire_all()
        events = self.db.scalars(select(AuditLog).where(AuditLog.action.in_(["ip_review_started", "ip_review_resolved"])).order_by(AuditLog.id)).all()
        self.assertEqual([item.action for item in events], ["ip_review_started", "ip_review_resolved"])
        self.assertEqual(events[1].changes["review"]["old"]["note"], "스위치 포트와 고정 IP를 점검 중입니다.")
        self.assertEqual(self.db.get(Device, self.device.id).ip_address, "198.51.100.1")

    def test_start_can_record_work_while_pc_offline_but_does_not_claim_resolution(self):
        self.now += timedelta(seconds=61)
        response = self.review(note="PC가 오프라인이어서 현장 확인을 요청했습니다.")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "offline")
        self.assertEqual(response.json()["network_monitor"]["review"]["state"], "reviewing")
        self.assertEqual(self.review(action="resolve").status_code, 409)

    def test_fixed_ip_change_after_normal_snapshot_blocks_resolution_until_new_matching_sample(self):
        normal = copy.deepcopy(self.monitor)
        normal.update(status="normal", alert_active=False, observed_ipv4=["198.51.100.1"], incident=None)
        self.save_monitor(normal)
        changed = self.client.put(f"/api/v1/devices/{self.device.id}", json={"ip_address": "198.51.100.20"})
        self.assertEqual(changed.status_code, 200, changed.text)
        response = self.review(action="resolve", note="기존 정상 표본만으로 완료하면 안 됩니다.")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.detail()["agent"]["network_monitor"]["review"]["state"], "open")
        matching = copy.deepcopy(ADAPTERS)
        matching[0]["ipv4"] = [{"address": "198.51.100.20", "netmask": "255.255.255.0"}]
        self.assertEqual(self.heartbeat(self.registration, networkAdapters=matching).status_code, 200)
        review = self.detail()["agent"]["network_monitor"]["review"]
        resolved = self.review(action="resolve", incidentId=review["incident_id"], note="변경한 기준 IP와 새 수신 표본을 확인했습니다.")
        self.assertEqual(resolved.status_code, 200, resolved.text)
        self.db.expire_all()
        self.assertEqual(self.db.get(Device, self.device.id).ip_address, "198.51.100.20")


if __name__ == "__main__":
    unittest.main()
