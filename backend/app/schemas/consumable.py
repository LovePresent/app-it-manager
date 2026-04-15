from pydantic import BaseModel
from datetime import date, datetime


class ConsumableStockBase(BaseModel):
    asset_id: int
    qty_in_stock: int = 0
    min_stock_level: int = 0
    unit: str = "개"
    last_restock_date: date | None = None


class ConsumableStockCreate(ConsumableStockBase):
    pass


class ConsumableStockUpdate(BaseModel):
    qty_in_stock: int | None = None
    min_stock_level: int | None = None
    unit: str | None = None
    last_restock_date: date | None = None


class ConsumableStockResponse(ConsumableStockBase):
    id: int
    asset_name: str | None = None
    asset_tag: str | None = None
    is_low_stock: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConsumableTransactionBase(BaseModel):
    consumable_id: int
    qty_change: int
    transaction_type: str  # in, out
    notes: str | None = None


class ConsumableTransactionCreate(ConsumableTransactionBase):
    pass


class ConsumableTransactionResponse(ConsumableTransactionBase):
    id: int
    user_name: str | None = None
    date: datetime | None = None

    model_config = {"from_attributes": True}
