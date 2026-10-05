from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class SavePurchasePlan(BaseModel):
    """保存一个到货日的人工总量；None恢复自动，0取消，严格整数拒绝隐式取整。

    confirmation_token仅用于异常人工量的二次确认，不能代替角色和截止校验。
    input_method区分键盘与加减键；来源只影响误按提醒，不影响超量或权限校验。
    """

    department_id: int = Field(ge=1)
    arrival_date: date
    supplier_product_id: int = Field(ge=1)
    quantity: int | None = Field(ge=0, le=1000000, strict=True)
    confirmation_token: str | None = Field(default=None, max_length=2000)
    input_method: Literal["keyboard", "stepper"] = "keyboard"


class SaveMinimumStock(BaseModel):
    """按门店供应目录设置预测销售后的目标余量，默认值由目录模型保存为0。"""

    department_id: int = Field(ge=1)
    supplier_product_id: int = Field(ge=1)
    minimum_stock: int = Field(ge=0, le=1000000, strict=True)
    confirmation_token: str | None = Field(default=None, max_length=2000)
    input_method: Literal["keyboard", "stepper"] = "keyboard"
