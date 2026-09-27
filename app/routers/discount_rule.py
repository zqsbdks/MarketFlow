"""折扣规则与适用范围 API 路由。"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.discount_rule_requests import (
    AddDiscountRuleProductsRequest,
    CreateDiscountRuleRequest,
    GetDiscountRuleListRequest,
    GetDiscountRuleProductsRequest,
)
from app.schemas.discount_rule_responses import (
    AddDiscountRuleProductsResponse,
    DeleteDiscountRuleProductsResponse,
    DiscountRuleListItemResponse,
    DiscountRuleListResponse,
    DiscountRuleProductListResponse,
)
from app.services.discount_rule import (
    add_discount_rule_products_service,
    create_discount_rule_service,
    delete_all_discount_rule_products_service,
    delete_discount_rule_product_service,
    get_discount_rule_detail_service,
    get_discount_rule_list_service,
    get_discount_rule_products_service,
)

# 本模块内的接口都会以 /api/v1/discount-rules 开头。
discount_rules_router = APIRouter(
    prefix="/discount-rules",
    tags=["discount-rules"],
)


# region 获取折扣规则列表
@discount_rules_router.get(
    "/list",
    response_model=ResponseModel[DiscountRuleListResponse],
    summary="获取折扣规则列表",
    description="分页查询折扣规则，并支持按名称、折扣方式、执行周期和当前状态筛选。",
)
async def get_discount_rule_list(
    # Depends()让FastAPI从URL查询参数中组装并校验请求模型。
    request: GetDiscountRuleListRequest = Depends(),
    # 访问令牌解析出的员工ID用于检查当前登录账号是否仍然可用。
    current_employee_id: int = Depends(get_current_employee_id),
    # 每次请求获取独立的异步数据库会话，响应结束后由依赖统一关闭。
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[DiscountRuleListResponse]:
    """接收列表筛选条件，并返回统一响应格式的折扣规则分页列表。"""

    rules = await get_discount_rule_list_service(
        page=request.page,
        page_size=request.page_size,
        keyword=request.keyword,
        department_id=request.department_id,
        discount_type=request.discount_type,
        schedule_type=request.schedule_type,
        is_active=request.is_active,
        computed_status=request.computed_status,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[DiscountRuleListResponse](
        message="获取折扣规则列表成功",
        data=rules,
    )


# endregion


# region 创建折扣规则
@discount_rules_router.post(
    "",
    response_model=ResponseModel[DiscountRuleListItemResponse],
    summary="创建折扣规则",
    description="创建并保存折扣配置；适用商品通过添加折扣商品接口另行设置。",
)
async def create_discount_rule(
    request: CreateDiscountRuleRequest,
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[DiscountRuleListItemResponse]:
    """接收折扣配置，并返回创建成功后的完整规则资料。"""

    rule = await create_discount_rule_service(
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[DiscountRuleListItemResponse](
        message="创建折扣规则成功",
        data=rule,
    )


# endregion


# region 添加折扣商品
@discount_rules_router.post(
    "/{discount_rule_id}/products",
    response_model=ResponseModel[AddDiscountRuleProductsResponse],
    summary="添加折扣商品",
    description="店长可以添加任意部门商品，正式员工只能添加自己所属部门的商品。",
)
async def add_discount_rule_products(
    request: AddDiscountRuleProductsRequest,
    discount_rule_id: int = Path(..., ge=1, description="折扣规则ID"),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[AddDiscountRuleProductsResponse]:
    """接收折扣规则ID和商品ID列表，批量建立规则与商品的关联。"""

    result = await add_discount_rule_products_service(
        discount_rule_id=discount_rule_id,
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[AddDiscountRuleProductsResponse](
        message="添加折扣商品成功",
        data=result,
    )


# endregion


# region 获取折扣商品列表
@discount_rules_router.get(
    "/{discount_rule_id}/products",
    response_model=ResponseModel[DiscountRuleProductListResponse],
    summary="获取折扣商品列表",
    description="分页查询指定折扣规则关联的商品，并返回原价和计算后的折后价。",
)
async def get_discount_rule_products(
    discount_rule_id: int = Path(..., ge=1, description="折扣规则ID"),
    request: GetDiscountRuleProductsRequest = Depends(),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[DiscountRuleProductListResponse]:
    """接收规则ID与筛选条件，返回统一响应格式的分页折扣商品列表。"""

    products = await get_discount_rule_products_service(
        discount_rule_id=discount_rule_id,
        request=request,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[DiscountRuleProductListResponse](
        message="获取折扣商品列表成功",
        data=products,
    )


# endregion


# region 删除单个折扣商品
@discount_rules_router.delete(
    "/{discount_rule_id}/products/{product_id}",
    response_model=ResponseModel[DeleteDiscountRuleProductsResponse],
    summary="删除单个折扣商品",
    description="只删除折扣规则与指定商品的关联，不删除商品或折扣规则。",
)
async def delete_discount_rule_product(
    discount_rule_id: int = Path(..., ge=1, description="折扣规则ID"),
    product_id: int = Path(..., ge=1, description="需要移出折扣规则的商品ID"),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[DeleteDiscountRuleProductsResponse]:
    """接收规则ID和商品ID，删除一条折扣商品关联。"""

    result = await delete_discount_rule_product_service(
        discount_rule_id=discount_rule_id,
        product_id=product_id,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[DeleteDiscountRuleProductsResponse](
        message="删除折扣商品成功",
        data=result,
    )


# endregion


# region 删除全部折扣商品
@discount_rules_router.delete(
    "/{discount_rule_id}/products",
    response_model=ResponseModel[DeleteDiscountRuleProductsResponse],
    summary="删除全部折扣商品",
    description="店长删除规则下全部商品；正式员工只删除自己所属部门的商品。",
)
async def delete_all_discount_rule_products(
    discount_rule_id: int = Path(..., ge=1, description="折扣规则ID"),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[DeleteDiscountRuleProductsResponse]:
    """接收规则ID，删除当前员工权限范围内的全部折扣商品。"""

    result = await delete_all_discount_rule_products_service(
        discount_rule_id=discount_rule_id,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[DeleteDiscountRuleProductsResponse](
        message="删除全部折扣商品成功",
        data=result,
    )


# endregion


# region 获取折扣规则详情
@discount_rules_router.get(
    "/{discount_rule_id}",
    response_model=ResponseModel[DiscountRuleListItemResponse],
    summary="获取折扣规则详情",
    description="根据折扣规则ID获取完整规则资料、创建员工和当前动态状态。",
)
async def get_discount_rule_detail(
    discount_rule_id: int = Path(..., ge=1, description="折扣规则ID"),
    current_employee_id: int = Depends(get_current_employee_id),
    db: AsyncSession = Depends(get_db),
) -> ResponseModel[DiscountRuleListItemResponse]:
    """接收折扣规则ID，并返回统一响应格式的折扣规则详情。"""

    rule = await get_discount_rule_detail_service(
        discount_rule_id=discount_rule_id,
        current_employee_id=current_employee_id,
        db=db,
    )
    return ResponseModel[DiscountRuleListItemResponse](
        message="获取折扣规则详情成功",
        data=rule,
    )


# endregion


# region 其他折扣规则接口
# 后续添加：启停、修改和删除接口。
# endregion


# region 折扣适用范围接口
# 后续添加：分类或部门类型的适用范围接口。
# endregion


__all__ = ["discount_rules_router"]
