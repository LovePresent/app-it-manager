from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.certificate import Certificate
from app.schemas.certificate import CertificateCreate, CertificateUpdate, CertificateResponse
from app.services.audit_service import log_action

router = APIRouter()


def _to_response(c: Certificate) -> CertificateResponse:
    return CertificateResponse(
        id=c.id, asset_id=c.asset_id, domain=c.domain, issuer=c.issuer,
        issued_date=c.issued_date, expiry_date=c.expiry_date, cert_type=c.cert_type,
        auto_renew=c.auto_renew, registrar=c.registrar, notes=c.notes,
        asset_name=c.asset.name if c.asset else None,
        asset_tag=c.asset.asset_tag if c.asset else None,
        created_at=c.created_at, updated_at=c.updated_at,
    )


@router.get("/certificates", response_model=dict)
def list_certs(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), search: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Certificate)
    if search:
        query = query.filter(Certificate.domain.ilike(f"%{search}%"))
    total = query.count()
    items = query.order_by(Certificate.expiry_date).offset((page - 1) * size).limit(size).all()
    return {"items": [_to_response(i) for i in items], "total": total, "page": page, "size": size, "pages": (total + size - 1) // size}


@router.get("/certificates/{cert_id}", response_model=CertificateResponse)
def get_cert(cert_id: int, db: Session = Depends(get_db)):
    cert = db.query(Certificate).filter(Certificate.id == cert_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return _to_response(cert)


@router.post("/certificates", response_model=CertificateResponse, status_code=201)
def create_cert(data: CertificateCreate, db: Session = Depends(get_db)):
    cert = Certificate(**data.model_dump())
    db.add(cert)
    db.commit()
    db.refresh(cert)
    log_action(db, "certificate", cert.id, "create")
    return _to_response(cert)


@router.put("/certificates/{cert_id}", response_model=CertificateResponse)
def update_cert(cert_id: int, data: CertificateUpdate, db: Session = Depends(get_db)):
    cert = db.query(Certificate).filter(Certificate.id == cert_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(cert, k, v)
    db.commit()
    db.refresh(cert)
    log_action(db, "certificate", cert.id, "update")
    return _to_response(cert)


@router.delete("/certificates/{cert_id}")
def delete_cert(cert_id: int, db: Session = Depends(get_db)):
    cert = db.query(Certificate).filter(Certificate.id == cert_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    log_action(db, "certificate", cert.id, "delete")
    db.delete(cert)
    db.commit()
    return {"message": "Certificate deleted"}
