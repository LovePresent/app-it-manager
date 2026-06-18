from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.device_inventory import ComputerSetting, Device, DeviceLicense, DeviceUsageHistory
from app.models.ip_address import IPChangeHistory
from app.schemas.device_inventory import (
    ComputerSettingCreate,
    ComputerSettingResponse,
    ComputerSettingSummary,
    ComputerSettingUpdate,
    DeviceBulkUpdateRequest,
    DeviceCreate,
    DeviceLicenseCreate,
    DeviceLicenseResponse,
    DeviceLicenseSummary,
    DeviceLicenseUpdate,
    DeviceReassignRequest,
    DeviceReplaceRequest,
    DeviceResponse,
    DeviceUpdate,
    DeviceUserMergeRequest,
    DeviceUsageHistoryResponse,
)
from app.services.audit_service import compute_changes, log_action

router = APIRouter()


def _license_summary(item: DeviceLicense | None) -> DeviceLicenseSummary | None:
    if not item:
        return None
    return DeviceLicenseSummary(
        hangul=item.hangul,
        ms_office=item.ms_office,
        cad=item.cad,
        windows_security=item.windows_security,
        pc_manager=item.pc_manager,
        dlp=item.dlp,
        av=item.av,
        edr=item.edr,
        renewal_date=item.renewal_date,
    )


def _setting_summary(item: ComputerSetting | None) -> ComputerSettingSummary | None:
    if not item:
        return None
    return ComputerSettingSummary(
        smart_app_control=item.smart_app_control,
        reputation_based_protection=item.reputation_based_protection,
        exploit_protection=item.exploit_protection,
        core_isolation=item.core_isolation,
    )


def _device_response(device: Device) -> DeviceResponse:
    return DeviceResponse(
        id=device.id,
        user_name=device.user_name,
        employee_number=device.employee_number,
        serial_number=device.serial_number,
        device_type=device.device_type,
        cpu=device.cpu,
        memory=device.memory,
        storage=device.storage,
        gpu=device.gpu,
        os_version=device.os_version,
        ip_address=device.ip_address,
        mac_address=device.mac_address,
        purchase_date=device.purchase_date,
        manufacture_date=device.manufacture_date,
        location=device.location,
        department=device.department,
        factory=device.factory,
        status=device.status,
        notes=device.notes,
        created_at=device.created_at,
        updated_at=device.updated_at,
        license_summary=_license_summary(device.license_profile),
        computer_setting_summary=_setting_summary(device.computer_setting),
    )


def _license_response(item: DeviceLicense) -> DeviceLicenseResponse:
    device = item.device
    return DeviceLicenseResponse(
        id=item.id,
        device_id=item.device_id,
        hangul=item.hangul,
        ms_office=item.ms_office,
        cad=item.cad,
        windows_security=item.windows_security,
        pc_manager=item.pc_manager,
        dlp=item.dlp,
        av=item.av,
        edr=item.edr,
        purchase_date=item.purchase_date,
        manufacture_date=item.manufacture_date,
        renewal_date=item.renewal_date,
        notes=item.notes,
        user_name=device.user_name if device else None,
        employee_number=device.employee_number if device else None,
        serial_number=device.serial_number if device else None,
        device_type=device.device_type if device else None,
        location=device.location if device else None,
        department=device.department if device else None,
        factory=device.factory if device else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _setting_response(item: ComputerSetting) -> ComputerSettingResponse:
    device = item.device
    return ComputerSettingResponse(
        id=item.id,
        device_id=item.device_id,
        smart_app_control=item.smart_app_control,
        reputation_based_protection=item.reputation_based_protection,
        exploit_protection=item.exploit_protection,
        core_isolation=item.core_isolation,
        notes=item.notes,
        user_name=device.user_name if device else None,
        employee_number=device.employee_number if device else None,
        serial_number=device.serial_number if device else None,
        device_type=device.device_type if device else None,
        location=device.location if device else None,
        department=device.department if device else None,
        factory=device.factory if device else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _device_search_filter(search: str):
    like = f"%{search}%"
    return or_(
        Device.user_name.ilike(like),
        Device.employee_number.ilike(like),
        Device.serial_number.ilike(like),
        Device.device_type.ilike(like),
        Device.cpu.ilike(like),
        Device.memory.ilike(like),
        Device.storage.ilike(like),
        Device.gpu.ilike(like),
        Device.os_version.ilike(like),
        Device.ip_address.ilike(like),
        Device.mac_address.ilike(like),
        Device.location.ilike(like),
        Device.department.ilike(like),
        Device.factory.ilike(like),
    )


def _close_active_history(db: Session, device: Device, reason: str, notes: str | None = None):
    active = (
        db.query(DeviceUsageHistory)
        .filter(DeviceUsageHistory.device_id == device.id, DeviceUsageHistory.ended_at.is_(None))
        .order_by(DeviceUsageHistory.id.desc())
        .first()
    )
    if active:
        active.ended_at = datetime.now()
        active.change_reason = reason
        active.notes = notes or active.notes


def _open_history(db: Session, device: Device, reason: str, notes: str | None = None):
    if not device.employee_number and not device.user_name:
        return
    db.add(
        DeviceUsageHistory(
            device_id=device.id,
            user_name=device.user_name,
            employee_number=device.employee_number,
            serial_number=device.serial_number,
            change_reason=reason,
            notes=notes,
        )
    )


def _record_device_network_history(
    db: Session,
    device: Device,
    old_ip_address: str | None,
    old_mac_address: str | None,
    reason: str,
    notes: str | None = None,
    old_serial_number: str | None = None,
):
    if old_ip_address == device.ip_address and old_mac_address == device.mac_address:
        return
    if not any((old_ip_address, device.ip_address, old_mac_address, device.mac_address)):
        return

    db.add(
        IPChangeHistory(
            source_type="device",
            source_id=device.id,
            device_id=device.id,
            old_serial_number=old_serial_number or device.serial_number,
            new_serial_number=device.serial_number,
            user_name=device.user_name,
            employee_number=device.employee_number,
            old_ip_address=old_ip_address,
            new_ip_address=device.ip_address,
            old_mac_address=old_mac_address,
            new_mac_address=device.mac_address,
            old_status=None,
            new_status=device.status,
            change_reason=reason,
            notes=notes,
        )
    )


def _handle_integrity_error(db: Session, exc: IntegrityError):
    db.rollback()
    message = str(exc.orig).lower()
    if "serial_number" in message:
        detail = "이미 등록된 시리얼 번호입니다."
    elif "device_licenses" in message or "uq_device_licenses_device_id" in message:
        detail = "해당 디바이스의 라이센스 현황이 이미 존재합니다."
    elif "computer_settings" in message or "uq_computer_settings_device_id" in message:
        detail = "해당 디바이스의 보안 설정이 이미 존재합니다."
    else:
        detail = "이미 존재하는 정보가 있습니다."
    raise HTTPException(status_code=409, detail=detail)


def _compute_changes_include_none(old_data: dict, new_data: dict) -> dict:
    changes = {}
    for key, new_val in new_data.items():
        old_val = old_data.get(key)
        if old_val != new_val:
            changes[key] = {"old": old_val, "new": new_val}
    return changes


@router.get("/devices", response_model=dict)
def list_devices(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=1000),
    search: str | None = None,
    device_type: str | None = None,
    factory: str | None = None,
    department: str | None = None,
    status: str | None = None,
    has_purchase_date: bool | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Device)
    if search:
        query = query.filter(_device_search_filter(search))
    if device_type:
        query = query.filter(Device.device_type == device_type)
    if factory:
        query = query.filter(Device.factory == factory)
    if department:
        query = query.filter(Device.department == department)
    if status:
        query = query.filter(Device.status == status)
    if has_purchase_date is True:
        query = query.filter(Device.purchase_date.is_not(None))
    elif has_purchase_date is False:
        query = query.filter(Device.purchase_date.is_(None))

    total = query.count()
    device_type_order = case(
        (Device.device_type == "desktop", 1),
        (Device.device_type == "laptop", 2),
        (Device.device_type == "all_in_one", 3),
        (Device.device_type == "monitor", 4),
        else_=9,
    )
    items = (
        query.order_by(
            func.coalesce(Device.department, "").asc(),
            func.coalesce(Device.user_name, "").asc(),
            func.coalesce(Device.employee_number, "").asc(),
            device_type_order.asc(),
            Device.id.desc(),
        )
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "items": [_device_response(item) for item in items],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.post("/devices/bulk-update", response_model=dict)
def bulk_update_devices(data: DeviceBulkUpdateRequest, db: Session = Depends(get_db)):
    device_ids = list(dict.fromkeys(data.device_ids))
    if not device_ids:
        raise HTTPException(status_code=400, detail="변경할 디바이스를 선택하세요.")

    update_data = data.updates.model_dump(exclude_unset=True)
    setting_data = data.computer_setting.model_dump(exclude_unset=True) if data.computer_setting else {}
    if not update_data and not setting_data:
        raise HTTPException(status_code=400, detail="변경할 항목을 선택하세요.")
    if "status" in update_data and not update_data["status"]:
        raise HTTPException(status_code=400, detail="상태를 선택하세요.")
    if "device_type" in update_data and not update_data["device_type"]:
        raise HTTPException(status_code=400, detail="종류를 선택하세요.")

    devices = db.query(Device).filter(Device.id.in_(device_ids)).all()
    found_ids = {device.id for device in devices}
    missing_ids = [device_id for device_id in device_ids if device_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"디바이스를 찾을 수 없습니다. ({', '.join(map(str, missing_ids))})")

    device_logs: list[tuple[int, dict]] = []
    setting_logs: list[tuple[int, dict]] = []
    setting_update_count = 0
    reason = data.reason or "일괄 변경"

    try:
        for device in devices:
            if update_data:
                old_data = {column.name: getattr(device, column.name) for column in Device.__table__.columns}
                for key, value in update_data.items():
                    setattr(device, key, value)
                changes = _compute_changes_include_none(old_data, update_data)
                if changes:
                    device_logs.append((device.id, {"reason": reason, "notes": data.notes, "changes": changes}))

            if setting_data:
                setting = device.computer_setting
                if not setting:
                    setting = ComputerSetting(device_id=device.id)
                    db.add(setting)
                    old_setting = {key: None for key in setting_data}
                else:
                    old_setting = {column.name: getattr(setting, column.name) for column in ComputerSetting.__table__.columns}
                for key, value in setting_data.items():
                    setattr(setting, key, value)
                changes = _compute_changes_include_none(old_setting, setting_data)
                if changes:
                    setting_update_count += 1
                    db.flush()
                    setting_logs.append((setting.id, {"reason": reason, "notes": data.notes, "device_id": device.id, "changes": changes}))

        db.commit()
    except IntegrityError as exc:
        _handle_integrity_error(db, exc)

    for entity_id, changes in device_logs:
        log_action(db, "device", entity_id, "bulk_update", changes=jsonable_encoder(changes))
    for entity_id, changes in setting_logs:
        log_action(db, "computer_setting", entity_id, "bulk_update", changes=jsonable_encoder(changes))

    return {
        "message": "일괄 변경이 완료되었습니다.",
        "updated": len(devices),
        "device_fields_updated": len(device_logs),
        "computer_settings_updated": setting_update_count,
    }


@router.post("/devices/merge-users", response_model=dict)
def merge_device_user_info(data: DeviceUserMergeRequest, db: Session = Depends(get_db)):
    device_ids = list(dict.fromkeys(data.device_ids))
    if not device_ids:
        raise HTTPException(status_code=400, detail="병합할 디바이스를 선택하세요.")

    target_data = data.target.model_dump()
    if not target_data.get("user_name") and not target_data.get("employee_number"):
        raise HTTPException(status_code=400, detail="기준 사용자 또는 사번이 필요합니다.")

    devices = db.query(Device).filter(Device.id.in_(device_ids)).all()
    found_ids = {device.id for device in devices}
    missing_ids = [device_id for device_id in device_ids if device_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"디바이스를 찾을 수 없습니다. ({', '.join(map(str, missing_ids))})")

    reason = data.reason or "중복 사용자 정보 병합"
    device_logs: list[tuple[int, dict]] = []
    updated_count = 0

    try:
        for device in devices:
            old_data = {column.name: getattr(device, column.name) for column in Device.__table__.columns}
            user_changed = (
                old_data.get("user_name") != target_data.get("user_name")
                or old_data.get("employee_number") != target_data.get("employee_number")
            )

            if user_changed:
                _close_active_history(db, device, reason, data.notes)

            for key, value in target_data.items():
                setattr(device, key, value)

            if user_changed:
                if device.user_name or device.employee_number:
                    if device.status == "stock":
                        device.status = "assigned"
                    _open_history(db, device, reason, data.notes)
                else:
                    device.status = "stock"

            new_data = {**target_data, "status": device.status}
            changes = _compute_changes_include_none(old_data, new_data)
            if changes:
                updated_count += 1
                device_logs.append(
                    (
                        device.id,
                        {
                            "reason": reason,
                            "notes": data.notes,
                            "target": target_data,
                            "changes": changes,
                        },
                    )
                )

        db.commit()
    except IntegrityError as exc:
        _handle_integrity_error(db, exc)

    for entity_id, changes in device_logs:
        log_action(db, "device", entity_id, "merge_user_info", changes=jsonable_encoder(changes))

    return {
        "message": "중복 사용자 정보 병합이 완료되었습니다.",
        "updated": updated_count,
    }


@router.get("/devices/{device_id}", response_model=DeviceResponse)
def get_device(device_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="디바이스를 찾을 수 없습니다.")
    return _device_response(device)


@router.post("/devices", response_model=DeviceResponse, status_code=201)
def create_device(data: DeviceCreate, db: Session = Depends(get_db)):
    payload = data.model_dump(exclude={"initial_reason"})
    device = Device(**payload)
    if not device.user_name and not device.employee_number:
        device.status = "stock"
    db.add(device)
    try:
        db.flush()
        _open_history(db, device, data.initial_reason)
        _record_device_network_history(db, device, None, None, "초기 IP/MAC 등록")
        db.commit()
    except IntegrityError as exc:
        _handle_integrity_error(db, exc)
    db.refresh(device)
    log_action(db, "device", device.id, "create", changes=jsonable_encoder(data.model_dump()))
    return _device_response(device)


@router.put("/devices/{device_id}", response_model=DeviceResponse)
def update_device(device_id: int, data: DeviceUpdate, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="디바이스를 찾을 수 없습니다.")

    old_data = {column.name: getattr(device, column.name) for column in Device.__table__.columns}
    old_ip_address = device.ip_address
    old_mac_address = device.mac_address
    update_data = data.model_dump(exclude_unset=True, exclude={"assignment_reason"})
    user_changed = any(key in update_data for key in ("user_name", "employee_number"))
    reason = data.assignment_reason or "사용자 변경"

    if user_changed:
        _close_active_history(db, device, reason)

    for key, value in update_data.items():
        setattr(device, key, value)

    network_changed = old_ip_address != device.ip_address or old_mac_address != device.mac_address

    if user_changed:
        if device.user_name or device.employee_number:
            device.status = "assigned"
            _open_history(db, device, reason)
        else:
            device.status = "stock"

    try:
        if network_changed:
            _record_device_network_history(db, device, old_ip_address, old_mac_address, "IP/MAC 변경")
        db.commit()
    except IntegrityError as exc:
        _handle_integrity_error(db, exc)
    db.refresh(device)

    changes = compute_changes(old_data, update_data)
    if changes:
        log_action(db, "device", device.id, "update", changes=jsonable_encoder(changes))
    return _device_response(device)


@router.delete("/devices/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="디바이스를 찾을 수 없습니다.")
    log_action(db, "device", device.id, "delete", changes={"serial_number": device.serial_number})
    db.delete(device)
    db.commit()
    return {"message": "Device deleted"}


@router.post("/devices/{device_id}/reassign", response_model=DeviceResponse)
def reassign_device(device_id: int, data: DeviceReassignRequest, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="디바이스를 찾을 수 없습니다.")

    _close_active_history(db, device, data.reason, data.notes)
    device.user_name = data.user_name
    device.employee_number = data.employee_number
    if data.location is not None:
        device.location = data.location
    if data.department is not None:
        device.department = data.department
    if data.factory is not None:
        device.factory = data.factory
    device.status = "assigned" if data.user_name or data.employee_number else "stock"
    _open_history(db, device, data.reason, data.notes)
    db.commit()
    db.refresh(device)
    log_action(db, "device", device.id, "reassign", changes=jsonable_encoder(data.model_dump()))
    return _device_response(device)


@router.post("/devices/{device_id}/replace", response_model=DeviceResponse, status_code=201)
def replace_device(device_id: int, data: DeviceReplaceRequest, db: Session = Depends(get_db)):
    old_device = db.query(Device).filter(Device.id == device_id).first()
    if not old_device:
        raise HTTPException(status_code=404, detail="디바이스를 찾을 수 없습니다.")

    _close_active_history(db, old_device, data.replacement_reason)
    old_device.status = "replaced"
    new_device = Device(**data.model_dump(exclude={"replacement_reason"}))
    if not new_device.user_name and not new_device.employee_number:
        new_device.user_name = old_device.user_name
        new_device.employee_number = old_device.employee_number
    if not new_device.location:
        new_device.location = old_device.location
    if not new_device.department:
        new_device.department = old_device.department
    if not new_device.factory:
        new_device.factory = old_device.factory
    new_device.status = "assigned" if new_device.user_name or new_device.employee_number else "stock"

    db.add(new_device)
    try:
        db.flush()
        _open_history(db, new_device, f"{data.replacement_reason} 지급")
        _record_device_network_history(
            db,
            new_device,
            old_device.ip_address,
            old_device.mac_address,
            f"{data.replacement_reason} IP/MAC 변경",
            old_serial_number=old_device.serial_number,
        )
        db.commit()
    except IntegrityError as exc:
        _handle_integrity_error(db, exc)
    db.refresh(new_device)
    log_action(
        db,
        "device",
        old_device.id,
        "replace",
        changes=jsonable_encoder({"old_serial_number": old_device.serial_number, "new_serial_number": new_device.serial_number}),
    )
    return _device_response(new_device)


@router.get("/devices/{device_id}/history", response_model=list[DeviceUsageHistoryResponse])
def list_device_history(device_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="디바이스를 찾을 수 없습니다.")
    return (
        db.query(DeviceUsageHistory)
        .filter(DeviceUsageHistory.device_id == device_id)
        .order_by(DeviceUsageHistory.started_at.desc(), DeviceUsageHistory.id.desc())
        .all()
    )


@router.get("/device-licenses", response_model=dict)
def list_device_licenses(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=1000),
    search: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(DeviceLicense).join(Device)
    if search:
        query = query.filter(_device_search_filter(search))
    total = query.count()
    items = query.order_by(Device.employee_number.asc(), DeviceLicense.id.desc()).offset((page - 1) * size).limit(size).all()
    return {
        "items": [_license_response(item) for item in items],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.post("/device-licenses", response_model=DeviceLicenseResponse, status_code=201)
def create_device_license(data: DeviceLicenseCreate, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == data.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="디바이스를 찾을 수 없습니다.")
    item = DeviceLicense(**data.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        _handle_integrity_error(db, exc)
    db.refresh(item)
    log_action(db, "device_license", item.id, "create", changes=jsonable_encoder(data.model_dump()))
    return _license_response(item)


@router.put("/device-licenses/{license_id}", response_model=DeviceLicenseResponse)
def update_device_license(license_id: int, data: DeviceLicenseUpdate, db: Session = Depends(get_db)):
    item = db.query(DeviceLicense).filter(DeviceLicense.id == license_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="라이센스 현황을 찾을 수 없습니다.")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        _handle_integrity_error(db, exc)
    db.refresh(item)
    log_action(db, "device_license", item.id, "update", changes=jsonable_encoder(data.model_dump(exclude_unset=True)))
    return _license_response(item)


@router.delete("/device-licenses/{license_id}")
def delete_device_license(license_id: int, db: Session = Depends(get_db)):
    item = db.query(DeviceLicense).filter(DeviceLicense.id == license_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="라이센스 현황을 찾을 수 없습니다.")
    log_action(db, "device_license", item.id, "delete")
    db.delete(item)
    db.commit()
    return {"message": "Device license deleted"}


@router.get("/computer-settings", response_model=dict)
def list_computer_settings(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=1000),
    search: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(ComputerSetting).join(Device)
    if search:
        query = query.filter(_device_search_filter(search))
    total = query.count()
    items = query.order_by(Device.employee_number.asc(), ComputerSetting.id.desc()).offset((page - 1) * size).limit(size).all()
    return {
        "items": [_setting_response(item) for item in items],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.post("/computer-settings", response_model=ComputerSettingResponse, status_code=201)
def create_computer_setting(data: ComputerSettingCreate, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == data.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="디바이스를 찾을 수 없습니다.")
    item = ComputerSetting(**data.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        _handle_integrity_error(db, exc)
    db.refresh(item)
    log_action(db, "computer_setting", item.id, "create", changes=jsonable_encoder(data.model_dump()))
    return _setting_response(item)


@router.put("/computer-settings/{setting_id}", response_model=ComputerSettingResponse)
def update_computer_setting(setting_id: int, data: ComputerSettingUpdate, db: Session = Depends(get_db)):
    item = db.query(ComputerSetting).filter(ComputerSetting.id == setting_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="컴퓨터 설정을 찾을 수 없습니다.")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        _handle_integrity_error(db, exc)
    db.refresh(item)
    log_action(db, "computer_setting", item.id, "update", changes=jsonable_encoder(data.model_dump(exclude_unset=True)))
    return _setting_response(item)


@router.delete("/computer-settings/{setting_id}")
def delete_computer_setting(setting_id: int, db: Session = Depends(get_db)):
    item = db.query(ComputerSetting).filter(ComputerSetting.id == setting_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="컴퓨터 설정을 찾을 수 없습니다.")
    log_action(db, "computer_setting", item.id, "delete")
    db.delete(item)
    db.commit()
    return {"message": "Computer setting deleted"}
