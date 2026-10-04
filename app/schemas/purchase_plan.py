from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class SavePurchasePlan(BaseModel):
    department_id: int = Field(ge=1)
    arrival_date: date
    supplier_product_id: int = Field(ge=1)
    quantity: int | None = Field(ge=0, le=1000000, strict=True)
    confirmation_token: str | None = Field(default=None, max_length=2000)
    input_method: Literal["keyboard", "stepper"] = "keyboard"


class SaveMinimumStock(BaseModel):
    department_id: int = Field(ge=1)
    supplier_product_id: int = Field(ge=1)
    minimum_stock: int = Field(ge=0, le=1000000, strict=True)
    confirmation_token: str | None = Field(default=None, max_length=2000)
    input_method: Literal["keyboard", "stepper"] = "keyboard"

