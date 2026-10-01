"""AI 可提议的 MarketFlow 数据变更类型、参数校验与确认摘要。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.discount_rule_requests import (
    AddDiscountRuleProductsRequest,
    CreateDiscountRuleRequest,
    UpdateDiscountRuleRequest,
    UpdateDiscountRuleStatusRequest,
)
from app.schemas.employees_requests import (
    EmployeeDetailUpdateRequest,
    EmployeesCreateRequest,
    EmployeesStatusUpdateRequest,
)
from app.schemas.products_requests import UpdateProductRequest
from app.schemas.purchases_requests import CreatePurchaseRequest
from app.schemas.sales_requests import CreateSaleRequest
from app.schemas.supplier_products_requests import (
    SupplierProductCreateRequest,
    SupplierProductStatusUpdateRequest,
    SupplierProductUpdateRequest,
)
from app.schemas.suppliers_requests import (
    SuppliersCreateRequest,
    SuppliersStatusUpdateRequest,
    SuppliersUpdateRequest,
)

AiBusinessActionType = Literal[
    "update_product_details",
    "create_supplier",
    "update_supplier",
    "update_supplier_status",
    "create_supplier_product",
    "update_supplier_product",
    "update_supplier_product_status",
    "create_purchase",
    "create_sale",
    "create_employee",
    "update_employee_status",
    "update_employee_details",
    "create_discount_rule",
    "add_discount_products",
    "remove_discount_product",
    "clear_discount_products",
    "update_discount_rule",
    "update_discount_status",
    "delete_discount_rule",
    "clear_discount_rules",
]


# region AI统一业务操作请求
class BusinessActionArguments(BaseModel):
    """模型调用统一写工具时提交的操作类型和业务参数。"""

    action_type: AiBusinessActionType = Field(..., description="准备执行的业务操作类型")
    payload: dict[str, Any] = Field(..., description="该操作需要的完整业务参数")


# endregion


# region 带目标ID的参数模型
class UpdateProductArguments(UpdateProductRequest):
    product_id: int = Field(..., ge=1)


class UpdateSupplierArguments(SuppliersUpdateRequest):
    supplier_id: int = Field(..., ge=1)


class UpdateSupplierStatusArguments(SuppliersStatusUpdateRequest):
    supplier_id: int = Field(..., ge=1)


class UpdateSupplierProductArguments(SupplierProductUpdateRequest):
    supplier_product_id: int = Field(..., ge=1)


class UpdateSupplierProductStatusArguments(SupplierProductStatusUpdateRequest):
    supplier_product_id: int = Field(..., ge=1)


class UpdateEmployeeStatusArguments(EmployeesStatusUpdateRequest):
    employee_id: int = Field(..., ge=1)


class UpdateEmployeeDetailsArguments(EmployeeDetailUpdateRequest):
    employee_id: int = Field(..., ge=1)


class AddDiscountProductsArguments(AddDiscountRuleProductsRequest):
    discount_rule_id: int = Field(..., ge=1)


class RemoveDiscountProductArguments(BaseModel):
    discount_rule_id: int = Field(..., ge=1)
    product_id: int = Field(..., ge=1)


class DiscountRuleIdArguments(BaseModel):
    discount_rule_id: int = Field(..., ge=1)


class UpdateDiscountRuleArguments(UpdateDiscountRuleRequest):
    discount_rule_id: int = Field(..., ge=1)


class UpdateDiscountStatusArguments(UpdateDiscountRuleStatusRequest):
    discount_rule_id: int = Field(..., ge=1)


class EmptyArguments(BaseModel):
    """不需要额外业务参数的批量操作。"""

    model_config = ConfigDict(extra="forbid")


# endregion


ACTION_PARAMETER_MODELS: dict[str, type[BaseModel]] = {
    "update_product_details": UpdateProductArguments,
    "create_supplier": SuppliersCreateRequest,
    "update_supplier": UpdateSupplierArguments,
    "update_supplier_status": UpdateSupplierStatusArguments,
    "create_supplier_product": SupplierProductCreateRequest,
    "update_supplier_product": UpdateSupplierProductArguments,
    "update_supplier_product_status": UpdateSupplierProductStatusArguments,
    "create_purchase": CreatePurchaseRequest,
    "create_sale": CreateSaleRequest,
    "create_employee": EmployeesCreateRequest,
    "update_employee_status": UpdateEmployeeStatusArguments,
    "update_employee_details": UpdateEmployeeDetailsArguments,
    "create_discount_rule": CreateDiscountRuleRequest,
    "add_discount_products": AddDiscountProductsArguments,
    "remove_discount_product": RemoveDiscountProductArguments,
    "clear_discount_products": DiscountRuleIdArguments,
    "update_discount_rule": UpdateDiscountRuleArguments,
    "update_discount_status": UpdateDiscountStatusArguments,
    "delete_discount_rule": DiscountRuleIdArguments,
    "clear_discount_rules": EmptyArguments,
}

ACTION_NAMES = {
    "update_product_details": "修改商品资料",
    "create_supplier": "创建供应商",
    "update_supplier": "修改供应商资料",
    "update_supplier_status": "修改供应商状态",
    "create_supplier_product": "创建供应商商品",
    "update_supplier_product": "修改供应商商品",
    "update_supplier_product_status": "修改供应商商品状态",
    "create_purchase": "创建进货单",
    "create_sale": "创建销售单并扣减库存",
    "create_employee": "创建员工账号",
    "update_employee_status": "修改员工账号状态",
    "update_employee_details": "修改员工资料",
    "create_discount_rule": "创建折扣规则",
    "add_discount_products": "添加折扣商品",
    "remove_discount_product": "删除单个折扣商品",
    "clear_discount_products": "清空规则内的折扣商品",
    "update_discount_rule": "修改折扣规则",
    "update_discount_status": "开启或关闭折扣规则",
    "delete_discount_rule": "删除折扣规则",
    "clear_discount_rules": "清空权限范围内的全部折扣规则",
}


def validate_business_action(action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """按操作类型选择对应请求模型，返回可安全保存的标准化参数。"""

    parameter_model = ACTION_PARAMETER_MODELS.get(action_type)
    if parameter_model is None:
        raise ValueError("该业务操作尚未向AI开放")
    validated = parameter_model.model_validate(payload)
    return validated.model_dump(mode="json", exclude_unset=True)


def build_business_action_summary(action_type: str, payload: dict[str, Any]) -> str:
    """生成确认卡片使用的简洁中文摘要，避免用户只看到内部操作代码。"""

    action_name = ACTION_NAMES[action_type]
    target_parts: list[str] = []
    for field_name, label in (
        ("product_id", "商品ID"),
        ("supplier_id", "供应商ID"),
        ("supplier_product_id", "供应商商品ID"),
        ("employee_id", "员工ID"),
        ("discount_rule_id", "折扣规则ID"),
    ):
        value = payload.get(field_name)
        if value is not None:
            target_parts.append(f"{label} {value}")

    name = payload.get("name")
    if isinstance(name, str):
        target_parts.append(f"名称“{name}”")
    item_values = payload.get("items")
    if isinstance(item_values, list):
        target_parts.append(f"共 {len(item_values)} 种明细")
    product_ids = payload.get("product_ids")
    if isinstance(product_ids, list):
        target_parts.append(f"共 {len(product_ids)} 个商品")

    if not target_parts:
        return action_name
    return f"{action_name}：{'，'.join(target_parts)}"


__all__ = [
    "ACTION_NAMES",
    "BusinessActionArguments",
    "build_business_action_summary",
    "validate_business_action",
]
