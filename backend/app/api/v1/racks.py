from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc

from app.database import get_db
from app.models.rack import Rack, RackUnit
from app.schemas.rack import (
    RackCreate, RackUpdate, RackResponse,
    RackUnitCreate, RackUnitUpdate, RackUnitResponse,
)

router = APIRouter()


def _rack_response(r: Rack, db: Session) -> RackResponse:
    used = db.query(sqlfunc.count(RackUnit.id)).filter(RackUnit.rack_id == r.id).scalar() or 0
    return RackResponse(
        id=r.id, name=r.name, location_id=r.location_id, total_units=r.total_units,
        power_capacity=r.power_capacity, description=r.description, used_units=used,
        location_name=r.location.name if r.location else None,
        created_at=r.created_at, updated_at=r.updated_at,
    )


@router.get("/racks", response_model=list[RackResponse])
def list_racks(db: Session = Depends(get_db)):
    racks = db.query(Rack).order_by(Rack.name).all()
    return [_rack_response(r, db) for r in racks]


@router.post("/racks", response_model=RackResponse, status_code=201)
def create_rack(data: RackCreate, db: Session = Depends(get_db)):
    r = Rack(**data.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return _rack_response(r, db)


@router.put("/racks/{rack_id}", response_model=RackResponse)
def update_rack(rack_id: int, data: RackUpdate, db: Session = Depends(get_db)):
    r = db.query(Rack).filter(Rack.id == rack_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Rack not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return _rack_response(r, db)


@router.delete("/racks/{rack_id}")
def delete_rack(rack_id: int, db: Session = Depends(get_db)):
    r = db.query(Rack).filter(Rack.id == rack_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Rack not found")
    db.delete(r)
    db.commit()
    return {"message": "Rack deleted"}


# --- Rack Units ---
@router.get("/racks/{rack_id}/units", response_model=list[RackUnitResponse])
def list_rack_units(rack_id: int, db: Session = Depends(get_db)):
    units = db.query(RackUnit).filter(RackUnit.rack_id == rack_id).order_by(RackUnit.start_unit).all()
    return [RackUnitResponse(
        id=u.id, rack_id=u.rack_id, start_unit=u.start_unit, end_unit=u.end_unit,
        asset_id=u.asset_id, position=u.position, notes=u.notes,
        asset_name=u.asset.name if u.asset else None,
        asset_tag=u.asset.asset_tag if u.asset else None,
    ) for u in units]


@router.post("/racks/{rack_id}/units", response_model=RackUnitResponse, status_code=201)
def create_rack_unit(rack_id: int, data: RackUnitCreate, db: Session = Depends(get_db)):
    u = RackUnit(**data.model_dump())
    u.rack_id = rack_id
    db.add(u)
    db.commit()
    db.refresh(u)
    return RackUnitResponse(
        id=u.id, rack_id=u.rack_id, start_unit=u.start_unit, end_unit=u.end_unit,
        asset_id=u.asset_id, position=u.position, notes=u.notes,
        asset_name=u.asset.name if u.asset else None,
        asset_tag=u.asset.asset_tag if u.asset else None,
    )


@router.delete("/rack-units/{unit_id}")
def delete_rack_unit(unit_id: int, db: Session = Depends(get_db)):
    u = db.query(RackUnit).filter(RackUnit.id == unit_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Rack unit not found")
    db.delete(u)
    db.commit()
    return {"message": "Rack unit deleted"}
