from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.asset import Asset
from app.models.common import Department
from app.models.device_inventory import Device
from app.schemas.location import DepartmentCreate, DepartmentUpdate, DepartmentResponse

router = APIRouter()


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_department_payload(data: DepartmentCreate | DepartmentUpdate, *, partial: bool = False) -> dict:
    payload = data.model_dump(exclude_unset=partial)
    for key in ("name", "code", "manager"):
        if key in payload:
            payload[key] = _clean_text(payload[key])
    if "name" in payload and not payload["name"]:
        raise HTTPException(status_code=400, detail="Department name is required")
    return payload


def _department_value_exists(
    db: Session,
    field,
    value: str,
    *,
    exclude_id: int | None = None,
) -> bool:
    query = db.query(Department.id).filter(func.lower(field) == value.lower())
    if exclude_id is not None:
        query = query.filter(Department.id != exclude_id)
    return query.first() is not None


def _sync_departments_from_devices(db: Session):
    existing = {name.strip().lower() for (name,) in db.query(Department.name).all() if name and name.strip()}
    names = {
        value.strip()
        for (value,) in db.query(Device.department).filter(Device.department.isnot(None)).distinct().all()
        if value and value.strip()
    }
    new_names = sorted((name for name in names if name.lower() not in existing), key=lambda item: item.casefold())
    if not new_names:
        return
    db.add_all(Department(name=name) for name in new_names)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def _department_usage_counts(db: Session, dept: Department) -> dict[str, int]:
    normalized_name = dept.name.strip().lower()
    return {
        "자산": db.query(Asset).filter(Asset.department_id == dept.id).count(),
        "디바이스": db.query(Device)
        .filter(func.lower(func.trim(Device.department)) == normalized_name)
        .count(),
    }


def _raise_if_department_in_use(db: Session, dept: Department) -> None:
    usages = {label: count for label, count in _department_usage_counts(db, dept).items() if count}
    if not usages:
        return
    detail = ", ".join(f"{label} {count}개" for label, count in usages.items())
    raise HTTPException(
        status_code=409,
        detail=f"이 부서는 사용 중이라 삭제할 수 없습니다. 먼저 연결된 항목을 수정하세요. ({detail})",
    )


@router.get("/departments", response_model=list[DepartmentResponse])
def list_departments(db: Session = Depends(get_db)):
    _sync_departments_from_devices(db)
    return db.query(Department).order_by(Department.name).all()

@router.post("/departments", response_model=DepartmentResponse, status_code=201)
def create_department(data: DepartmentCreate, db: Session = Depends(get_db)):
    payload = _clean_department_payload(data)
    if _department_value_exists(db, Department.name, payload["name"]):
        raise HTTPException(status_code=409, detail="Department already exists")
    if payload.get("code") and _department_value_exists(db, Department.code, payload["code"]):
        raise HTTPException(status_code=409, detail="Department code already exists")
    dept = Department(**payload)
    db.add(dept)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Department already exists")
    db.refresh(dept)
    return dept

@router.put("/departments/{dept_id}", response_model=DepartmentResponse)
def update_department(dept_id: int, data: DepartmentUpdate, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    payload = _clean_department_payload(data, partial=True)
    if "name" in payload and _department_value_exists(db, Department.name, payload["name"], exclude_id=dept_id):
        raise HTTPException(status_code=409, detail="Department already exists")
    if payload.get("code") and _department_value_exists(db, Department.code, payload["code"], exclude_id=dept_id):
        raise HTTPException(status_code=409, detail="Department code already exists")
    for k, v in payload.items():
        setattr(dept, k, v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Department already exists")
    db.refresh(dept)
    return dept

@router.delete("/departments/{dept_id}")
def delete_department(dept_id: int, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="부서를 찾을 수 없습니다.")
    _raise_if_department_in_use(db, dept)
    db.delete(dept)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="이 부서는 사용 중이라 삭제할 수 없습니다.")
    return {"message": "부서가 삭제되었습니다."}
