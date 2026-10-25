"""Issue an approved automatic-install ticket from a hash-only deploy request.

Input is a bounded UTF-8 JSON file or stdin ('-'). Raw registration tokens are
never accepted, printed, persisted, or needed by this administrative command.
"""
import hmac
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.auto_enrollment_ticket import AutoEnrollmentTicket
from app.services.agent_connection_service import configured_connection, server_id
from app.services.auto_enrollment_service import enrollment_key
from app.services.agent_installer_service import verify_package_ready

FIELDS = {"ticketId", "tokenHash", "expiresAt", "expectedServerId", "issuerEmail"}
HEX = re.compile(r"^[0-9a-f]{64}$")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate request field.")
        result[key] = value
    return result


def parse_request(raw, now=None):
    if not isinstance(raw, bytes) or len(raw) > 8192:
        raise ValueError("Request must be at most 8192 bytes.")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    if not isinstance(data, dict) or set(data) != FIELDS or any(not isinstance(value, str) for value in data.values()):
        raise ValueError("Exactly the five documented string fields are required.")
    if str(UUID(data["ticketId"])) != data["ticketId"] or UUID(data["ticketId"]).int == 0:
        raise ValueError("Invalid ticket identifier.")
    if not HEX.fullmatch(data["tokenHash"]) or not HEX.fullmatch(data["expectedServerId"]):
        raise ValueError("Invalid digest field.")
    if not re.fullmatch(r"[^\s@]{1,128}@[^\s@]{1,125}", data["issuerEmail"]) or len(data["issuerEmail"]) > 254:
        raise ValueError("Invalid administrator email.")
    expires = datetime.fromisoformat(data["expiresAt"].replace("Z", "+00:00"))
    if expires.tzinfo is None or expires.utcoffset() != timedelta(0):
        raise ValueError("Expiry must be an explicit UTC timestamp.")
    now = now or datetime.now(timezone.utc)
    if not now < expires <= now + timedelta(hours=24):
        raise ValueError("Expiry must be in the next 24 hours.")
    data["expires"] = expires.replace(tzinfo=None)
    return data


def matching(ticket, data, issuer):
    return (hmac.compare_digest(ticket.token_hash, data["tokenHash"])
            and ticket.expires_at == data["expires"] and ticket.issued_by_id == issuer.id
            and ticket.unlimited is True and ticket.max_uses == 1)


def issue(data, sessions=SessionLocal):
    connection = configured_connection()
    if connection["deploymentMode"] != "production":
        raise ValueError("Deployment ticket issuance requires production configuration.")
    if not hmac.compare_digest(server_id(enrollment_key()), data["expectedServerId"]):
        raise ValueError("Deployment identity does not match the approved request.")
    verify_package_ready()
    database = make_url(settings.DATABASE_URL)
    if database.get_backend_name() == "sqlite" and (not database.database or not Path(database.database).is_file()):
        raise ValueError("Existing application database is required.")
    with sessions() as db:
        try:
            with db.begin():
                users = db.scalars(select(User).where(func.lower(User.email) == data["issuerEmail"].lower())).all()
                if len(users) != 1:
                    raise ValueError("An existing active administrator is required.")
                issuer = users[0]
                # Lock the existing principal and serialize concurrent idempotent requests.
                db.execute(update(User).where(User.id == issuer.id).values(updated_at=User.updated_at)
                           .execution_options(synchronize_session=False))
                db.refresh(issuer)
                if issuer.role != "admin" or issuer.is_active is not True:
                    raise ValueError("An existing active administrator is required.")
                ticket = db.get(AutoEnrollmentTicket, data["ticketId"])
                if ticket is not None:
                    if not matching(ticket, data, issuer):
                        raise ValueError("Ticket identifier already exists with different approved parameters.")
                    return ticket.id
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                if not now < data["expires"] <= now + timedelta(hours=24):
                    raise ValueError("Approved request expired before issuance.")
                ticket = AutoEnrollmentTicket(id=data["ticketId"], token_hash=data["tokenHash"],
                    expires_at=data["expires"], unlimited=True, max_uses=1, used_count=0,
                    issued_by_id=issuer.id, created_at=now, updated_at=now)
                db.add(ticket)
                db.add(AuditLog(entity_type="agent_auto_enrollment", entity_id=0, action="deployment_installer_issue",
                    changes={"ticket_id": ticket.id, "unlimited": True,
                             "expires_at": data["expiresAt"], "source": "authorized_deployment"},
                    user_id=issuer.id, user_name=issuer.name, ip_address=None))
                db.flush()
                return ticket.id
        except IntegrityError as exc:
            raise ValueError("Ticket request conflicted; retry the same approved request.") from exc


def main():
    if len(sys.argv) != 2:
        raise ValueError("Usage: issue_agent_ticket.py <request.json|->")
    if sys.argv[1] == "-":
        raw = sys.stdin.buffer.read(8193)
    else:
        with open(sys.argv[1], "rb") as stream:
            raw = stream.read(8193)
    identifier = issue(parse_request(raw))
    print(identifier)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Request contents, tokens, SQL, and row values never enter deployment logs.
        print("Agent ticket issuance rejected; check the approved request and existing administrator configuration.", file=sys.stderr)
        sys.exit(1)
