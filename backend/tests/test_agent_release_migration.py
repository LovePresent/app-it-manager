"""Nonempty legacy migration rehearsal; only per-test temporary databases."""
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from scripts import migrate_agent_release as guard


class AgentReleaseMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="itam-release-migration-")
        self.root = Path(self.temporary.name)
        self.path = self.root / "existing.db"
        self.backups = self.root / "backups"
        self.url = patch.object(guard.settings, "DATABASE_URL", "sqlite:///" + str(self.path))
        self.backup_setting = patch.object(guard.settings, "AGENT_DATABASE_BACKUP_DIR", str(self.backups))
        self.url.start()
        self.backup_setting.start()

    def tearDown(self):
        self.backup_setting.stop()
        self.url.stop()
        self.temporary.cleanup()

    def fixture(self):
        guard.create_legacy(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO users(id,email,name,role,is_active) VALUES (5,'existing@example.test','기존 관리자','admin',1)")
            db.execute("INSERT INTO asset_categories(id,name,slug) VALUES (2,'기존 장비','existing')")
            db.execute("INSERT INTO assets(id,asset_tag,name,category_id,status,notes,custom_fields) VALUES (10,'OLD-001','기존 자산',2,'assigned','보존할 값',?)", ('{"unicode":"원래 값"}',))
            db.execute("INSERT INTO devices(id,serial_number,device_type,status,ip_address,notes) VALUES (33,'EXISTING-PC','desktop','assigned','192.0.2.15','원래 메모')")
            db.execute("INSERT INTO software_licenses(id,asset_id,license_key,seats_total,seats_used) VALUES (7,10,'fixture-license-only',20,3)")
            db.execute("INSERT INTO maintenance_records(id,asset_id,maintenance_type,cost,description) VALUES (4,10,'corrective',12.5,'기존 수리')")
            db.execute("INSERT INTO audit_logs(id,entity_type,entity_id,action,changes,user_id) VALUES (8,'device',33,'update','{}',5)")
            db.execute("INSERT INTO ip_change_history(id,source_type,source_id,device_id,new_ip_address,change_reason) VALUES (11,'device',33,33,'192.0.2.15','기존 기록')")
            db.commit()
            return guard.snapshot(db)

    def test_unstamped_nonempty_legacy_is_backed_up_adopted_and_every_old_value_preserved(self):
        before = self.fixture()
        result = guard.migrate()
        self.assertEqual(result["revision"], guard.EXPECTED_HEAD)
        with closing(guard.read_only(self.path)) as db:
            self.assertEqual(guard.snapshot(db, before), before)
            self.assertEqual(guard.current_revision(db), guard.EXPECTED_HEAD)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(db.execute("SELECT service_company FROM software_licenses WHERE id=7").fetchone(), (None,))
            self.assertEqual(db.execute("SELECT device_id,unregistered_target FROM maintenance_records WHERE id=4").fetchone(), (None, 0))
            self.assertIn("device_agents", guard.table_names(db))
        backups = list(self.backups.glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        with closing(guard.read_only(backups[0])) as db:
            self.assertEqual(guard.snapshot(db), before)
            self.assertIsNone(guard.current_revision(db))
        manifest = json.loads(backups[0].with_suffix(".json").read_text())
        self.assertEqual(manifest["tables"], before)
        self.assertNotIn("기존 관리자", backups[0].with_suffix(".json").read_text())
        # Repeated startup validates the full known schema, backs up again, and changes no values.
        second = guard.migrate()
        self.assertTrue(second["existing_values_preserved"])
        self.assertEqual(len(list(self.backups.glob("*.db"))), 2)

    def test_stamped_baseline_migrates_without_rewriting_history(self):
        before = self.fixture()
        guard.alembic("stamp", guard.BASELINE, self.path)
        self.assertTrue(guard.migrate()["existing_values_preserved"])
        with closing(guard.read_only(self.path)) as db:
            self.assertEqual(guard.snapshot(db, before), before)

    def test_deployed_b856_without_inventory_adds_tables_without_stamping_away_ip_history_migration(self):
        guard.create_legacy(self.path, "b856260")
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO users(id,email,name,role,is_active) VALUES (5,'existing@example.test','기존 사용자','admin',1)")
            db.execute("INSERT INTO asset_categories(id,name,slug) VALUES (2,'기존 장비','existing')")
            db.execute("INSERT INTO assets(id,asset_tag,name,category_id,status) VALUES (10,'OLD-001','보존 자산',2,'assigned')")
            db.execute("INSERT INTO software_licenses(id,asset_id,license_key,seats_total,seats_used) VALUES (7,10,'fixture-only',20,3)")
            db.execute("INSERT INTO maintenance_records(id,asset_id,maintenance_type,cost) VALUES (4,10,'corrective',12.5)")
            db.commit()
            before = guard.snapshot(db)
            self.assertEqual(len(before), 19)
            self.assertNotIn("devices", before)
            self.assertNotIn("ip_change_history", before)
        self.assertTrue(guard.migrate()["existing_values_preserved"])
        with closing(guard.read_only(self.path)) as db:
            self.assertEqual(guard.snapshot(db, before), before)
            self.assertEqual(guard.current_revision(db), guard.EXPECTED_HEAD)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM devices").fetchone(), (0,))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ip_change_history").fetchone(), (0,))
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_missing_empty_unknown_schema_and_unknown_revision_never_initialize_or_stamp(self):
        with self.assertRaisesRegex(RuntimeError, "not found"):
            guard.migrate()
        self.assertFalse(self.path.exists())
        self.path.touch()
        with self.assertRaisesRegex(RuntimeError, "not found"):
            guard.migrate()
        self.assertEqual(self.path.stat().st_size, 0)
        before = self.fixture()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TABLE unrecognized_data(id INTEGER)")
            db.commit()
        with self.assertRaisesRegex(RuntimeError, "schema"):
            guard.migrate()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIsNone(guard.current_revision(db))
            db.execute("DROP TABLE unrecognized_data")
            db.execute("CREATE TABLE alembic_version(version_num VARCHAR(64) NOT NULL)")
            db.execute("INSERT INTO alembic_version VALUES ('unknown-production-revision')")
            db.commit()
        with self.assertRaisesRegex(RuntimeError, "Unknown migration"):
            guard.migrate()
        with closing(guard.read_only(self.path)) as db:
            self.assertEqual(guard.snapshot(db, before), before)
            self.assertEqual(guard.current_revision(db), "unknown-production-revision")

    def test_missing_legacy_ip_history_or_changed_constraint_is_not_silently_adopted(self):
        self.fixture()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("DROP TABLE ip_change_history")
            db.commit()
        with self.assertRaisesRegex(RuntimeError, "schema"):
            guard.migrate()
        with closing(guard.read_only(self.path)) as db:
            self.assertIsNone(guard.current_revision(db))

    def test_preservation_failure_blocks_startup_and_keeps_verified_prechange_backup(self):
        before = self.fixture()
        original = guard.alembic
        def altered(command, revision, path):
            original(command, revision, path)
            if command == "upgrade" and revision == "head" and path == self.path:
                with closing(sqlite3.connect(path)) as db:
                    db.execute("UPDATE devices SET notes='unexpected change' WHERE id=33")
                    db.commit()
        with patch.object(guard, "alembic", side_effect=altered):
            with self.assertRaisesRegex(RuntimeError, "preservation"):
                guard.migrate()
        backups = list(self.backups.glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertFalse(list(self.backups.glob("*.verified.json")))
        with closing(guard.read_only(backups[0])) as db:
            self.assertEqual(guard.snapshot(db), before)


if __name__ == "__main__":
    unittest.main()
