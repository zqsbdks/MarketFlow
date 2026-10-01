"""MarketFlow AI 工具白名单、参数校验与业务函数调度。"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.action_registry import (
    ACTION_NAMES,
    BusinessActionArguments,
    build_business_action_summary,
    validate_business_action,
)
from app.crud.ai_pending_actions import create_ai_pending_action
from app.crud.auth import get_employee_by_id
from app.models.ai_pending_action import AiPendingAction
from app.models.enums import (
    DiscountComputedStatus,
    DiscountScheduleType,
    DiscountType,
    EmployeeRole,
    InventoryBatchStatus,
    ProductStatus,
    PurchaseStatus,
)
from app.schemas.discount_rule_requests import GetDiscountRuleProductsRequest
from app.services.categories import get_categories_list_service
from app.services.departments import get_departments_list_service
from app.services.discount_rule import (
    get_discount_rule_detail_service,
    get_discount_rule_list_service,
    get_discount_rule_products_service,
)
from app.services.employees import get_employee_detail_service, get_list_employees_service
from app.services.inventory_batches import (
    get_inventory_batch_detail_service,
    get_inventory_batches_list_service,
)
from app.services.products import get_product_detail_service, get_products_list_service
from app.services.purchases import get_purchase_detail_service, get_purchases_list_service
from app.services.reports import overview_service
from app.services.supplier_products import (
    get_supplier_product_detail_service,
    get_supplier_products_list_service,
)
from app.services.suppliers import get_supplier_detail_service, get_suppliers_list_service

AI_ACTION_EXPIRY_MINUTES = 10


# region 工具参数模型
class ProductSearchArguments(BaseModel):
    """按名称、编号含义或库存预警查询商品。"""

    keyword: str | None = Field(None, max_length=100)
    department_id: int | None = Field(None, ge=1)
    low_stock: bool | None = None
    status: ProductStatus | None = None

    model_config = ConfigDict(str_strip_whitespace=True)


class BatchListArguments(BaseModel):
    """查询库存批次的常用筛选条件。"""

    status: InventoryBatchStatus | None = None
    supplier_id: int | None = Field(None, ge=1)
    product_id: int | None = Field(None, ge=1)
    department_id: int | None = Field(None, ge=1)
    expiration_start: date | None = None
    expiration_end: date | None = None


class IdArguments(BaseModel):
    """只需要一个正整数ID的工具参数。"""

    id: int = Field(..., ge=1)


class PurchaseListArguments(BaseModel):
    """查询近期进货单的筛选条件。"""

    purchase_no: str | None = Field(None, max_length=30)
    department_id: int | None = Field(None, ge=1)
    status: PurchaseStatus | None = None

    model_config = ConfigDict(str_strip_whitespace=True)


class SalesOverviewArguments(BaseModel):
    """营业概览工具的可选时间范围。"""

    start_time: datetime | None = None
    end_time: datetime | None = None
    department_id: int | None = Field(None, ge=1)


class SupplierListArguments(BaseModel):
    """查询供应商列表的状态筛选参数。"""

    is_active: bool | None = None


class SupplierProductListArguments(BaseModel):
    """查询供应商商品目录的常用筛选参数。"""

    supplier_id: int | None = Field(None, ge=1)
    keyword: str | None = Field(None, min_length=1, max_length=100)
    is_active: bool | None = None

    model_config = ConfigDict(str_strip_whitespace=True)


class EmployeeListArguments(BaseModel):
    """查询员工列表的部门、角色和状态筛选参数。"""

    department_id: int | None = Field(None, ge=1)
    role: EmployeeRole | None = None
    is_active: bool | None = None


class CategoryListArguments(BaseModel):
    """查询全部分类或指定部门分类。"""

    department_id: int | None = Field(None, ge=1)


class DiscountRuleListArguments(BaseModel):
    """查询折扣规则的常用筛选参数。"""

    keyword: str | None = Field(None, min_length=1, max_length=100)
    department_id: int | None = Field(None, ge=1)
    discount_type: DiscountType | None = None
    schedule_type: DiscountScheduleType | None = None
    is_active: bool | None = None
    computed_status: DiscountComputedStatus | None = None

    model_config = ConfigDict(str_strip_whitespace=True)


class DiscountProductListArguments(BaseModel):
    """查询一条折扣规则所关联商品的参数。"""

    discount_rule_id: int = Field(..., ge=1)
    keyword: str | None = Field(None, min_length=1, max_length=100)
    category_id: int | None = Field(None, ge=1)

    model_config = ConfigDict(str_strip_whitespace=True)


class InventoryAdjustmentArguments(BaseModel):
    """AI提出库存数量调整时必须提供的参数。"""

    batch_id: int = Field(..., ge=1)
    remaining_quantity: int = Field(..., ge=0)
    reason: str | None = Field(None, min_length=1, max_length=255)

    model_config = ConfigDict(str_strip_whitespace=True)


class DiscardBatchArguments(BaseModel):
    """AI提出废弃过期批次时必须提供的参数。"""

    batch_id: int = Field(..., ge=1)
    reason: str | None = Field(None, min_length=1, max_length=255)

    model_config = ConfigDict(str_strip_whitespace=True)


class ProductStatusArguments(BaseModel):
    """AI提出上架或停售商品时必须提供的参数。"""

    product_id: int = Field(..., ge=1)
    status: ProductStatus
    reason: str | None = Field(None, min_length=1, max_length=255)

    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


@dataclass
class ToolExecutionResult:
    """工具返回给模型的结果及可选待确认记录。"""

    data: dict[str, Any]
    pending_action: AiPendingAction | None = None


# region 模型可见工具定义
MARKETFLOW_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_products",
        "description": (
            "查询实时商品库存，可按关键词、部门、在售状态或低库存筛选，"
            "返回全部、可售、临期和过期库存。"
        ),
        "parameters": ProductSearchArguments.model_json_schema(),
    },
    {
        "name": "list_inventory_batches",
        "description": (
            "查询实时库存批次，可筛选可用、临期、过期、售完、供应商、商品、部门或到期日期。"
        ),
        "parameters": BatchListArguments.model_json_schema(),
    },
    {
        "name": "get_inventory_batch",
        "description": "根据库存批次ID查询完整批次详情。",
        "parameters": IdArguments.model_json_schema(),
    },
    {
        "name": "list_purchases",
        "description": "查询近期进货单列表及待到货、已到货状态。",
        "parameters": PurchaseListArguments.model_json_schema(),
    },
    {
        "name": "get_purchase",
        "description": "根据进货单ID查询进货单及全部明细。",
        "parameters": IdArguments.model_json_schema(),
    },
    {
        "name": "get_sales_overview",
        "description": "查询指定营业时间和部门的实时营业额、成本、毛利润、销量和销售单数。",
        "parameters": SalesOverviewArguments.model_json_schema(),
    },
    {
        "name": "list_departments",
        "description": "查询系统中的部门名称和ID，创建或筛选业务数据前可先调用。",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_categories",
        "description": "查询商品分类名称和ID，可按部门筛选。",
        "parameters": CategoryListArguments.model_json_schema(),
    },
    {
        "name": "list_suppliers",
        "description": "查询供应商列表、编号、名称、ID及合作状态。",
        "parameters": SupplierListArguments.model_json_schema(),
    },
    {
        "name": "get_supplier",
        "description": "根据供应商ID查询供应商详情。",
        "parameters": IdArguments.model_json_schema(),
    },
    {
        "name": "list_supplier_products",
        "description": "查询供应商商品目录及目录ID、供应商、价格、分类和保质期。",
        "parameters": SupplierProductListArguments.model_json_schema(),
    },
    {
        "name": "get_supplier_product",
        "description": "根据供应商商品目录ID查询详情。",
        "parameters": IdArguments.model_json_schema(),
    },
    {
        "name": "list_employees",
        "description": "查询员工ID、编号、部门、角色和启用状态；该查询仍受店长权限限制。",
        "parameters": EmployeeListArguments.model_json_schema(),
    },
    {
        "name": "get_employee",
        "description": "根据员工ID查询详情；只能查看原接口允许查看的员工。",
        "parameters": IdArguments.model_json_schema(),
    },
    {
        "name": "list_discount_rules",
        "description": "查询折扣规则、规则ID、所属部门、启停开关和动态状态。",
        "parameters": DiscountRuleListArguments.model_json_schema(),
    },
    {
        "name": "get_discount_rule",
        "description": "根据折扣规则ID查询规则详情。",
        "parameters": IdArguments.model_json_schema(),
    },
    {
        "name": "list_discount_products",
        "description": "查询指定折扣规则当前关联的商品。",
        "parameters": DiscountProductListArguments.model_json_schema(),
    },
    {
        "name": "prepare_inventory_adjustment",
        "description": "提出修改某个库存批次剩余数量。只生成待确认操作，绝不直接修改数据库。",
        "parameters": InventoryAdjustmentArguments.model_json_schema(),
    },
    {
        "name": "prepare_discard_expired_batch",
        "description": "提出废弃一个已经过期的库存批次。只生成待确认操作，绝不直接修改数据库。",
        "parameters": DiscardBatchArguments.model_json_schema(),
    },
    {
        "name": "prepare_product_status_update",
        "description": "提出上架或停售一个商品。只生成待确认操作，绝不直接修改数据库。",
        "parameters": ProductStatusArguments.model_json_schema(),
    },
    {
        "name": "prepare_business_action",
        "description": (
            "提出其他MarketFlow数据变更，只生成待确认卡片，用户确认后才执行。"
            "action_type可选值及含义："
            + "；".join(f"{code}={name}" for code, name in ACTION_NAMES.items())
            + "。payload必须提供对应接口所需的完整参数和目标ID。常用结构："
            "修改操作包含对应的product_id、supplier_id、supplier_product_id、employee_id或"
            "discount_rule_id；状态修改再带is_active或status；添加折扣商品带product_ids；"
            "创建进货单带department_id和items；创建销售单带items；创建折扣带department_id、"
            "name、discount_type、discount_value、schedule_type及该周期所需时间。"
        ),
        "parameters": BusinessActionArguments.model_json_schema(),
    },
]


# endregion


def _validation_error(error: ValidationError) -> ToolExecutionResult:
    """把模型生成的错误参数转换成可供模型自我说明的安全结果。"""

    return ToolExecutionResult(
        data={"ok": False, "error": "工具参数不正确", "details": error.errors(include_url=False)}
    )


async def _ensure_department_write_permission(
    *,
    employee_id: int,
    department_id: int,
    db: AsyncSession,
) -> None:
    """准备修改时先做一次角色和部门检查；确认时原Service还会再次验证。"""

    employee = await get_employee_by_id(employee_id=employee_id, db=db)
    if employee is None:
        raise HTTPException(status_code=401, detail="当前登录员工不存在")
    if employee.role not in (EmployeeRole.STORE_MANAGER, EmployeeRole.REGULAR_EMPLOYEE):
        raise HTTPException(status_code=403, detail="只有店长或正式员工可以修改业务数据")
    if employee.role == EmployeeRole.REGULAR_EMPLOYEE and employee.department_id != department_id:
        raise HTTPException(status_code=403, detail="正式员工只能修改自己所属部门的数据")


async def execute_marketflow_tool(
    *,
    name: str,
    arguments: dict[str, Any],
    employee_id: int,
    provider: str,
    db: AsyncSession,
) -> ToolExecutionResult:
    """仅执行白名单工具；所有查询和修改继续复用现有 Service 权限逻辑。"""

    try:
        if name == "search_products":
            product_values = ProductSearchArguments.model_validate(arguments)
            product_response = await get_products_list_service(
                page=1,
                page_size=10,
                keyword=product_values.keyword,
                department_id=product_values.department_id,
                category_id=None,
                status=product_values.status,
                stock_consistent=None,
                low_stock=product_values.low_stock,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(
                data={"ok": True, **product_response.model_dump(mode="json")}
            )

        if name == "list_inventory_batches":
            batch_values = BatchListArguments.model_validate(arguments)
            batch_response = await get_inventory_batches_list_service(
                page=1,
                page_size=10,
                status=batch_values.status,
                supplier_id=batch_values.supplier_id,
                product_id=batch_values.product_id,
                department_id=batch_values.department_id,
                expiration_start=batch_values.expiration_start,
                expiration_end=batch_values.expiration_end,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(data={"ok": True, **batch_response.model_dump(mode="json")})

        if name == "get_inventory_batch":
            batch_id_values = IdArguments.model_validate(arguments)
            batch_detail = await get_inventory_batch_detail_service(
                batch_id=batch_id_values.id,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(data={"ok": True, **batch_detail.model_dump(mode="json")})

        if name == "list_purchases":
            purchase_values = PurchaseListArguments.model_validate(arguments)
            purchase_response = await get_purchases_list_service(
                page=1,
                page_size=10,
                purchase_no=purchase_values.purchase_no,
                department_id=purchase_values.department_id,
                ordered_at=None,
                arrived_at=None,
                purchase_status=purchase_values.status,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(
                data={"ok": True, **purchase_response.model_dump(mode="json")}
            )

        if name == "get_purchase":
            purchase_id_values = IdArguments.model_validate(arguments)
            purchase_detail = await get_purchase_detail_service(
                purchase_id=purchase_id_values.id,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(data={"ok": True, **purchase_detail.model_dump(mode="json")})

        if name == "get_sales_overview":
            overview_values = SalesOverviewArguments.model_validate(arguments)
            overview_response = await overview_service(
                db=db,
                employee_id=employee_id,
                start_time=overview_values.start_time,
                end_time=overview_values.end_time,
                department_id=overview_values.department_id,
            )
            return ToolExecutionResult(
                data={"ok": True, **overview_response.model_dump(mode="json")}
            )

        if name == "list_departments":
            departments = await get_departments_list_service(
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(
                data={
                    "ok": True,
                    "items": [item.model_dump(mode="json") for item in departments],
                }
            )

        if name == "list_categories":
            category_values = CategoryListArguments.model_validate(arguments)
            categories = await get_categories_list_service(
                department_id=category_values.department_id,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(
                data={
                    "ok": True,
                    "items": [item.model_dump(mode="json") for item in categories],
                }
            )

        if name == "list_suppliers":
            supplier_values = SupplierListArguments.model_validate(arguments)
            suppliers = await get_suppliers_list_service(
                page=1,
                page_size=20,
                is_active=supplier_values.is_active,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(data={"ok": True, **suppliers.model_dump(mode="json")})

        if name == "get_supplier":
            supplier_id_values = IdArguments.model_validate(arguments)
            supplier = await get_supplier_detail_service(
                supplier_id=supplier_id_values.id,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(data={"ok": True, **supplier.model_dump(mode="json")})

        if name == "list_supplier_products":
            catalog_values = SupplierProductListArguments.model_validate(arguments)
            catalog = await get_supplier_products_list_service(
                page=1,
                page_size=20,
                supplier_id=catalog_values.supplier_id,
                keyword=catalog_values.keyword,
                is_active=catalog_values.is_active,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(data={"ok": True, **catalog.model_dump(mode="json")})

        if name == "get_supplier_product":
            catalog_id_values = IdArguments.model_validate(arguments)
            catalog_item = await get_supplier_product_detail_service(
                supplier_product_id=catalog_id_values.id,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(data={"ok": True, **catalog_item.model_dump(mode="json")})

        if name == "list_employees":
            employee_values = EmployeeListArguments.model_validate(arguments)
            employees = await get_list_employees_service(
                page=1,
                page_size=20,
                department_id=employee_values.department_id,
                role=employee_values.role,
                is_active=employee_values.is_active,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(data={"ok": True, **employees.model_dump(mode="json")})

        if name == "get_employee":
            target_employee_values = IdArguments.model_validate(arguments)
            employee = await get_employee_detail_service(
                employee_id=target_employee_values.id,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(data={"ok": True, **employee.model_dump(mode="json")})

        if name == "list_discount_rules":
            discount_values = DiscountRuleListArguments.model_validate(arguments)
            discounts = await get_discount_rule_list_service(
                page=1,
                page_size=20,
                keyword=discount_values.keyword,
                department_id=discount_values.department_id,
                discount_type=discount_values.discount_type,
                schedule_type=discount_values.schedule_type,
                is_active=discount_values.is_active,
                computed_status=discount_values.computed_status,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(data={"ok": True, **discounts.model_dump(mode="json")})

        if name == "get_discount_rule":
            discount_id_values = IdArguments.model_validate(arguments)
            discount = await get_discount_rule_detail_service(
                discount_rule_id=discount_id_values.id,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(data={"ok": True, **discount.model_dump(mode="json")})

        if name == "list_discount_products":
            discount_product_values = DiscountProductListArguments.model_validate(arguments)
            discount_product_request = GetDiscountRuleProductsRequest(
                page=1,
                page_size=20,
                keyword=discount_product_values.keyword,
                category_id=discount_product_values.category_id,
            )
            discount_products = await get_discount_rule_products_service(
                discount_rule_id=discount_product_values.discount_rule_id,
                request=discount_product_request,
                current_employee_id=employee_id,
                db=db,
            )
            return ToolExecutionResult(
                data={"ok": True, **discount_products.model_dump(mode="json")}
            )

        if name == "prepare_inventory_adjustment":
            adjustment_values = InventoryAdjustmentArguments.model_validate(arguments)
            batch = await get_inventory_batch_detail_service(
                batch_id=adjustment_values.batch_id,
                current_employee_id=employee_id,
                db=db,
            )
            await _ensure_department_write_permission(
                employee_id=employee_id,
                department_id=batch.department_id,
                db=db,
            )
            if adjustment_values.remaining_quantity > batch.initial_quantity:
                raise HTTPException(
                    status_code=400,
                    detail="批次剩余数量不能超过到货初始数量",
                )
            summary = (
                f"将批次 {batch.batch_no}（{batch.product_name}）的剩余库存从 "
                f"{batch.remaining_quantity} 件修改为 {adjustment_values.remaining_quantity} 件"
            )
            action_arguments = adjustment_values.model_dump(mode="json")
            action = await create_ai_pending_action(
                employee_id=employee_id,
                provider=provider,
                action_type="update_inventory_batch_quantity",
                arguments=action_arguments,
                summary=summary,
                expires_at=datetime.now() + timedelta(minutes=AI_ACTION_EXPIRY_MINUTES),
                db=db,
            )
            return ToolExecutionResult(
                data={
                    "ok": True,
                    "requires_confirmation": True,
                    "action_id": action.id,
                    "summary": summary,
                    "expires_at": action.expires_at.isoformat(),
                },
                pending_action=action,
            )

        if name == "prepare_discard_expired_batch":
            discard_values = DiscardBatchArguments.model_validate(arguments)
            batch = await get_inventory_batch_detail_service(
                batch_id=discard_values.batch_id,
                current_employee_id=employee_id,
                db=db,
            )
            await _ensure_department_write_permission(
                employee_id=employee_id,
                department_id=batch.department_id,
                db=db,
            )
            if batch.expiration_date is None or batch.expiration_date >= date.today():
                raise HTTPException(status_code=400, detail="只有已经过期的库存批次可以废弃")
            if batch.remaining_quantity == 0:
                raise HTTPException(status_code=400, detail="该过期批次已经没有剩余库存")
            summary = (
                f"废弃批次 {batch.batch_no}（{batch.product_name}）当前剩余的 "
                f"{batch.remaining_quantity} 件过期库存"
            )
            action_arguments = discard_values.model_dump(mode="json")
            action = await create_ai_pending_action(
                employee_id=employee_id,
                provider=provider,
                action_type="discard_expired_inventory_batch",
                arguments=action_arguments,
                summary=summary,
                expires_at=datetime.now() + timedelta(minutes=AI_ACTION_EXPIRY_MINUTES),
                db=db,
            )
            return ToolExecutionResult(
                data={
                    "ok": True,
                    "requires_confirmation": True,
                    "action_id": action.id,
                    "summary": summary,
                    "expires_at": action.expires_at.isoformat(),
                },
                pending_action=action,
            )

        if name == "prepare_product_status_update":
            status_values = ProductStatusArguments.model_validate(arguments)
            product = await get_product_detail_service(
                product_id=status_values.product_id,
                current_employee_id=employee_id,
                db=db,
            )
            await _ensure_department_write_permission(
                employee_id=employee_id,
                department_id=product.department.id,
                db=db,
            )
            status_name = "上架" if status_values.status == ProductStatus.ON_SALE else "停售"
            summary = f"将商品 {product.product_no}（{product.name}）修改为{status_name}状态"
            action_arguments = status_values.model_dump(mode="json")
            action = await create_ai_pending_action(
                employee_id=employee_id,
                provider=provider,
                action_type="update_product_status",
                arguments=action_arguments,
                summary=summary,
                expires_at=datetime.now() + timedelta(minutes=AI_ACTION_EXPIRY_MINUTES),
                db=db,
            )
            return ToolExecutionResult(
                data={
                    "ok": True,
                    "requires_confirmation": True,
                    "action_id": action.id,
                    "summary": summary,
                    "expires_at": action.expires_at.isoformat(),
                },
                pending_action=action,
            )
        if name == "prepare_business_action":
            business_values = BusinessActionArguments.model_validate(arguments)
            action_arguments = validate_business_action(
                business_values.action_type,
                business_values.payload,
            )
            summary = build_business_action_summary(
                business_values.action_type,
                action_arguments,
            )
            action = await create_ai_pending_action(
                employee_id=employee_id,
                provider=provider,
                action_type=business_values.action_type,
                arguments=action_arguments,
                summary=summary,
                expires_at=datetime.now() + timedelta(minutes=AI_ACTION_EXPIRY_MINUTES),
                db=db,
            )
            return ToolExecutionResult(
                data={
                    "ok": True,
                    "requires_confirmation": True,
                    "action_id": action.id,
                    "summary": summary,
                    "expires_at": action.expires_at.isoformat(),
                },
                pending_action=action,
            )
    except ValidationError as error:
        return _validation_error(error)
    except ValueError as error:
        return ToolExecutionResult(data={"ok": False, "error": str(error)})
    except HTTPException as error:
        return ToolExecutionResult(data={"ok": False, "error": str(error.detail)})

    return ToolExecutionResult(data={"ok": False, "error": "模型请求了未开放的工具"})


WRITE_TOOL_NAMES = {
    "prepare_inventory_adjustment",
    "prepare_discard_expired_batch",
    "prepare_business_action",
    "prepare_product_status_update",
}

__all__ = [
    "MARKETFLOW_TOOL_DEFINITIONS",
    "ToolExecutionResult",
    "WRITE_TOOL_NAMES",
    "execute_marketflow_tool",
]
