from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ip_address import IPAddress
from app.schemas.ip_address import IPAddressCreate, IPAddressUpdate, IPAddressResponse
from app.services.audit_service import log_action

router = APIRouter()


def _to_response(ip: IPAddress) -> IPAddressResponse:
    return IPAddressResponse(
        id=ip.id, address=ip.address, subnet=ip.subnet, gateway=ip.gateway,
        dns_primary=ip.dns_primary, dns_secondary=ip.dns_secondary, vlan=ip.vlan,
        status=ip.status, asset_id=ip.asset_id, description=ip.description, notes=ip.notes,
        asset_name=ip.asset.name if ip.asset else None,
        asset_tag=ip.asset.asset_tag if ip.asset else None,
        created_at=ip.created_at, updated_at=ip.updated_at,
    )


@router.get("/ip-addresses", response_model=dict)
def list_ips(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    vlan: str | None = None, status: str | None = None, search: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(IPAddress)
    if vlan:
        query = query.filter(IPAddress.vlan == vlan)
    if status:
        query = query.filter(IPAddress.status == status)
    if search:
        query = query.filter(IPAddress.address.ilike(f"%{search}%"))
    total = query.count()
    items = query.order_by(IPAddress.address).offset((page - 1) * size).limit(size).all()
    return {"items": [_to_response(i) for i in items], "total": total, "page": page, "size": size, "pages": (total + size - 1) // size}


@router.get("/ip-addresses/{ip_id}", response_model=IPAddressResponse)
def get_ip(ip_id: int, db: Session = Depends(get_db)):
    ip = db.query(IPAddress).filter(IPAddress.id == ip_id).first()
    if not ip:
        raise HTTPException(status_code=404, detail="IP address not found")
    return _to_response(ip)


@router.post("/ip-addresses", response_model=IPAddressResponse, status_code=201)
def create_ip(data: IPAddressCreate, db: Session = Depends(get_db)):
    existing = db.query(IPAddress).filter(IPAddress.address == data.address).first()
    if existing:
        raise HTTPException(status_code=400, detail="IP address already exists")
    ip = IPAddress(**data.model_dump())
    db.add(ip)
    db.commit()
    db.refresh(ip)
    log_action(db, "ip_address", ip.id, "create")
    return _to_response(ip)


@router.put("/ip-addresses/{ip_id}", response_model=IPAddressResponse)
def update_ip(ip_id: int, data: IPAddressUpdate, db: Session = Depends(get_db)):
    ip = db.query(IPAddress).filter(IPAddress.id == ip_id).first()
    if not ip:
        raise HTTPException(status_code=404, detail="IP address not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(ip, k, v)
    db.commit()
    db.refresh(ip)
    log_action(db, "ip_address", ip.id, "update")
    return _to_response(ip)


@router.delete("/ip-addresses/{ip_id}")
def delete_ip(ip_id: int, db: Session = Depends(get_db)):
    ip = db.query(IPAddress).filter(IPAddress.id == ip_id).first()
    if not ip:
        raise HTTPException(status_code=404, detail="IP address not found")
    log_action(db, "ip_address", ip.id, "delete")
    db.delete(ip)
    db.commit()
    return {"message": "IP address deleted"}
