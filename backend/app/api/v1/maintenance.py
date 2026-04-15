from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.maintenance import MaintenanceRecord
from app.schemas.maintenance import MaintenanceCreate, MaintenanceUpdate, MaintenanceResponse
from app.services.audit_service import log_action

router = APIRouter()


def _to_response(m: MaintenanceRecord) -> MaintenanceResponse:
    return MaintenanceResponse(
        id=m.id, asset_id=m.asset_id, maintenance_type=m.maintenance_type,
        description=m.description, cost=m.cost, scheduled_date=m.scheduled_date,
        completed_date=m.completed_date, vendor_id=m.vendor_id, technician=m.technician,
        status=m.status, notes=m.notes,
        asset_name=m.asset.name if m.asset else None,
        asset_tag=m.asset.asset_tag if m.asset else None,
        vendor_name=m.vendor.name if m.vendor else None,
        created_at=m.created_at, updated_at=m.updated_at,
    )


@router.get("/maintenance", response_model=dict)
def list_maintenance(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    asset_id: int | None = None, status: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(MaintenanceRecord)
    if asset_id:
        query = query.filter(MaintenanceRecord.asset_id == asset_id)
    if status:
        query = query.filter(MaintenanceRecord.status == status)
    total = query.count()
    items = query.order_by(MaintenanceRecord.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"items": [_to_response(i) for i in items], "total": total, "page": page, "size": size, "pages": (total + size - 1) // size}


@router.post("/maintenance", response_model=MaintenanceResponse, status_code=201)
def create_maintenance(data: MaintenanceCreate, db: Session = Depends(get_db)):
    m = MaintenanceRecord(**data.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    log_action(db, "maintenance", m.id, "create")
    return _to_response(m)


@router.put("/maintenance/{m_id}", response_model=MaintenanceResponse)
def update_maintenance(m_id: int, data: MaintenanceUpdate, db: Session = Depends(get_db)):
    m = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == m_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Maintenance record not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    log_action(db, "maintenance", m.id, "update")
    return _to_response(m)


@router.delete("/maintenance/{m_id}")
def delete_maintenance(m_id: int, db: Session = Depends(get_db)):
    m = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == m_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Maintenance record not found")
    log_action(db, "maintenance", m.id, "delete")
    db.delete(m)
    db.commit()
    return {"message": "Maintenance record deleted"}
