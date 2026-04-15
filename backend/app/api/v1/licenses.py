from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.license import SoftwareLicense
from app.models.asset import Asset
from app.schemas.license import LicenseCreate, LicenseUpdate, LicenseResponse
from app.services.audit_service import log_action

router = APIRouter()


def _to_response(lic: SoftwareLicense) -> LicenseResponse:
    return LicenseResponse(
        id=lic.id,
        asset_id=lic.asset_id,
        license_key=lic.license_key,
        license_type=lic.license_type,
        seats_total=lic.seats_total,
        seats_used=lic.seats_used,
        expiry_date=lic.expiry_date,
        vendor_id=lic.vendor_id,
        notes=lic.notes,
        asset_name=lic.asset.name if lic.asset else None,
        asset_tag=lic.asset.asset_tag if lic.asset else None,
        vendor_name=lic.vendor.name if lic.vendor else None,
        created_at=lic.created_at,
        updated_at=lic.updated_at,
    )


@router.get("/licenses", response_model=dict)
def list_licenses(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(SoftwareLicense)
    if search:
        query = query.join(Asset).filter(Asset.name.ilike(f"%{search}%"))
    total = query.count()
    items = query.order_by(SoftwareLicense.id.desc()).offset((page - 1) * size).limit(size).all()
    return {
        "items": [_to_response(i) for i in items],
        "total": total, "page": page, "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/licenses/{lic_id}", response_model=LicenseResponse)
def get_license(lic_id: int, db: Session = Depends(get_db)):
    lic = db.query(SoftwareLicense).filter(SoftwareLicense.id == lic_id).first()
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    return _to_response(lic)


@router.post("/licenses", response_model=LicenseResponse, status_code=201)
def create_license(data: LicenseCreate, db: Session = Depends(get_db)):
    lic = SoftwareLicense(**data.model_dump())
    db.add(lic)
    db.commit()
    db.refresh(lic)
    log_action(db, "license", lic.id, "create")
    return _to_response(lic)


@router.put("/licenses/{lic_id}", response_model=LicenseResponse)
def update_license(lic_id: int, data: LicenseUpdate, db: Session = Depends(get_db)):
    lic = db.query(SoftwareLicense).filter(SoftwareLicense.id == lic_id).first()
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(lic, k, v)
    db.commit()
    db.refresh(lic)
    log_action(db, "license", lic.id, "update")
    return _to_response(lic)


@router.delete("/licenses/{lic_id}")
def delete_license(lic_id: int, db: Session = Depends(get_db)):
    lic = db.query(SoftwareLicense).filter(SoftwareLicense.id == lic_id).first()
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    log_action(db, "license", lic.id, "delete")
    db.delete(lic)
    db.commit()
    return {"message": "License deleted"}
