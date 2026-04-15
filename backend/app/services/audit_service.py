from sqlalchemy.orm import Session
from datetime import datetime

from app.models.audit_log import AuditLog


def log_action(
    db: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    changes: dict | None = None,
    user_id: int | None = None,
    user_name: str | None = None,
    ip_address: str | None = None,
):
    log = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        changes=changes,
        user_id=user_id,
        user_name=user_name,
        ip_address=ip_address,
    )
    db.add(log)
    db.commit()


def compute_changes(old_data: dict, new_data: dict) -> dict:
    changes = {}
    for key, new_val in new_data.items():
        if new_val is None:
            continue
        old_val = old_data.get(key)
        if old_val != new_val:
            changes[key] = {"old": old_val, "new": new_val}
    return changes
