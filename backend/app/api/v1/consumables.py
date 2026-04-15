from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.consumable import ConsumableStock, ConsumableTransaction
from app.models.asset import Asset
from app.schemas.consumable import (
    ConsumableStockCreate, ConsumableStockUpdate, ConsumableStockResponse,
    ConsumableTransactionCreate, ConsumableTransactionResponse,
)
from app.services.audit_service import log_action

router = APIRouter()


def _to_response(cs: ConsumableStock) -> ConsumableStockResponse:
    return ConsumableStockResponse(
        id=cs.id, asset_id=cs.asset_id, qty_in_stock=cs.qty_in_stock,
        min_stock_level=cs.min_stock_level, unit=cs.unit,
        last_restock_date=cs.last_restock_date,
        asset_name=cs.asset.name if cs.asset else None,
        asset_tag=cs.asset.asset_tag if cs.asset else None,
        is_low_stock=cs.qty_in_stock <= cs.min_stock_level if cs.min_stock_level > 0 else False,
        created_at=cs.created_at, updated_at=cs.updated_at,
    )


@router.get("/consumables", response_model=dict)
def list_consumables(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), low_stock: bool = False, db: Session = Depends(get_db)):
    query = db.query(ConsumableStock)
    if low_stock:
        query = query.filter(ConsumableStock.qty_in_stock <= ConsumableStock.min_stock_level, ConsumableStock.min_stock_level > 0)
    total = query.count()
    items = query.order_by(ConsumableStock.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"items": [_to_response(i) for i in items], "total": total, "page": page, "size": size, "pages": (total + size - 1) // size}


@router.post("/consumables", response_model=ConsumableStockResponse, status_code=201)
def create_consumable(data: ConsumableStockCreate, db: Session = Depends(get_db)):
    cs = ConsumableStock(**data.model_dump())
    db.add(cs)
    db.commit()
    db.refresh(cs)
    log_action(db, "consumable", cs.id, "create")
    return _to_response(cs)


@router.put("/consumables/{cs_id}", response_model=ConsumableStockResponse)
def update_consumable(cs_id: int, data: ConsumableStockUpdate, db: Session = Depends(get_db)):
    cs = db.query(ConsumableStock).filter(ConsumableStock.id == cs_id).first()
    if not cs:
        raise HTTPException(status_code=404, detail="Consumable not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(cs, k, v)
    db.commit()
    db.refresh(cs)
    return _to_response(cs)


@router.post("/consumables/{cs_id}/transactions", response_model=ConsumableTransactionResponse, status_code=201)
def add_transaction(cs_id: int, data: ConsumableTransactionCreate, db: Session = Depends(get_db)):
    cs = db.query(ConsumableStock).filter(ConsumableStock.id == cs_id).first()
    if not cs:
        raise HTTPException(status_code=404, detail="Consumable not found")

    tx = ConsumableTransaction(consumable_id=cs_id, qty_change=data.qty_change, transaction_type=data.transaction_type, notes=data.notes)
    db.add(tx)

    if data.transaction_type == "in":
        cs.qty_in_stock += abs(data.qty_change)
    else:
        cs.qty_in_stock = max(0, cs.qty_in_stock - abs(data.qty_change))

    db.commit()
    db.refresh(tx)
    return ConsumableTransactionResponse(
        id=tx.id, consumable_id=tx.consumable_id, qty_change=tx.qty_change,
        transaction_type=tx.transaction_type, notes=tx.notes, date=tx.date,
        user_name=tx.user.name if tx.user else None,
    )


@router.get("/consumables/{cs_id}/transactions", response_model=list[ConsumableTransactionResponse])
def list_transactions(cs_id: int, db: Session = Depends(get_db)):
    txs = db.query(ConsumableTransaction).filter(ConsumableTransaction.consumable_id == cs_id).order_by(ConsumableTransaction.date.desc()).all()
    return [ConsumableTransactionResponse(
        id=tx.id, consumable_id=tx.consumable_id, qty_change=tx.qty_change,
        transaction_type=tx.transaction_type, notes=tx.notes, date=tx.date,
        user_name=tx.user.name if tx.user else None,
    ) for tx in txs]
