import copy
import hashlib
import json
import secrets
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models.audit_log import AuditLog
from app.models.auto_enrollment_ticket import AutoEnrollmentTicket
from app.models.user import User
from scripts import issue_agent_ticket as issuer


class AgentTicketCliTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="itam-ticket-cli-")
        self.path = Path(self.temporary.name) / "fixture.db"
        self.engine = create_engine("sqlite:///" + str(self.path))
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.key = b"isolated-ticket-test-key-32-bytes!"
        self.stack = ExitStack()
        for name, value in {"DATABASE_URL": "sqlite:///" + str(self.path), "AGENT_PUBLIC_URL": "https://dev.cqv.kr",
                            "AGENT_API_PREFIX": "/manage/it/api/v1/agent", "AGENT_DEPLOYMENT_MODE": "production",
                            "AGENT_ENROLLMENT_SECRET": self.key.decode()}.items():
            self.stack.enter_context(patch.object(issuer.settings, name, value))
        self.stack.enter_context(patch.object(issuer, "verify_package_ready"))
        self.now = datetime.now(timezone.utc)
        self.request = {"ticketId": str(uuid4()), "tokenHash": hashlib.sha256(b"fixture-random-bootstrap-not-an-actual-secret").hexdigest(),
                        "expiresAt": (self.now + timedelta(hours=23)).isoformat().replace("+00:00", "Z"),
                        "expectedServerId": issuer.server_id(self.key), "issuerEmail": "existing-admin@example.test"}
        with self.sessions.begin() as db:
            db.add(User(email=self.request["issuerEmail"], name="Existing administrator", role="admin", is_active=True))

    def tearDown(self):
        self.stack.close()
        self.engine.dispose()
        self.temporary.cleanup()

    def data(self, body=None):
        return issuer.parse_request(json.dumps(body or self.request).encode())

    def test_hash_only_request_issues_once_and_replay_never_resets_expiry_or_audit(self):
        identifier = issuer.issue(self.data(), self.sessions)
        self.assertEqual(identifier, self.request["ticketId"])
        self.assertEqual(issuer.issue(self.data(), self.sessions), identifier)
        with self.sessions() as db:
            tickets = db.scalars(select(AutoEnrollmentTicket)).all()
            self.assertEqual(len(tickets), 1)
            self.assertTrue(tickets[0].unlimited)
            self.assertEqual(tickets[0].token_hash, self.request["tokenHash"])
            self.assertEqual(tickets[0].expires_at, self.data()["expires"])
            logs = db.scalars(select(AuditLog)).all()
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].user_name, "Existing administrator")
            self.assertNotIn(self.request["tokenHash"], json.dumps(logs[0].changes))
            self.assertNotIn(self.request["expectedServerId"], json.dumps(logs[0].changes))
        for field, value in [("tokenHash", "a" * 64), ("expiresAt", (self.now + timedelta(hours=22)).isoformat())]:
            with self.subTest(field=field):
                body = {**self.request, field: value}
                with self.assertRaisesRegex(ValueError, "different"):
                    issuer.issue(self.data(body), self.sessions)

    def test_only_existing_active_admin_and_matching_server_can_issue(self):
        for body in [{**self.request, "issuerEmail": "missing@example.test"}, {**self.request, "expectedServerId": "0" * 64}]:
            with self.assertRaises(ValueError):
                issuer.issue(self.data(body), self.sessions)
        for role, active in [("manager", True), ("user", True), ("admin", False)]:
            with self.sessions.begin() as db:
                user = db.scalar(select(User))
                user.role, user.is_active = role, active
            with self.assertRaisesRegex(ValueError, "administrator"):
                issuer.issue(self.data(), self.sessions)
        with self.sessions() as db:
            self.assertEqual(len(db.scalars(select(User)).all()), 1)
            self.assertEqual(db.scalars(select(AutoEnrollmentTicket)).all(), [])
            self.assertEqual(db.scalars(select(AuditLog)).all(), [])
        with patch.object(issuer.settings, "AGENT_DEPLOYMENT_MODE", "development"):
            with self.assertRaisesRegex(ValueError, "production"):
                issuer.issue(self.data(), self.sessions)

    def test_hash_only_deployment_ticket_is_consumable_by_the_real_auto_enrollment_api(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_db
        raw_token = secrets.token_urlsafe(32)
        self.request["tokenHash"] = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        issuer.issue(self.data(), self.sessions)
        old = app.dependency_overrides.copy()
        def fixture_db():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = fixture_db
        body = {"ticketId": self.request["ticketId"], "registrationToken": raw_token,
                "clientNonce": secrets.token_urlsafe(32), "hardwareUuid": str(uuid4()),
                "serialNumber": "CLI-TEST-PC", "hostname": "Synthetic CLI Test PC",
                "deviceType": "desktop", "os": "Windows test fixture"}
        try:
            with TestClient(app) as client:
                first = client.post("/api/v1/agent/auto-enroll", json=body)
                self.assertEqual(first.status_code, 200, first.text)
                retry = client.post("/api/v1/agent/auto-enroll", json=body)
                self.assertEqual(retry.status_code, 200, retry.text)
                self.assertEqual(retry.json(), first.json())
                self.assertTrue(first.json()["created"])
            self.assertEqual(issuer.issue(self.data(), self.sessions), self.request["ticketId"])
        finally:
            app.dependency_overrides = old

    def test_strict_json_rejects_extra_duplicate_raw_token_bad_uuid_expiry_and_oversize(self):
        invalid = [b"[]", b"x" * 8193, b'{"ticketId":"x","ticketId":"y"}']
        for updates in [{"registrationToken": "raw-not-allowed"}, {"ticketId": "0" * 36}, {"tokenHash": "A" * 64},
                        {"expiresAt": (self.now - timedelta(seconds=1)).isoformat()},
                        {"expiresAt": (self.now + timedelta(hours=25)).isoformat()},
                        {"expiresAt": "2030-01-01T00:00:00"}, {"issuerEmail": "not-an-email"}]:
            invalid.append(json.dumps({**self.request, **updates}).encode())
        for raw in invalid:
            with self.subTest(length=len(raw)), self.assertRaises((ValueError, TypeError)):
                issuer.parse_request(raw, self.now)


if __name__ == "__main__":
    unittest.main()
