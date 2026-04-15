from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.subscription import CloudSubscription
from app.schemas.subscription import SubscriptionCreate, SubscriptionUpdate, SubscriptionResponse
from app.services.audit_service import log_action

router = APIRouter()


def _to_response(sub: CloudSubscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=sub.id, asset_id=sub.asset_id, provider=sub.provider, plan=sub.plan,
        billing_cycle=sub.billing_cycle, monthly_cost=sub.monthly_cost,
        renewal_date=sub.renewal_date, auto_renew=sub.auto_renew,
        account_url=sub.account_url, notes=sub.notes,
        asset_name=sub.asset.name if sub.asset else None,
        asset_tag=sub.asset.asset_tag if sub.asset else None,
        created_at=sub.created_at, updated_at=sub.updated_at,
    )


@router.get("/subscriptions", response_model=dict)
def list_subscriptions(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    query = db.query(CloudSubscription)
    total = query.count()
    items = query.order_by(CloudSubscription.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"items": [_to_response(i) for i in items], "total": total, "page": page, "size": size, "pages": (total + size - 1) // size}


@router.get("/subscriptions/{sub_id}", response_model=SubscriptionResponse)
def get_subscription(sub_id: int, db: Session = Depends(get_db)):
    sub = db.query(CloudSubscription).filter(CloudSubscription.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return _to_response(sub)


@router.post("/subscriptions", response_model=SubscriptionResponse, status_code=201)
def create_subscription(data: SubscriptionCreate, db: Session = Depends(get_db)):
    sub = CloudSubscription(**data.model_dump())
    db.add(sub)
    db.commit()
    db.refresh(sub)
    log_action(db, "subscription", sub.id, "create")
    return _to_response(sub)


@router.put("/subscriptions/{sub_id}", response_model=SubscriptionResponse)
def update_subscription(sub_id: int, data: SubscriptionUpdate, db: Session = Depends(get_db)):
    sub = db.query(CloudSubscription).filter(CloudSubscription.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(sub, k, v)
    db.commit()
    db.refresh(sub)
    log_action(db, "subscription", sub.id, "update")
    return _to_response(sub)


@router.delete("/subscriptions/{sub_id}")
def delete_subscription(sub_id: int, db: Session = Depends(get_db)):
    sub = db.query(CloudSubscription).filter(CloudSubscription.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    log_action(db, "subscription", sub.id, "delete")
    db.delete(sub)
    db.commit()
    return {"message": "Subscription deleted"}
