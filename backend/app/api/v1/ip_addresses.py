from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.asset import Asset
from app.models.ip_address import IPAddress, IPChangeHistory
from app.schemas.ip_address import IPAddressCreate, IPAddressUpdate, IPAddressResponse, IPChangeHistoryResponse
from app.services.audit_service import compute_changes, log_action

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


def _history_response(item: IPChangeHistory) -> IPChangeHistoryResponse:
    return IPChangeHistoryResponse(
        id=item.id,
        source_type=item.source_type,
        source_id=item.source_id,
        device_id=item.device_id,
        ip_address_id=item.ip_address_id,
        old_serial_number=item.old_serial_number,
        new_serial_number=item.new_serial_number,
        user_name=item.user_name,
        employee_number=item.employee_number,
        asset_tag=item.asset_tag,
        asset_name=item.asset_name,
        old_ip_address=item.old_ip_address,
        new_ip_address=item.new_ip_address,
        old_mac_address=item.old_mac_address,
        new_mac_address=item.new_mac_address,
        old_status=item.old_status,
        new_status=item.new_status,
        change_reason=item.change_reason,
        notes=item.notes,
        created_at=item.created_at,
    )


def _asset_info(db: Session, asset_id: int | None) -> tuple[str | None, str | None]:
    if not asset_id:
        return None, None
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return None, None
    return asset.asset_tag, asset.name


def _record_ip_address_history(
    db: Session,
    ip: IPAddress,
    old_data: dict,
    reason: str,
    notes: str | None = None,
):
    watched_fields = ("address", "status", "asset_id")
    if all(old_data.get(field) == getattr(ip, field) for field in watched_fields):
        return

    asset_tag, asset_name = _asset_info(db, ip.asset_id)
    old_asset_tag, old_asset_name = _asset_info(db, old_data.get("asset_id"))
    db.add(
        IPChangeHistory(
            source_type="ip_address",
            source_id=ip.id,
            ip_address_id=ip.id,
            asset_tag=asset_tag or old_asset_tag,
            asset_name=asset_name or old_asset_name,
            old_ip_address=old_data.get("address"),
            new_ip_address=ip.address,
            old_status=old_data.get("status"),
            new_status=ip.status,
            change_reason=reason,
            notes=notes,
        )
    )


@router.get("/ip-change-history", response_model=dict)
def list_ip_change_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=1000),
    search: str | None = None,
    source_type: str | None = None,
    device_id: int | None = None,
    ip_address_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(IPChangeHistory)
    if source_type:
        query = query.filter(IPChangeHistory.source_type == source_type)
    if device_id:
        query = query.filter(IPChangeHistory.device_id == device_id)
    if ip_address_id:
        query = query.filter(IPChangeHistory.ip_address_id == ip_address_id)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                IPChangeHistory.old_ip_address.ilike(like),
                IPChangeHistory.new_ip_address.ilike(like),
                IPChangeHistory.old_mac_address.ilike(like),
                IPChangeHistory.new_mac_address.ilike(like),
                IPChangeHistory.old_serial_number.ilike(like),
                IPChangeHistory.new_serial_number.ilike(like),
                IPChangeHistory.user_name.ilike(like),
                IPChangeHistory.employee_number.ilike(like),
                IPChangeHistory.asset_tag.ilike(like),
                IPChangeHistory.asset_name.ilike(like),
                IPChangeHistory.change_reason.ilike(like),
                IPChangeHistory.notes.ilike(like),
            )
        )

    total = query.count()
    items = query.order_by(IPChangeHistory.created_at.desc(), IPChangeHistory.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"items": [_history_response(item) for item in items], "total": total, "page": page, "size": size, "pages": (total + size - 1) // size}


@router.get("/ip-addresses", response_model=dict)
def list_ips(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=1000),
    vlan: str | None = None, status: str | None = None, search: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(IPAddress).outerjoin(Asset)
    if vlan:
        query = query.filter(IPAddress.vlan == vlan)
    if status:
        query = query.filter(IPAddress.status == status)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                IPAddress.address.ilike(like),
                IPAddress.subnet.ilike(like),
                IPAddress.gateway.ilike(like),
                IPAddress.dns_primary.ilike(like),
                IPAddress.dns_secondary.ilike(like),
                IPAddress.vlan.ilike(like),
                IPAddress.status.ilike(like),
                IPAddress.description.ilike(like),
                IPAddress.notes.ilike(like),
                Asset.name.ilike(like),
                Asset.asset_tag.ilike(like),
            )
        )
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
    db.flush()
    _record_ip_address_history(db, ip, {"address": None, "status": None, "asset_id": None}, "IP 대장 등록", data.notes)
    db.commit()
    db.refresh(ip)
    log_action(db, "ip_address", ip.id, "create")
    return _to_response(ip)


@router.put("/ip-addresses/{ip_id}", response_model=IPAddressResponse)
def update_ip(ip_id: int, data: IPAddressUpdate, db: Session = Depends(get_db)):
    ip = db.query(IPAddress).filter(IPAddress.id == ip_id).first()
    if not ip:
        raise HTTPException(status_code=404, detail="IP address not found")

    update_data = data.model_dump(exclude_unset=True, exclude={"change_reason"})
    if "address" in update_data and update_data["address"] != ip.address:
        existing = db.query(IPAddress).filter(IPAddress.address == update_data["address"], IPAddress.id != ip.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="IP address already exists")

    old_data = {column.name: getattr(ip, column.name) for column in IPAddress.__table__.columns}
    for k, v in update_data.items():
        setattr(ip, k, v)

    reason = data.change_reason or "IP 대장 변경"
    _record_ip_address_history(db, ip, old_data, reason, data.notes)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="IP address already exists")
    db.refresh(ip)
    changes = compute_changes(old_data, update_data)
    log_action(db, "ip_address", ip.id, "update", changes=changes or None)
    return _to_response(ip)


@router.delete("/ip-addresses/{ip_id}")
def delete_ip(ip_id: int, db: Session = Depends(get_db)):
    ip = db.query(IPAddress).filter(IPAddress.id == ip_id).first()
    if not ip:
        raise HTTPException(status_code=404, detail="IP address not found")
    asset_tag, asset_name = _asset_info(db, ip.asset_id)
    db.add(
        IPChangeHistory(
            source_type="ip_address",
            source_id=ip.id,
            ip_address_id=ip.id,
            asset_tag=asset_tag,
            asset_name=asset_name,
            old_ip_address=ip.address,
            new_ip_address=None,
            old_status=ip.status,
            new_status=None,
            change_reason="IP 대장 삭제",
            notes=ip.notes,
        )
    )
    log_action(db, "ip_address", ip.id, "delete")
    db.delete(ip)
    db.commit()
    return {"message": "IP address deleted"}
