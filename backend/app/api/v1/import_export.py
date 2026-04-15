from fastapi import APIRouter, Depends, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.export_service import export_assets_to_excel, get_import_template, import_assets_from_excel

router = APIRouter()


@router.get("/export/assets")
def export_assets(category_id: int | None = None, db: Session = Depends(get_db)):
    output = export_assets_to_excel(db, category_id)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=assets.xlsx"},
    )


@router.get("/export/template")
def download_template():
    output = get_import_template()
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=import_template.xlsx"},
    )


@router.post("/import/assets")
async def import_assets(file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = await file.read()
    result = import_assets_from_excel(db, contents)
    return result
