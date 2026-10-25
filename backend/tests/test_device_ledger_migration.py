import copy
import json
import shutil
import sqlite3
import tempfile
import unittest
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, JSON, MetaData, Table, create_engine, select, text
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import device_ledger_migration_service as migration
from scripts import migrate_agent_release as guard
from scripts.export_device_ledger import export


class DeviceLedgerMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_dir = tempfile.TemporaryDirectory(prefix="itam-ledger-schema-")
        cls.template = Path(cls.template_dir.name) / "template.db"
        guard.create_legacy(cls.template)
        guard.alembic("stamp", guard.BASELINE, cls.template)
        guard.alembic("upgrade", guard.LEGACY_BRANCH, cls.template)
        guard.alembic("upgrade", "head", cls.template)

    @classmethod
    def tearDownClass(cls):
        cls.template_dir.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="itam-ledger-test-")
        self.destination = Path(self.directory.name) / "destination.db"
        self.source = Path(self.directory.name) / "source.db"
        shutil.copyfile(self.template, self.destination)
        shutil.copyfile(self.template, self.source)
        self.engine = create_engine("sqlite:///" + str(self.destination), connect_args={"check_same_thread": False})
        self.sessions = sessionmaker(bind=self.engine)
        source_engine = create_engine("sqlite:///" + str(self.source))
        with source_engine.begin() as db:
            self.insert(db, "users", 7, email="historical@example.test", name="원본 작성자", role="user", is_active=True)
            self.insert(db, "asset_categories", 2, name="Software", slug="software")
            self.insert(db, "vendors", 3, name="Fixture vendor")
            self.insert(db, "assets", 4, asset_tag="SRC-LIC-001", name="Fixture software asset", category_id=2, status="in_stock", vendor_id=3)
            self.insert(db, "software_licenses", 5, asset_id=4, license_key="FIXTURE-KEY", license_type="per_seat", seats_total=10, seats_used=1, vendor_id=3)
            self.insert(db, "purchases", 6, purchase_number="SRC-PURCHASE-001", item_type="device", item_name="Fixture PC", quantity=1, status="registered", details={})
            self.insert(db, "devices", 7, serial_number=" DEV-001 ", user_name="원본 사용자", device_type="desktop", status="assigned", ip_address="192.0.2.10", notes="원본 메모")
            self.insert(db, "devices", 8, serial_number="", device_type="laptop", status="stock")
            self.insert(db, "device_licenses", 9, device_id=7, hangul=True)
            self.insert(db, "computer_settings", 10, device_id=7, core_isolation=True)
            self.insert(db, "device_usage_history", 11, device_id=7, serial_number=" DEV-001 ", user_name="과거 사용자", change_reason="사용 이력")
            self.insert(db, "ip_change_history", 12, source_type="device", source_id=7, device_id=7, old_ip_address="192.0.2.9", new_ip_address="192.0.2.10", change_reason="이전 변경")
            self.insert(db, "license_assignments", 13, license_id=5, device_id=7)
            self.insert(db, "purchase_allocations", 14, purchase_id=6, resource_type="device", resource_id=7, quantity=1)
            self.insert(db, "audit_logs", 15, entity_type="device", entity_id=7, action="create", changes={"notes": "원본 메모"}, user_id=7, user_name="원본 작성자")
            self.insert(db, "audit_logs", 16, entity_type="device_agent", entity_id=7, action="heartbeat_state_change", changes={"status": "online"}, user_name="Windows Agent")
            self.insert(db, "audit_logs", 17, entity_type="device_command", entity_id=7, action="command_ack", changes={"status": "accepted"})
        source_engine.dispose()
        with sqlite3.connect(self.source) as db:
            self.payload = export(db, str(uuid4()))
        with self.engine.begin() as db:
            self.insert(db, "users", 100, email="operator@example.test", name="운영 관리자", role="admin", is_active=True)
            self.insert(db, "devices", 501, serial_number="OPERATING-001", device_type="desktop", user_name="기존 사용자", status="assigned", notes="변경 금지")
            self.insert(db, "audit_logs", 500, entity_type="device", entity_id=501, action="create", changes={"notes": "기존 운영 기록"}, user_id=100)
        with self.sessions() as db:
            self.actor = db.get(User, 100)
            db.expunge(self.actor)
        self.original_overrides = app.dependency_overrides.copy()
        def request_db():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = request_db
        app.dependency_overrides[get_current_user] = lambda: self.actor
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides = self.original_overrides
        self.engine.dispose()
        self.directory.cleanup()

    @staticmethod
    def insert(db, table_name, identifier, **overrides):
        table = Table(table_name, MetaData(), autoload_with=db)
        values = {column.name: None for column in table.columns}
        values["id"] = identifier
        for column in table.columns:
            if column.name == "id":
                continue
            if column.name in {"created_at", "updated_at", "timestamp"} or isinstance(column.type, DateTime) and not column.nullable:
                values[column.name] = datetime(2026, 1, 2, 3, 4, 5)
            elif not column.nullable:
                values[column.name] = False if isinstance(column.type, Boolean) else 0 if isinstance(column.type, (Integer, Float)) else {} if isinstance(column.type, JSON) else date(2026, 1, 2) if isinstance(column.type, Date) else "fixture"
        values.update(overrides)
        db.execute(table.insert().values(**values))

    def raw(self, payload=None):
        return json.dumps(payload or self.payload, ensure_ascii=False, separators=(",", ":")).encode()

    def preview(self, payload=None):
        return self.client.post("/api/v1/devices/migration/preview", files={"file": ("private-ledger.json", self.raw(payload), "application/json")})

    def apply(self, preview, payload=None):
        return self.client.post("/api/v1/devices/migration/apply", files={"file": ("private-ledger.json", self.raw(payload), "application/json")}, data={"preview_fingerprint": preview["preview_fingerprint"]})

    def snapshot(self):
        with sqlite3.connect(self.destination) as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            return {name: Counter(migration.canonical(row) for row in db.execute('SELECT * FROM "' + name + '"')) for name in tables}

    def assert_preserved(self, before):
        after = self.snapshot()
        for name, rows in before.items():
            self.assertFalse(rows - after[name], name)

    def test_preview_readonly_then_bounded_import_preserves_all_operating_rows_links_history_and_blank_identity(self):
        before = self.snapshot()
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json()
        self.assertTrue(preview["can_apply"])
        self.assertEqual(preview["tables"]["devices"]["create"], 2)
        self.assertEqual(preview["summary"]["manual_review"], 1)
        self.assertEqual(self.snapshot(), before)
        applied = self.apply(preview)
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertTrue(applied.json()["applied"])
        self.assert_preserved(before)
        with sqlite3.connect(self.destination) as db:
            device_id = db.execute("SELECT id FROM devices WHERE serial_number=' DEV-001 '").fetchone()[0]
            self.assertEqual(db.execute("SELECT COUNT(*) FROM devices WHERE serial_number='' ").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM notifications WHERE type='device_identity_review'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM license_assignments a JOIN software_licenses l ON l.id=a.license_id JOIN assets s ON s.id=l.asset_id WHERE a.device_id=? AND s.asset_tag='SRC-LIC-001'", (device_id,)).fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM purchase_allocations a JOIN purchases p ON p.id=a.purchase_id WHERE a.resource_id=? AND p.purchase_number='SRC-PURCHASE-001'", (device_id,)).fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT source_id,device_id FROM ip_change_history").fetchone(), (device_id, device_id))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM device_agents").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM device_commands").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
            audit = db.execute("SELECT action,user_name,changes FROM audit_logs WHERE entity_type='device' AND entity_id=? AND action='history_create'", (device_id,)).fetchone()
            self.assertEqual(audit[0], "history_create")
            self.assertEqual(audit[1], "원본 작성자")
            self.assertEqual(json.loads(audit[2])["_migration_source"]["user_id"], 7)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_exact_batch_retry_and_new_batch_same_source_rows_are_idempotent(self):
        first = self.apply(self.preview().json())
        self.assertEqual(first.status_code, 200, first.text)
        after = self.snapshot()
        replay = self.apply({"preview_fingerprint": "stale-on-purpose"})
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["already_applied"])
        self.assertEqual(replay.json()["receipt"], first.json()["receipt"])
        self.assertEqual(self.snapshot(), after)
        another = copy.deepcopy(self.payload)
        another["batch_id"] = str(uuid4())
        preview = self.preview(another)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["summary"]["create"], 0)
        result = self.apply(preview.json(), another)
        self.assertEqual(result.status_code, 200, result.text)
        with sqlite3.connect(self.destination) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM devices").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0], 1)

    def test_existing_serial_is_reused_without_overwriting_and_child_conflict_is_explicit(self):
        # Remove required parents for this independent matching case.
        for name in ("license_assignments", "purchase_allocations", "assets", "software_licenses", "vendors", "asset_categories", "purchases"):
            self.payload["tables"][name] = []
        with self.engine.begin() as db:
            self.insert(db, "devices", 502, serial_number="dev-001", device_type="desktop", user_name="운영 정보 우선", status="assigned", notes="기존 메모")
            self.insert(db, "device_licenses", 503, device_id=502, hangul=False)
        before = self.snapshot()
        preview = self.preview().json()
        self.assertEqual(preview["tables"]["devices"]["reuse"], 1)
        self.assertEqual(preview["tables"]["device_licenses"]["skip"], 1)
        self.assertIn("existing_device_retained", {item["code"] for item in preview["issues"]})
        self.assertEqual(self.apply(preview).status_code, 200)
        self.assert_preserved(before)

    def test_ambiguous_serial_and_occupied_blank_hold_whole_device_and_prune_unused_parents(self):
        with self.engine.begin() as db:
            self.insert(db, "devices", 502, serial_number="dev-001", device_type="desktop", status="stock")
            self.insert(db, "devices", 503, serial_number="DEV-001", device_type="desktop", status="stock")
            self.insert(db, "devices", 504, serial_number="", device_type="laptop", status="stock")
        preview = self.preview()
        self.assertEqual(preview.status_code, 200, preview.text)
        result = preview.json()
        self.assertFalse(result["can_apply"])
        self.assertEqual(result["tables"]["devices"]["skip"], 2)
        self.assertEqual(result["tables"]["assets"]["create"], 0)
        self.assertEqual(result["tables"]["license_assignments"]["skip"], 1)

    def test_stale_preview_rejected_but_unrelated_agent_audit_append_does_not_break_review(self):
        preview = self.preview().json()
        with self.engine.begin() as db:
            db.execute(text("UPDATE devices SET notes='운영자가 수정함' WHERE id=501"))
        before = self.snapshot()
        self.assertEqual(self.apply(preview).status_code, 409)
        self.assertEqual(self.snapshot(), before)
        preview = self.preview().json()
        with self.engine.begin() as db:
            self.insert(db, "audit_logs", 501, entity_type="device_agent", entity_id=501, action="heartbeat_state_change", changes={"status": "online"})
        self.assertEqual(self.apply(preview).status_code, 200)

    def test_invalid_reference_unknown_credentials_bad_values_and_duplicate_json_never_write(self):
        before = self.snapshot()
        invalid = copy.deepcopy(self.payload)
        invalid["tables"]["assets"] = []
        self.assertEqual(self.preview(invalid).status_code, 422)
        invalid = copy.deepcopy(self.payload)
        invalid["tables"]["devices"][0]["deviceToken"] = "should-never-be-accepted"
        self.assertEqual(self.preview(invalid).status_code, 422)
        invalid = copy.deepcopy(self.payload)
        invalid["tables"]["devices"][0]["purchase_date"] = "not-a-date"
        self.assertEqual(self.preview(invalid).status_code, 422)
        duplicated = b'{"format":"a","format":"b"}'
        self.assertEqual(self.client.post("/api/v1/devices/migration/preview", files={"file": ("x.json", duplicated)}).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/devices/migration/preview", files={"file": ("x.json", b"x" * (migration.MAX_BYTES + 1))}).status_code, 413)
        self.assertEqual(self.snapshot(), before)

    def test_unmapped_prior_device_audit_ids_never_attach_history_to_an_unrelated_operating_device(self):
        history = copy.deepcopy(self.payload["tables"]["audit_logs"][0])
        history.update(id=18, entity_type="device_license", entity_id=9, action="update",
                       changes={"device_id": 7, "previous_device_id": 501, "target_device_id": 501, "hangul": True})
        self.payload["tables"]["audit_logs"].append(history)
        result = self.apply(self.preview().json())
        self.assertEqual(result.status_code, 200, result.text)
        old_logs = self.client.get("/api/v1/devices/501/logs").json()["items"]
        self.assertFalse(any(row["entity_type"] == "device_license" for row in old_logs))
        with self.engine.connect() as db:
            changes = json.loads(db.execute(text("SELECT changes FROM audit_logs WHERE entity_type='device_license'")).scalar_one())
            self.assertNotIn("previous_device_id", changes)
            self.assertNotIn("target_device_id", changes)
            self.assertEqual(changes["_migration_source"]["scope_fields"]["previous_device_id"], 501)
            self.assertNotEqual(changes["device_id"], 501)

    def test_duplicate_semantic_purchase_allocations_and_nonfinite_numbers_are_rejected(self):
        duplicate = copy.deepcopy(self.payload["tables"]["purchase_allocations"][0])
        duplicate["id"] = 99
        self.payload["tables"]["purchase_allocations"].append(duplicate)
        self.assertEqual(self.preview().status_code, 422)
        self.payload["tables"]["purchase_allocations"].pop()
        raw = self.raw().replace(b'"unit_price":null', b'"unit_price":1e400')
        self.assertNotEqual(raw, self.raw())
        self.assertEqual(self.client.post("/api/v1/devices/migration/preview", files={"file": ("x.json", raw)}).status_code, 422)

    def test_legacy_device_type_text_is_preserved_exactly(self):
        self.payload["tables"]["devices"][0]["device_type"] = "legacy workstation"
        result = self.apply(self.preview().json())
        self.assertEqual(result.status_code, 200, result.text)
        with self.engine.connect() as db:
            self.assertEqual(db.execute(text("SELECT device_type FROM devices WHERE serial_number=' DEV-001 '")).scalar_one(), "legacy workstation")

    def test_new_imported_device_gets_creation_anchor_before_source_history_when_numeric_id_is_reused(self):
        with self.engine.begin() as db:
            db.execute(text("DELETE FROM devices WHERE id=501"))
            self.insert(db, "audit_logs", 600, entity_type="device", entity_id=1, action="create", changes={"notes":"former device"})
            self.insert(db, "audit_logs", 601, entity_type="device_agent", entity_id=1, action="heartbeat_state_change", changes={"hostname":"former hostname"})
        before = self.snapshot()
        response = self.apply(self.preview().json())
        self.assertEqual(response.status_code, 200, response.text)
        self.assert_preserved(before)
        logs = self.client.get("/api/v1/devices/1/logs").json()["items"]
        self.assertFalse(any(row["id"] in {600,601} for row in logs))
        self.assertTrue(any(row["action"] == "create" and row["changes"].get("source") == "device_ledger_migration" for row in logs))
        self.assertTrue(any(row["action"] == "history_create" for row in logs))

    def test_authenticated_admin_only_and_imported_private_readers_require_login(self):
        self.actor.role = "manager"
        self.assertEqual(self.preview().status_code, 403)
        self.actor.role = "user"
        self.assertEqual(self.preview().status_code, 403)
        app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.preview().status_code, 401)
        for route in ("audit-logs", "assets", "licenses", "vendors", "locations", "departments", "notifications", "export/assets", "dashboard/stats", "qr/1"):
            self.assertEqual(self.client.get("/api/v1/" + route).status_code, 401, route)

    def test_any_write_failure_rolls_back_devices_parents_children_notifications_and_audit(self):
        with self.engine.begin() as db:
            db.execute(text("CREATE TRIGGER reject_test_batch BEFORE INSERT ON audit_logs WHEN NEW.entity_type='device_ledger_migration' BEGIN SELECT RAISE(ABORT,'test rejection'); END"))
        before = self.snapshot()
        result = self.apply(self.preview().json())
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(self.snapshot(), before)


    def test_numeric_string_unknown_prior_device_scope_is_kept_only_in_origin_metadata(self):
        history = copy.deepcopy(self.payload["tables"]["audit_logs"][0])
        history.update(id=18, entity_type="device_license", entity_id=9, action="update",
                       changes={"device_id": "7", "previous_device_id": "501", "target_device_id": True})
        self.payload["tables"]["audit_logs"].append(history)
        response = self.apply(self.preview().json())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(any(item["entity_type"] == "device_license" for item in self.client.get("/api/v1/devices/501/logs").json()["items"]))
        with self.engine.connect() as db:
            changes = json.loads(db.execute(text("SELECT changes FROM audit_logs WHERE entity_type='device_license'")).scalar_one())
            self.assertNotIn("previous_device_id", changes)
            self.assertNotIn("target_device_id", changes)
            self.assertEqual(changes["_migration_source"]["scope_fields"]["previous_device_id"], "501")

    def test_repeat_batch_unchanged_device_cannot_bypass_new_full_purchase_capacity(self):
        self.assertEqual(self.apply(self.preview().json()).status_code, 200)
        self.payload["batch_id"] = str(uuid4())
        purchase = copy.deepcopy(self.payload["tables"]["purchases"][0])
        purchase.update(id=66, purchase_number="OPERATING-FULL")
        self.payload["tables"]["purchases"].append(purchase)
        allocation = copy.deepcopy(self.payload["tables"]["purchase_allocations"][0])
        allocation.update(id=67, purchase_id=66)
        self.payload["tables"]["purchase_allocations"].append(allocation)
        with self.engine.begin() as db:
            self.insert(db, "purchases", 900, purchase_number="OPERATING-FULL", item_type="device", item_name="Fixture PC", quantity=1, status="registered", details={})
            self.insert(db, "purchase_allocations", 901, purchase_id=900, resource_type="device", resource_id=501, quantity=1)
        before = self.snapshot()
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("purchase_capacity_conflict", {item["code"] for item in response.json()["issues"]})
        result = self.apply(response.json())
        self.assertEqual(result.status_code, 200, result.text)
        self.assert_preserved(before)
        with self.engine.connect() as db:
            self.assertEqual(db.execute(text("SELECT SUM(quantity) FROM purchase_allocations WHERE purchase_id=900")).scalar_one(), 1)

    def test_repeat_batch_unchanged_device_cannot_bypass_existing_license_seat_review(self):
        self.assertEqual(self.apply(self.preview().json()).status_code, 200)
        self.payload["batch_id"] = str(uuid4())
        asset = copy.deepcopy(self.payload["tables"]["assets"][0]); asset.update(id=44, asset_tag="OPERATING-LICENSE")
        license = copy.deepcopy(self.payload["tables"]["software_licenses"][0]); license.update(id=55, asset_id=44, license_key="EXISTING-FIXTURE-KEY")
        assignment = copy.deepcopy(self.payload["tables"]["license_assignments"][0]); assignment.update(id=56, license_id=55)
        self.payload["tables"]["assets"].append(asset)
        self.payload["tables"]["software_licenses"].append(license)
        self.payload["tables"]["license_assignments"].append(assignment)
        with self.engine.begin() as db:
            category_id = db.execute(text("SELECT id FROM asset_categories WHERE slug='software'")).scalar_one()
            vendor_id = db.execute(text("SELECT id FROM vendors WHERE name='Fixture vendor'")).scalar_one()
            self.insert(db, "assets", 900, asset_tag="OPERATING-LICENSE", name="Fixture software asset", category_id=category_id, status="in_stock", vendor_id=vendor_id)
            self.insert(db, "software_licenses", 901, asset_id=900, license_key="EXISTING-FIXTURE-KEY", license_type="per_seat", seats_total=10, seats_used=1, vendor_id=vendor_id)
            self.insert(db, "license_assignments", 902, license_id=901, device_id=501)
        before = self.snapshot()
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("existing_license_assignment_review", {item["code"] for item in response.json()["issues"]})
        result = self.apply(response.json())
        self.assertEqual(result.status_code, 200, result.text)
        self.assert_preserved(before)
        with self.engine.connect() as db:
            self.assertEqual(db.execute(text("SELECT COUNT(*) FROM license_assignments WHERE license_id=901")).scalar_one(), 1)


    def test_linked_imported_device_cannot_be_deleted_until_license_and_purchase_links_are_cleared(self):
        result = self.apply(self.preview().json())
        self.assertEqual(result.status_code, 200, result.text)
        with self.engine.connect() as db:
            device_id = db.execute(text("SELECT id FROM devices WHERE serial_number=' DEV-001 '")).scalar_one()
        before = self.snapshot()
        self.assertEqual(self.client.delete(f"/api/v1/devices/{device_id}").status_code, 409)
        self.assertEqual(self.snapshot(), before)
        with self.engine.begin() as db:
            db.execute(text("DELETE FROM license_assignments WHERE device_id=:id"), {"id":device_id})
        before = self.snapshot()
        self.assertEqual(self.client.delete(f"/api/v1/devices/{device_id}").status_code, 409)
        self.assertEqual(self.snapshot(), before)
        with self.engine.begin() as db:
            db.execute(text("DELETE FROM purchase_allocations WHERE resource_type='device' AND resource_id=:id"), {"id":device_id})
        self.assertEqual(self.client.delete(f"/api/v1/devices/{device_id}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
