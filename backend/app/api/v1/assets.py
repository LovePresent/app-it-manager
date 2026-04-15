from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.api.deps import get_current_user
from app.models.asset import Asset, AssetAssignment, AssetStatus
from app.models.user import User
from app.schemas.asset import (
    AssetCreate, AssetUpdate, AssetResponse,
    AssetAssignRequest, AssetReturnRequest, AssetAssignmentResponse,
)
from app.services.asset_service import generate_asset_tag
from app.services.audit_service import log_action, compute_changes
from app.services.qr_service import generate_qr_code

router = APIRouter()


def _to_response(asset: Asset) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        asset_tag=asset.asset_tag,
        name=asset.name,
        category_id=asset.category_id,
        status=asset.status,
        serial_number=asset.serial_number,
        model=asset.model,
        manufacturer=asset.manufacturer,
        purchase_date=asset.purchase_date,
        purchase_price=asset.purchase_price,
        warranty_expiry=asset.warranty_expiry,
        vendor_id=asset.vendor_id,
        location_id=asset.location_id,
        department_id=asset.department_id,
        assigned_to=asset.assigned_to,
        notes=asset.notes,
        custom_fields=asset.custom_fields,
        qr_code_path=asset.qr_code_path,
        image_path=asset.image_path,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
        category_name=asset.category.name if asset.category else None,
        location_name=asset.location.name if asset.location else None,
        department_name=asset.department.name if asset.department else None,
        assigned_user_name=asset.assigned_user.name if asset.assigned_user else None,
        vendor_name=asset.vendor.name if asset.vendor else None,
    )


@router.get("/assets", response_model=dict)
def list_assets(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    category_id: int | None = None,
    status: str | None = None,
    search: str | None = None,
    department_id: int | None = None,
    location_id: int | None = None,
    assigned_to: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Asset)
    if category_id:
        query = query.filter(Asset.category_id == category_id)
    if status:
        query = query.filter(Asset.status == status)
    if department_id:
        query = query.filter(Asset.department_id == department_id)
    if location_id:
        query = query.filter(Asset.location_id == location_id)
    if assigned_to:
        query = query.filter(Asset.assigned_to == assigned_to)
    if search:
        query = query.filter(
            or_(
                Asset.name.ilike(f"%{search}%"),
                Asset.asset_tag.ilike(f"%{search}%"),
                Asset.serial_number.ilike(f"%{search}%"),
                Asset.model.ilike(f"%{search}%"),
            )
        )

    total = query.count()
    assets = query.order_by(Asset.id.desc()).offset((page - 1) * size).limit(size).all()

    return {
        "items": [_to_response(a) for a in assets],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/assets/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _to_response(asset)


@router.post("/assets", response_model=AssetResponse, status_code=201)
def create_asset(data: AssetCreate, db: Session = Depends(get_db)):
    asset = Asset(
        asset_tag=generate_asset_tag(db),
        **data.model_dump(),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    qr_path = generate_qr_code(asset.asset_tag, asset.id)
    asset.qr_code_path = qr_path
    db.commit()
    db.refresh(asset)

    log_action(db, "asset", asset.id, "create", changes=data.model_dump())
    return _to_response(asset)


@router.put("/assets/{asset_id}", response_model=AssetResponse)
def update_asset(asset_id: int, data: AssetUpdate, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    old_data = {c.name: getattr(asset, c.name) for c in Asset.__table__.columns}
    update_data = data.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(asset, key, val)
    db.commit()
    db.refresh(asset)

    changes = compute_changes(old_data, update_data)
    if changes:
        log_action(db, "asset", asset.id, "update", changes=changes)
    return _to_response(asset)


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    log_action(db, "asset", asset.id, "delete", changes={"name": asset.name, "asset_tag": asset.asset_tag})
    db.delete(asset)
    db.commit()
    return {"message": "Asset deleted"}


# --- Assignment ---
@router.post("/assets/{asset_id}/assign", response_model=AssetResponse)
def assign_asset(asset_id: int, data: AssetAssignRequest, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    asset.assigned_to = data.user_id
    asset.status = AssetStatus.ASSIGNED.value

    assignment = AssetAssignment(asset_id=asset.id, user_id=data.user_id, notes=data.notes)
    db.add(assignment)
    db.commit()
    db.refresh(asset)

    log_action(db, "asset", asset.id, "assign", changes={"assigned_to": user.name})
    return _to_response(asset)


@router.post("/assets/{asset_id}/return", response_model=AssetResponse)
def return_asset(asset_id: int, data: AssetReturnRequest, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Close active assignment
    active = (
        db.query(AssetAssignment)
        .filter(AssetAssignment.asset_id == asset_id, AssetAssignment.returned_at.is_(None))
        .first()
    )
    if active:
        from datetime import datetime
        active.returned_at = datetime.now()
        active.notes = data.notes or active.notes

    old_user = asset.assigned_to
    asset.assigned_to = None
    asset.status = AssetStatus.IN_STOCK.value
    db.commit()
    db.refresh(asset)

    log_action(db, "asset", asset.id, "return", changes={"previous_user_id": old_user})
    return _to_response(asset)


@router.get("/assets/{asset_id}/assignments", response_model=list[AssetAssignmentResponse])
def get_asset_assignments(asset_id: int, db: Session = Depends(get_db)):
    assignments = (
        db.query(AssetAssignment)
        .filter(AssetAssignment.asset_id == asset_id)
        .order_by(AssetAssignment.assigned_at.desc())
        .all()
    )
    results = []
    for a in assignments:
        results.append(AssetAssignmentResponse(
            id=a.id,
            asset_id=a.asset_id,
            user_id=a.user_id,
            assigned_at=a.assigned_at,
            returned_at=a.returned_at,
            notes=a.notes,
            user_name=a.user.name if a.user else None,
            asset_name=a.asset.name if a.asset else None,
            asset_tag=a.asset.asset_tag if a.asset else None,
        ))
    return results
