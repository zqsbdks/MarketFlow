"""折扣规则与适用范围请求模型。"""

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DiscountComputedStatus, DiscountScheduleType, DiscountType


# region 折扣规则请求模型
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


# 后续添加：创建、启停和资料修改请求模型。
# endregion


# region 折扣适用范围请求模型
# 后续添加：批量添加适用商品、分类或部门的请求模型。
# endregion

__all__ = ["GetDiscountRuleListRequest"]
