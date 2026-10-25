from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.routing import APIRoute
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models.user import User
from app.services import device_ledger_migration_service as service


class LimitedUploadRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def limited(request):
            # Enforce the actual streamed request before multipart parsing; a
            # missing/forged Content-Length cannot cause an unbounded temp file.
            limit = service.MAX_BYTES + 65536
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > limit:
                    raise HTTPException(413, "가져오기 파일은 8MiB 이하이어야 합니다.")
                body.extend(chunk)
            request._body = bytes(body)
            return await handler(request)
        return limited


router = APIRouter(route_class=LimitedUploadRoute)


async def contents(file):
    try:
        raw = await file.read(service.MAX_BYTES + 1)
    finally:
        await file.close()
    return service.parse_payload(raw)


@router.post("/devices/migration/preview")
async def preview(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    payload, payload_hash = await contents(file)
    try:
        result = service.preview(db.connection(), payload, payload_hash)
        return result
    except HTTPException:
        raise
    except Exception:
        # SQL bind/validation failures can contain personal data. Never allow
        # their traceback or submitted values into application/server logs.
        raise HTTPException(422, "파일의 자료를 안전하게 미리보기할 수 없습니다. 형식과 연결 자료를 확인해 주세요.") from None
    finally:
        db.rollback()


@router.post("/devices/migration/apply")
async def apply(request: Request, file: UploadFile = File(...), preview_fingerprint: str = Form(...),
                db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if db.bind.dialect.name != "sqlite":
        raise HTTPException(503, "현재 장비 대장 가져오기는 SQLite 서버에서만 지원합니다. 다른 데이터베이스는 별도 검증이 필요합니다.")
    payload, payload_hash = await contents(file)
    actor_id = user.id
    db.rollback()
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        # Recheck the principal after taking the write transaction; a stale UI
        # cannot retain revoked administrator authorization.
        actor = db.scalar(select(User).where(User.id == actor_id).with_for_update())
        if actor is None or actor.role != "admin" or not actor.is_active:
            raise HTTPException(403, "관리자 권한이 필요합니다.")
        result = service.apply_plan(db.connection(), payload, payload_hash, preview_fingerprint,
                                    {"id": actor.id, "name": actor.name}, request.client.host if request.client else None)
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "운영 자료와 충돌하여 전체 적용을 취소했습니다. 다시 미리보기해 주세요.") from None
    except Exception:
        db.rollback()
        raise HTTPException(422, "자료를 안전하게 적용할 수 없어 전체 적용을 취소했습니다. 파일을 다시 확인해 주세요.") from None
