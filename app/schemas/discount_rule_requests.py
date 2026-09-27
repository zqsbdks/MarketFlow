"""折扣规则与适用范围请求模型。"""

from datetime import datetime, time
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DiscountComputedStatus, DiscountScheduleType, DiscountType


# region 获取折扣规则列表请求模型
class GetDiscountRuleListRequest(BaseModel):
    """获取折扣规则列表请求模型。"""

    # page表示前端准备查询第几页；最小值为1，不允许出现第0页或负数页码。
    page: int = Field(1, ge=1, description="当前页码")

    # page_size表示一页最多返回多少条规则；限制为100可以避免一次查询数据过多。
    page_size: int = Field(10, ge=1, le=100, description="每页数量")

    # keyword用于对折扣规则名称进行模糊查询；不传时不限制规则名称。
    keyword: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        description="折扣规则名称关键字",
    )

    # discount_type用于只查询某一种计价方式，例如percentage表示按比例打折。
    discount_type: DiscountType | None = Field(None, description="折扣计算方式")

    # schedule_type用于区分单次活动、每日循环活动和每周循环活动。
    schedule_type: DiscountScheduleType | None = Field(None, description="折扣执行周期")

    # is_active是人工启停开关；True表示已启用，False表示已经人工停止。
    is_active: bool | None = Field(None, description="是否启用")

    # computed_status不是数据库字段，而是后端根据人工开关和当前时间动态计算的状态。
    computed_status: DiscountComputedStatus | None = Field(None, description="动态计算状态")

    # 自动删除关键字两端的空格，例如“ 晚间折扣 ”会被处理成“晚间折扣”。
    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


# region 创建折扣规则请求模型
class CreateDiscountRuleRequest(BaseModel):
    """创建一条折扣规则时提交的完整规则配置。"""

    # 名称用于前端识别规则，并由Service检查是否与现有规则重名。
    name: str = Field(..., min_length=1, max_length=100, description="折扣规则名称")

    # discount_type决定discount_value代表比例、立减金额还是固定成交价。
    discount_type: DiscountType = Field(..., description="折扣计算方式")
    discount_value: Decimal = Field(
        ...,
        gt=0,
        max_digits=12,
        decimal_places=4,
        description="折扣比例、立减金额或固定价格",
    )

    # schedule_type决定后续应填写单次日期时间，还是每日循环时间。
    schedule_type: DiscountScheduleType = Field(..., description="折扣执行周期")

    # 单次活动填写完整日期时间；每日和每周循环活动不使用这两个字段。
    starts_at: datetime | None = Field(None, description="单次活动开始时间")
    ends_at: datetime | None = Field(None, description="单次活动结束时间")

    # 每日和每周活动填写每天的执行时段；当前版本不支持跨越午夜的时间段。
    daily_start_time: time | None = Field(None, description="每日循环开始时间")
    daily_end_time: time | None = Field(None, description="每日循环结束时间")

    # 每周活动使用1至7表示周一至周日；单次和每日活动不使用该字段。
    weekdays: list[int] | None = Field(None, description="每周执行日；1至7表示周一至周日")

    # 默认创建后立即开启；尚未添加适用商品时，规则不会作用于任何商品。
    is_active: bool = Field(True, description="创建后是否启用")

    # 自动去除规则名称首尾空格，避免仅因空格不同而创建重复名称。
    model_config = ConfigDict(str_strip_whitespace=True)


# endregion


# region 添加折扣商品请求模型
class AddDiscountRuleProductsRequest(BaseModel):
    """向一条现有折扣规则批量添加正式商品。"""

    # 至少选择一个商品；每个商品ID必须是大于0的数据库主键。
    product_ids: list[Annotated[int, Field(ge=1)]] = Field(
        ...,
        min_length=1,
        description="需要加入折扣规则的正式商品ID列表",
    )


# endregion


# region 后续折扣规则请求模型
# 后续添加：启停和资料修改请求模型。
# endregion


# region 折扣适用范围请求模型
# 后续添加：批量添加适用商品、分类或部门的请求模型。
# endregion

__all__ = [
    "AddDiscountRuleProductsRequest",
    "CreateDiscountRuleRequest",
    "GetDiscountRuleListRequest",
]
