from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.asset import Asset
from app.services.qr_service import generate_qr_code, generate_qr_bytes

router = APIRouter()


@router.get("/qr/{asset_id}")
def get_qr(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    qr_bytes = generate_qr_bytes(asset.asset_tag, asset.id)
    return Response(content=qr_bytes, media_type="image/png")


@router.post("/qr/{asset_id}/generate")
def regenerate_qr(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    path = generate_qr_code(asset.asset_tag, asset.id)
    asset.qr_code_path = path
    db.commit()
    return {"qr_code_path": path}
