from datetime import datetime
from pathlib import Path
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, object_session

from app.api.deps import require_admin
from app.database import SessionLocal, get_db
from app.models.user import User
from app.services.audit_service import log_action
from app.services.database_backup_service import (
    DatabaseBackupError,
    create_sqlite_backup,
    ensure_backup_dir,
    get_database_info,
    list_backups,
    resolve_backup_file,
    restore_sqlite_database,
    serialize_backup,
)

router = APIRouter()


def _service_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _log_database_action(
    action: str,
    changes: dict,
    user_id: int | None = None,
    user_name: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        log_action(
            db,
            "database",
            0,
            action,
            changes=changes,
            user_id=user_id,
            user_name=user_name,
        )
    finally:
        db.close()


@router.get("/system/database")
def database_info(admin: User = Depends(require_admin)):
    _ = admin
    try:
        return get_database_info()
    except DatabaseBackupError as exc:
        raise _service_error(exc) from exc


@router.get("/system/database/backups")
def database_backups(admin: User = Depends(require_admin)):
    _ = admin
    return {"items": list_backups()}


@router.post("/system/database/backups", status_code=201)
def create_database_backup(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        backup_path = create_sqlite_backup()
    except DatabaseBackupError as exc:
        raise _service_error(exc) from exc

    backup = serialize_backup(backup_path)
    log_action(
        db,
        "database",
        0,
        "backup",
        changes={"filename": backup["filename"], "size_bytes": backup["size_bytes"]},
        user_id=admin.id,
        user_name=admin.name,
    )
    return backup


@router.get("/system/database/download")
def download_current_database(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        backup_path = create_sqlite_backup(prefix="itam_download")
    except DatabaseBackupError as exc:
        raise _service_error(exc) from exc

    backup = serialize_backup(backup_path)
    log_action(
        db,
        "database",
        0,
        "download",
        changes={"filename": backup["filename"], "size_bytes": backup["size_bytes"]},
        user_id=admin.id,
        user_name=admin.name,
    )
    return FileResponse(
        backup_path,
        media_type="application/vnd.sqlite3",
        filename=backup_path.name,
    )


@router.get("/system/database/backups/{filename}/download")
def download_database_backup(filename: str, admin: User = Depends(require_admin)):
    _ = admin
    try:
        backup_path = resolve_backup_file(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="백업 파일을 찾을 수 없습니다.") from exc
    except DatabaseBackupError as exc:
        raise _service_error(exc) from exc

    return FileResponse(
        backup_path,
        media_type="application/vnd.sqlite3",
        filename=backup_path.name,
    )


@router.post("/system/database/restore")
async def restore_database(
    file: UploadFile = File(...),
    create_backup_before_restore: bool = Form(True),
    admin: User = Depends(require_admin),
):
    upload_dir = ensure_backup_dir()
    upload_path = upload_dir / f"_restore_upload_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db"
    pre_restore_backup: Path | None = None
    admin_name = admin.name

    try:
        with upload_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        if create_backup_before_restore:
            pre_restore_backup = create_sqlite_backup(prefix="itam_pre_restore")

        admin_session = object_session(admin)
        if admin_session:
            admin_session.close()

        info = restore_sqlite_database(upload_path)
    except DatabaseBackupError as exc:
        raise _service_error(exc) from exc
    finally:
        await file.close()
        if upload_path.exists():
            upload_path.unlink()

    try:
        _log_database_action(
            "restore",
            {
                "uploaded_filename": file.filename,
                "pre_restore_backup": pre_restore_backup.name if pre_restore_backup else None,
            },
            user_name=admin_name,
        )
    except Exception:
        pass

    return {
        "message": "DB 복원이 완료되었습니다.",
        "database": info,
        "pre_restore_backup": serialize_backup(pre_restore_backup) if pre_restore_backup else None,
    }
