"""折扣规则与适用范围 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_employee_id
from app.dependencies.db import get_db
from app.schemas.base import ResponseModel
from app.schemas.discount_rule_requests import GetDiscountRuleListRequest
from app.schemas.discount_rule_responses import DiscountRuleListResponse
from app.services.discount_rule import get_discount_rule_list_service

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


# region 其他折扣规则接口
# 后续添加：详情、创建、启停、修改和删除接口。
# endregion


# region 折扣适用范围接口
# 后续添加：适用范围列表、添加和删除接口。
# endregion


__all__ = ["discount_rules_router"]
