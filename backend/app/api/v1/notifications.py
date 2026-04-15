from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.notification import Notification
from app.schemas.notification import NotificationResponse, NotificationMarkRead

router = APIRouter()


@router.get("/notifications", response_model=dict)
def list_notifications(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Notification)
    if unread_only:
        query = query.filter(Notification.is_read == False)
    total = query.count()
    items = query.order_by(Notification.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return {"items": [NotificationResponse.model_validate(i) for i in items], "total": total, "page": page, "size": size, "pages": (total + size - 1) // size}


@router.get("/notifications/unread-count")
def unread_count(db: Session = Depends(get_db)):
    count = db.query(Notification).filter(Notification.is_read == False).count()
    return {"count": count}


@router.post("/notifications/mark-read")
def mark_read(data: NotificationMarkRead, db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.id.in_(data.ids)).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"message": f"{len(data.ids)} notifications marked as read"}


@router.post("/notifications/mark-all-read")
def mark_all_read(db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.is_read == False).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"message": "All notifications marked as read"}
