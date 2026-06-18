from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.asset import Asset
from app.models.common import Location, Department, Vendor
from app.models.device_inventory import Device
from app.models.network import NetworkPort
from app.models.rack import Rack
from app.schemas.location import (
    LocationCreate, LocationUpdate, LocationResponse,
    DepartmentCreate, DepartmentUpdate, DepartmentResponse,
    VendorCreate, VendorUpdate, VendorResponse,
)

# ----- Locations -----
router = APIRouter()


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_location_payload(data: LocationCreate | LocationUpdate, *, partial: bool = False) -> dict:
    payload = data.model_dump(exclude_unset=partial)
    for key in ("name", "type", "description"):
        if key in payload:
            payload[key] = _clean_text(payload[key])
    if "name" in payload and not payload["name"]:
        raise HTTPException(status_code=400, detail="Location name is required")
    return payload


def _location_name_exists(db: Session, name: str, *, exclude_id: int | None = None) -> bool:
    query = db.query(Location.id).filter(func.lower(Location.name) == name.lower())
    if exclude_id is not None:
        query = query.filter(Location.id != exclude_id)
    return query.first() is not None


def _sync_locations_from_devices(db: Session):
    existing = {name.strip().lower() for (name,) in db.query(Location.name).all() if name and name.strip()}
    location_names = {
        value.strip()
        for (value,) in db.query(Device.location).filter(Device.location.isnot(None)).distinct().all()
        if value and value.strip()
    }
    factory_names = {
        value.strip()
        for (value,) in db.query(Device.factory).filter(Device.factory.isnot(None)).distinct().all()
        if value and value.strip()
    }

    new_locations = [
        Location(name=name, type="device_location", description="디바이스 데이터에서 자동 추가")
        for name in sorted(location_names, key=lambda item: item.casefold())
        if name.lower() not in existing
    ]
    existing.update(name.lower() for name in location_names)
    new_factories = [
        Location(name=name, type="factory", description="디바이스 공장 데이터에서 자동 추가")
        for name in sorted(factory_names, key=lambda item: item.casefold())
        if name.lower() not in existing
    ]
    if not new_locations and not new_factories:
        return
    db.add_all([*new_locations, *new_factories])
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def _location_usage_counts(db: Session, loc: Location) -> dict[str, int]:
    normalized_name = loc.name.strip().lower()
    return {
        "하위 위치": db.query(Location).filter(Location.parent_id == loc.id).count(),
        "자산": db.query(Asset).filter(Asset.location_id == loc.id).count(),
        "랙": db.query(Rack).filter(Rack.location_id == loc.id).count(),
        "네트워크 포트": db.query(NetworkPort).filter(NetworkPort.location_id == loc.id).count(),
        "디바이스": db.query(Device)
        .filter(
            or_(
                func.lower(func.trim(Device.location)) == normalized_name,
                func.lower(func.trim(Device.factory)) == normalized_name,
            )
        )
        .count(),
    }


def _raise_if_location_in_use(db: Session, loc: Location) -> None:
    usages = {label: count for label, count in _location_usage_counts(db, loc).items() if count}
    if not usages:
        return
    detail = ", ".join(f"{label} {count}개" for label, count in usages.items())
    raise HTTPException(
        status_code=409,
        detail=f"이 위치는 사용 중이라 삭제할 수 없습니다. 먼저 연결된 항목을 수정하세요. ({detail})",
    )


@router.get("/locations", response_model=list[LocationResponse])
def list_locations(db: Session = Depends(get_db)):
    _sync_locations_from_devices(db)
    return db.query(Location).order_by(Location.name).all()

@router.post("/locations", response_model=LocationResponse, status_code=201)
def create_location(data: LocationCreate, db: Session = Depends(get_db)):
    payload = _clean_location_payload(data)
    if _location_name_exists(db, payload["name"]):
        raise HTTPException(status_code=409, detail="Location already exists")
    loc = Location(**payload)
    db.add(loc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Location already exists")
    db.refresh(loc)
    return loc

@router.put("/locations/{loc_id}", response_model=LocationResponse)
def update_location(loc_id: int, data: LocationUpdate, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == loc_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    payload = _clean_location_payload(data, partial=True)
    if "name" in payload and _location_name_exists(db, payload["name"], exclude_id=loc_id):
        raise HTTPException(status_code=409, detail="Location already exists")
    for k, v in payload.items():
        setattr(loc, k, v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Location already exists")
    db.refresh(loc)
    return loc

@router.delete("/locations/{loc_id}")
def delete_location(loc_id: int, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == loc_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="위치를 찾을 수 없습니다.")
    _raise_if_location_in_use(db, loc)
    db.delete(loc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="이 위치는 사용 중이라 삭제할 수 없습니다.")
    return {"message": "위치가 삭제되었습니다."}
