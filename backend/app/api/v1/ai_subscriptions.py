from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.ai_subscription import AIUsageSubscription
from app.schemas.ai_subscription import (
    AIUsageSubscriptionCreate,
    AIUsageSubscriptionResponse,
    AIUsageSubscriptionUpdate,
)
from app.services.audit_service import log_action

router = APIRouter()


@router.get("/ai-subscriptions", response_model=dict)
def list_ai_subscriptions(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=1000),
    search: str | None = None,
    provider: str | None = None,
    department: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(AIUsageSubscription)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                AIUsageSubscription.service_name.ilike(like),
                AIUsageSubscription.provider.ilike(like),
                AIUsageSubscription.model_name.ilike(like),
                AIUsageSubscription.plan_name.ilike(like),
                AIUsageSubscription.account_email.ilike(like),
                AIUsageSubscription.owner_name.ilike(like),
                AIUsageSubscription.employee_number.ilike(like),
                AIUsageSubscription.department.ilike(like),
                AIUsageSubscription.usage_purpose.ilike(like),
                AIUsageSubscription.notes.ilike(like),
            )
        )
    if provider:
        query = query.filter(AIUsageSubscription.provider == provider)
    if department:
        query = query.filter(AIUsageSubscription.department == department)
    if status:
        query = query.filter(AIUsageSubscription.status == status)

    total = query.count()
    items = (
        query.order_by(AIUsageSubscription.department.asc(), AIUsageSubscription.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.post("/ai-subscriptions", response_model=AIUsageSubscriptionResponse, status_code=201)
def create_ai_subscription(data: AIUsageSubscriptionCreate, db: Session = Depends(get_db)):
    item = AIUsageSubscription(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    log_action(db, "ai_subscription", item.id, "create", changes=jsonable_encoder(data.model_dump()))
    return item


@router.get("/ai-subscriptions/{subscription_id}", response_model=AIUsageSubscriptionResponse)
def get_ai_subscription(subscription_id: int, db: Session = Depends(get_db)):
    item = db.query(AIUsageSubscription).filter(AIUsageSubscription.id == subscription_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="AI 사용 구독을 찾을 수 없습니다.")
    return item


@router.put("/ai-subscriptions/{subscription_id}", response_model=AIUsageSubscriptionResponse)
def update_ai_subscription(
    subscription_id: int,
    data: AIUsageSubscriptionUpdate,
    db: Session = Depends(get_db),
):
    item = db.query(AIUsageSubscription).filter(AIUsageSubscription.id == subscription_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="AI 사용 구독을 찾을 수 없습니다.")

    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    log_action(db, "ai_subscription", item.id, "update", changes=jsonable_encoder(changes))
    return item


@router.delete("/ai-subscriptions/{subscription_id}")
def delete_ai_subscription(subscription_id: int, db: Session = Depends(get_db)):
    item = db.query(AIUsageSubscription).filter(AIUsageSubscription.id == subscription_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="AI 사용 구독을 찾을 수 없습니다.")
    log_action(db, "ai_subscription", item.id, "delete", changes={"service_name": item.service_name})
    db.delete(item)
    db.commit()
    return {"message": "AI subscription deleted"}
