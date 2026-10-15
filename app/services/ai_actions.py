"""AI 待确认操作的确认、取消与安全执行业务逻辑。"""

from typing import Any

from fastapi import HTTPException, Request
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_now
from app.core.cache import (
    CATEGORIES_CACHE_NAMESPACE,
    DEPARTMENTS_CACHE_NAMESPACE,
    SUPPLIER_PRODUCTS_CACHE_NAMESPACE,
    SUPPLIERS_CACHE_NAMESPACE,
    clear_cache_namespaces,
)
from app.crud import ai_actions as data_access
from app.crud.ai_pending_actions import get_ai_pending_action_by_id
from app.crud.auth import get_employee_by_id
from app.crud.operation_audit_logs import create_operation_audit_log
from app.crud.stores import first_active_store_id, get_store_by_id
from app.models.ai_pending_action import AiPendingAction
from app.models.enums import EmployeeRole
from app.schemas.ai_chat_responses import (
    AiActionExecutionResponse,
    AiPendingActionResponse,
)
from app.schemas.discount_rule_requests import (
    AddDiscountRuleProductsRequest,
    CreateDiscountRuleRequest,
    UpdateDiscountRuleRequest,
    UpdateDiscountRuleStatusRequest,
)
from app.schemas.employees_requests import EmployeeDetailUpdateRequest, EmployeesCreateRequest
from app.schemas.inventory_batches_requests import (
    InventoryBatchDiscardRequest,
    InventoryBatchQuantityUpdateRequest,
)
from app.schemas.products_requests import ProductStatusUpdateRequest, UpdateProductRequest
from app.schemas.sales_requests import CreateSaleRequest
from app.schemas.supplier_products_requests import (
    SupplierProductCreateRequest,
    SupplierProductUpdateRequest,
)
from app.schemas.suppliers_requests import SuppliersCreateRequest, SuppliersUpdateRequest
from app.services.discount_rule import (
    add_discount_rule_products_service,
    clear_discount_rules_service,
    create_discount_rule_service,
    delete_all_discount_rule_products_service,
    delete_discount_rule_product_service,
    delete_discount_rule_service,
    update_discount_rule_service,
    update_discount_rule_status_service,
)
from app.services.employees import (
    create_employee_service,
    update_employee_detail_service,
    update_employee_status_service,
)
from app.services.inventory_batches import (
    discard_expired_inventory_batch_service,
    update_inventory_batch_quantity_service,
)
from app.services.products import update_product_service, update_product_status_service
from app.services.sales import create_sale_service
from app.services.supplier_products import (
    create_supplier_product_service,
    update_supplier_product_service,
    update_supplier_product_status_service,
)
from app.services.suppliers import (
    create_supplier_service,
    update_supplier_service,
    update_supplier_status_service,
)


def _action_response(action: AiPendingAction) -> AiPendingActionResponse:
    """将 ORM 记录转换成不包含员工ID等内部字段的响应。"""

    return AiPendingActionResponse.model_validate(action)


def _validate_pending_action(action: AiPendingAction, employee_id: int) -> None:
    """确认操作属于当前员工、仍在等待确认并且没有过期。"""

    if action.employee_id != employee_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="不能处理其他员工发起的AI操作",
        )
    if action.status != "pending":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"该AI操作当前状态为{action.status}，不能重复处理",
        )


# region 确认AI操作
async def confirm_ai_action_service(
    *, action_id: int, employee_id: int, db: AsyncSession, http_request: Request | None = None
) -> AiActionExecutionResponse:
    """锁定待确认记录、复用现有业务Service再次鉴权并执行修改。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            raise HTTPException(403, "此接口不支持全公司汇总")
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and raw_store_id != "all":
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")

        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=True,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    action = await get_ai_pending_action_by_id(action_id=action_id, db=db, for_update=True)
    if action is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="AI操作不存在")
    _validate_pending_action(action, employee_id)

    employee = await data_access.get_action_employee(db=db, employee_id=employee_id)
    if (
        employee is None
        or employee.role == EmployeeRole.HEADQUARTERS
        or action.store_id != employee.store_id
        or db.info.get("read_store_id") != employee.store_id
    ):
        raise HTTPException(403, "门店已切换或员工已异动，请在所属门店重新发起操作")

    if action.expires_at <= business_now():
        action.status = "expired"
        await db.commit()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="该AI操作已经过期，请重新发起",
        )

    # 持有 FOR UPDATE 行锁，直至业务修改、审计与状态一起提交。
    action.status = "processing"
    db.info["defer_commit"] = True

    result: dict[str, Any]
    try:
        if action.action_type == "update_inventory_batch_quantity":
            quantity_request = InventoryBatchQuantityUpdateRequest.model_validate(action.arguments)
            batch_id = int(action.arguments["batch_id"])
            batch = await update_inventory_batch_quantity_service(
                batch_id=batch_id,
                request=quantity_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = batch.model_dump(mode="json")
        elif action.action_type == "discard_expired_inventory_batch":
            discard_request = InventoryBatchDiscardRequest.model_validate(action.arguments)
            batch_id = int(action.arguments["batch_id"])
            batch = await discard_expired_inventory_batch_service(
                batch_id=batch_id,
                request=discard_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = batch.model_dump(mode="json")
        elif action.action_type == "update_product_status":
            product_status_request = ProductStatusUpdateRequest.model_validate(action.arguments)
            product_id = int(action.arguments["product_id"])
            product = await update_product_status_service(
                product_id=product_id,
                request=product_status_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = product.model_dump(mode="json")
        elif action.action_type == "update_product_details":
            product_details_request = UpdateProductRequest.model_validate(action.arguments)
            updated_product = await update_product_service(
                product_id=int(action.arguments["product_id"]),
                request=product_details_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = updated_product.model_dump(mode="json")
        elif action.action_type == "create_supplier":
            supplier_create_request = SuppliersCreateRequest.model_validate(action.arguments)
            created_supplier = await create_supplier_service(
                request=supplier_create_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = created_supplier.model_dump(mode="json")
        elif action.action_type == "update_supplier":
            supplier_update_request = SuppliersUpdateRequest.model_validate(action.arguments)
            updated_supplier = await update_supplier_service(
                supplier_id=int(action.arguments["supplier_id"]),
                request=supplier_update_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = updated_supplier.model_dump(mode="json")
        elif action.action_type == "update_supplier_status":
            status_updated_supplier = await update_supplier_status_service(
                supplier_id=int(action.arguments["supplier_id"]),
                is_active=bool(action.arguments["is_active"]),
                reason=action.arguments.get("reason"),
                current_employee_id=employee_id,
                db=db,
            )
            result = status_updated_supplier.model_dump(mode="json")
        elif action.action_type == "create_supplier_product":
            supplier_product_create_request = SupplierProductCreateRequest.model_validate(
                action.arguments
            )
            created_supplier_product = await create_supplier_product_service(
                request=supplier_product_create_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = created_supplier_product.model_dump(mode="json")
        elif action.action_type == "update_supplier_product":
            supplier_product_update_request = SupplierProductUpdateRequest.model_validate(
                action.arguments
            )
            updated_supplier_product = await update_supplier_product_service(
                supplier_product_id=int(action.arguments["supplier_product_id"]),
                request=supplier_product_update_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = updated_supplier_product.model_dump(mode="json")
        elif action.action_type == "update_supplier_product_status":
            status_updated_supplier_product = await update_supplier_product_status_service(
                supplier_product_id=int(action.arguments["supplier_product_id"]),
                is_active=bool(action.arguments["is_active"]),
                reason=action.arguments.get("reason"),
                current_employee_id=employee_id,
                db=db,
            )
            result = status_updated_supplier_product.model_dump(mode="json")
        elif action.action_type == "create_purchase":
            raise HTTPException(409, "请保存订货计划，进货单将在截止时间自动生成")
        elif action.action_type == "create_sale":
            sale_request = CreateSaleRequest.model_validate(action.arguments)
            sale = await create_sale_service(
                request=sale_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = sale.model_dump(mode="json")
        elif action.action_type == "create_employee":
            employee_create_request = EmployeesCreateRequest.model_validate(action.arguments)
            created_employee = await create_employee_service(
                name=employee_create_request.name,
                role=employee_create_request.role,
                department_id=employee_create_request.department_id,
                current_employee_id=employee_id,
                db=db,
            )
            result = created_employee.model_dump(mode="json")
        elif action.action_type == "update_employee_status":
            status_updated_employee = await update_employee_status_service(
                employee_id=int(action.arguments["employee_id"]),
                is_active=bool(action.arguments["is_active"]),
                reason=action.arguments.get("reason"),
                current_employee_id=employee_id,
                db=db,
            )
            result = status_updated_employee.model_dump(mode="json")
        elif action.action_type == "update_employee_details":
            employee_details_request = EmployeeDetailUpdateRequest.model_validate(action.arguments)
            updated_employee = await update_employee_detail_service(
                employee_id=int(action.arguments["employee_id"]),
                request=employee_details_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = updated_employee.model_dump(mode="json")
        elif action.action_type == "create_discount_rule":
            discount_create_request = CreateDiscountRuleRequest.model_validate(action.arguments)
            created_discount = await create_discount_rule_service(
                request=discount_create_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = created_discount.model_dump(mode="json")
        elif action.action_type == "add_discount_products":
            discount_products_request = AddDiscountRuleProductsRequest.model_validate(
                action.arguments
            )
            added_discount_products = await add_discount_rule_products_service(
                discount_rule_id=int(action.arguments["discount_rule_id"]),
                request=discount_products_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = added_discount_products.model_dump(mode="json")
        elif action.action_type == "remove_discount_product":
            removed_discount_product = await delete_discount_rule_product_service(
                discount_rule_id=int(action.arguments["discount_rule_id"]),
                product_id=int(action.arguments["product_id"]),
                current_employee_id=employee_id,
                db=db,
            )
            result = removed_discount_product.model_dump(mode="json")
        elif action.action_type == "clear_discount_products":
            cleared_discount_products = await delete_all_discount_rule_products_service(
                discount_rule_id=int(action.arguments["discount_rule_id"]),
                current_employee_id=employee_id,
                db=db,
            )
            result = cleared_discount_products.model_dump(mode="json")
        elif action.action_type == "update_discount_rule":
            discount_update_request = UpdateDiscountRuleRequest.model_validate(action.arguments)
            updated_discount = await update_discount_rule_service(
                discount_rule_id=int(action.arguments["discount_rule_id"]),
                request=discount_update_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = updated_discount.model_dump(mode="json")
        elif action.action_type == "update_discount_status":
            discount_status_request = UpdateDiscountRuleStatusRequest.model_validate(
                action.arguments
            )
            status_updated_discount = await update_discount_rule_status_service(
                discount_rule_id=int(action.arguments["discount_rule_id"]),
                request=discount_status_request,
                current_employee_id=employee_id,
                db=db,
            )
            result = status_updated_discount.model_dump(mode="json")
        elif action.action_type == "delete_discount_rule":
            deleted_discount = await delete_discount_rule_service(
                discount_rule_id=int(action.arguments["discount_rule_id"]),
                current_employee_id=employee_id,
                db=db,
            )
            result = deleted_discount.model_dump(mode="json")
        elif action.action_type == "clear_discount_rules":
            discounts = await clear_discount_rules_service(
                current_employee_id=employee_id,
                db=db,
            )
            result = discounts.model_dump(mode="json")
        else:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="该AI操作类型未开放执行权限",
            )
    except Exception as error:
        db.info.pop("defer_commit", None)
        await db.rollback()
        failed_action = await get_ai_pending_action_by_id(
            action_id=action_id,
            db=db,
            for_update=True,
        )
        if failed_action is not None:
            failed_action.status = "failed"
            if isinstance(error, HTTPException):
                failed_action.failure_reason = str(error.detail)[:255]
            else:
                failed_action.failure_reason = "执行失败，请查看服务日志"
            await db.commit()
        raise

    try:
        action.status = "executed"
        action.executed_at = business_now()
        action.failure_reason = None
        await create_operation_audit_log(
            employee_id=employee_id,
            module="ai_assistant",
            action="confirm_action",
            target_type="ai_pending_action",
            target_id=action.id,
            before_data={"status": "processing"},
            after_data={"status": "executed", "action_type": action.action_type},
            reason="员工确认执行AI建议",
            db=db,
        )
        db.info.pop("defer_commit", None)
        await db.commit()
    except Exception:
        db.info.pop("defer_commit", None)
        await db.rollback()
        raise
    # Service 曾在中途清缓存；提交后再清一次，避免并发读回填旧值。
    await clear_cache_namespaces(
        CATEGORIES_CACHE_NAMESPACE,
        DEPARTMENTS_CACHE_NAMESPACE,
        SUPPLIERS_CACHE_NAMESPACE,
        SUPPLIER_PRODUCTS_CACHE_NAMESPACE,
    )
    return AiActionExecutionResponse(action=_action_response(action), result=result)


# endregion


# region 取消AI操作
async def cancel_ai_action_service(
    *, action_id: int, employee_id: int, db: AsyncSession, http_request: Request | None = None
) -> AiActionExecutionResponse:
    """取消本人仍在等待确认的操作，不执行任何业务数据修改。"""

    # 本接口在服务层明确检查店铺范围；不依赖数据库自动事件。
    if http_request is not None:
        access_employee = await get_employee_by_id(employee_id=employee_id, db=db)
        if access_employee is None or not access_employee.is_active:
            raise HTTPException(401, "账号不存在或已停用")
        is_headquarters = access_employee.role == EmployeeRole.HEADQUARTERS
        selected_store_id = access_employee.store_id
        raw_store_id = http_request.headers.get("X-Store-ID")
        if not raw_store_id:
            raw_store_id = http_request.query_params.get("store_id")
        if raw_store_id == "all":
            raise HTTPException(403, "此接口不支持全公司汇总")
        elif raw_store_id:
            try:
                selected_store_id = int(raw_store_id)
            except ValueError as error:
                raise HTTPException(422, "门店ID无效") from error
            if selected_store_id <= 0:
                raise HTTPException(422, "门店ID无效")
        if selected_store_id is None and is_headquarters and raw_store_id != "all":
            selected_store_id = await first_active_store_id(db)
        if selected_store_id is not None:
            selected_store = await get_store_by_id(selected_store_id, db)
            if selected_store is None or not selected_store.is_active:
                raise HTTPException(403, "门店不存在或已停用")
        if not is_headquarters and access_employee.store_id is None:
            raise HTTPException(403, "员工尚未分配门店")

        # 这里只记录本次查询参数；CRUD 会明确读取并添加 store_id 条件。
        db.info.update(
            actor_id=access_employee.id,
            actor_role=access_employee.role,
            own_store_id=access_employee.store_id,
            read_store_id=selected_store_id,
            write_store_id=access_employee.store_id,
            company_management=False,
            company_catalog_read=False,
            private_employee_path=True,
            store_context=True,
        )
        http_request.state.store_id = selected_store_id
        http_request.state.employee_id = access_employee.id
        http_request.state.own_store_id = access_employee.store_id

    action = await get_ai_pending_action_by_id(action_id=action_id, db=db, for_update=True)
    if action is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="AI操作不存在")
    _validate_pending_action(action, employee_id)
    action.status = "cancelled"
    await create_operation_audit_log(
        employee_id=employee_id,
        module="ai_assistant",
        action="cancel_action",
        target_type="ai_pending_action",
        target_id=action.id,
        before_data={"status": "pending"},
        after_data={"status": "cancelled", "action_type": action.action_type},
        reason="员工取消AI建议",
        db=db,
    )
    await db.commit()
    return AiActionExecutionResponse(action=_action_response(action), result=None)


# endregion

__all__ = ["cancel_ai_action_service", "confirm_ai_action_service"]
