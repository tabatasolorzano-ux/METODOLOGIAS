from __future__ import annotations

from typing import Dict, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


class InventoryItem(BaseModel):
    quantity: int = 0
    unit_cost: float = 0.0
    min_stock: int = 0

    @property
    def status(self) -> Literal["OK", "Atento", "Bajo"]:
        if self.min_stock <= 0:
            return "OK"
        if self.quantity <= 0:
            return "Bajo"
        if self.quantity <= self.min_stock:
            return "Atento"
        return "OK"


class MovePayload(BaseModel):
    type: Literal["sale", "purchase"] = Field(
        description="Type of move: sale (egreso de inventario) or purchase (ingreso)."
    )
    product: str = Field(min_length=1, description="Product name")
    quantity: int = Field(gt=0, description="Units involved in the move")
    total_cost: Optional[float] = Field(
        default=None,
        gt=0,
        description="Total cost of the purchase. Required for purchases, ignored for sales.",
    )
    min_stock: Optional[int] = Field(
        default=None,
        ge=0,
        description="Optional minimum stock for the product. Only applied on purchases.",
    )


class InventoryResponse(BaseModel):
    product: str
    quantity: int
    unit_cost: float
    min_stock: int
    status: Literal["OK", "Atento", "Bajo"]


app = FastAPI(title="Stock PWA MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_inventory: Dict[str, InventoryItem] = {}


def _get_or_create_item(product: str) -> InventoryItem:
    product_key = product.strip().lower()
    if product_key not in _inventory:
        _inventory[product_key] = InventoryItem()
    return _inventory[product_key]


def _to_response(product: str, item: InventoryItem) -> InventoryResponse:
    return InventoryResponse(
        product=product,
        quantity=item.quantity,
        unit_cost=round(item.unit_cost, 2),
        min_stock=item.min_stock,
        status=item.status,
    )


@app.post("/api/move", response_model=InventoryResponse)
def register_move(payload: MovePayload) -> InventoryResponse:
    product_key = payload.product.strip().lower()
    if not product_key:
        raise HTTPException(status_code=400, detail="El producto es obligatorio.")

    item = _get_or_create_item(product_key)

    if payload.type == "purchase":
        if payload.total_cost is None:
            raise HTTPException(status_code=422, detail="El total gastado es obligatorio.")
        unit_cost = payload.total_cost / payload.quantity
        # weighted average cost
        total_units = item.quantity + payload.quantity
        if total_units == 0:
            item.unit_cost = unit_cost
        else:
            existing_value = item.quantity * item.unit_cost
            new_value = payload.quantity * unit_cost
            item.unit_cost = (existing_value + new_value) / total_units
        item.quantity += payload.quantity
        if payload.min_stock is not None:
            item.min_stock = payload.min_stock
    else:  # sale
        if payload.quantity > item.quantity:
            raise HTTPException(
                status_code=400,
                detail="No hay suficiente stock para completar la venta.",
            )
        item.quantity -= payload.quantity

    return _to_response(payload.product.strip(), item)


@app.get("/api/inventory", response_model=list[InventoryResponse])
def get_inventory() -> list[InventoryResponse]:
    return [
        _to_response(product.title(), item) for product, item in sorted(_inventory.items())
    ]


@app.post("/api/reset")
def reset_inventory() -> dict[str, str]:
    _inventory.clear()
    return {"message": "Inventario reiniciado"}
