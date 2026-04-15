from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogResponse

router = APIRouter()


@router.get("/audit-logs", response_model=dict)
def list_audit_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    entity_type: str | None = None,
    entity_id: int | None = None,
    action: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if action:
        query = query.filter(AuditLog.action == action)
    total = query.count()
    items = query.order_by(AuditLog.timestamp.desc()).offset((page - 1) * size).limit(size).all()
    return {
        "items": [AuditLogResponse.model_validate(i) for i in items],
        "total": total, "page": page, "size": size,
        "pages": (total + size - 1) // size,
    }
