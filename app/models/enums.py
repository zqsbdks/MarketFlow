"""第一版业务模型使用的受限字符串枚举。"""

from enum import StrEnum


class EmployeeRole(StrEnum):
    """员工账号角色。"""

    STORE_MANAGER = "店长"  # 管理门店并维护员工账号。
    REGULAR_EMPLOYEE = "正式员工"  # 绑定部门的正式雇员。
    CONTRACT_WORKER = "契约工"  # 绑定部门的契约雇员。


class EmployeeGender(StrEnum):
    """员工登记的性别。"""

    MALE = "男"
    FEMALE = "女"
    UNSPECIFIED = "未填写"


class EmploymentStatus(StrEnum):
    """员工与门店之间的雇佣状态。"""

    EMPLOYED = "在职"
    ON_LEAVE = "休假"
    RESIGNED = "离职"
    DISMISSED = "解雇"


class ProductStatus(StrEnum):
    """商品的人工销售状态；缺货状态由库存数量动态计算。"""

    ON_SALE = "on_sale"  # 商品正常销售。
    STOPPED = "stopped"  # 商品人工停止销售。


class SaleSource(StrEnum):
    """销售原始数据来源。"""

    DEMO_SEED = "demo_seed"  # 系统初始化生成的演示销售数据。


class PurchaseStatus(StrEnum):
    """进货单从下单到入库的处理状态。"""

    PENDING = "pending"  # 已经下单，但尚未达到预计到货时间。
    ARRIVED = "arrived"  # 已经由系统自动签收并完成库存入库。


class InventoryBatchStatus(StrEnum):
    """库存批次的人工处理状态；是否过期根据到期日期动态判断。"""

    AVAILABLE = "available"  # 批次仍有库存并且没有被人工报废。
    SOLD_OUT = "sold_out"  # 批次的剩余数量已经变为0。
    DISCARDED = "discarded"  # 批次因损坏等原因被人工报废。


class RankingGroupBy(StrEnum):
    """销售排行的汇总方式。"""

    PRODUCT = "product"  # 将相同商品的销售明细合并。
    CATEGORY = "category"  # 将同一商品分类的销售明细合并。


class RankingSortBy(StrEnum):
    """销售排行的排序指标。"""

    QUANTITY = "quantity"  # 按累计销售数量排序。
    AMOUNT = "amount"  # 按累计销售金额排序。


class RankingSortOrder(StrEnum):
    """销售排行的排序方向。"""

    ASC = "asc"  # 从小到大排列。
    DESC = "desc"  # 从大到小排列。


class ReportMetric(StrEnum):
    """营业分析接口支持按需返回的指标。"""

    REVENUE = "revenue"  # 营业额。
    SALES_COST = "sales_cost"  # 销售成本。
    GROSS_PROFIT = "gross_profit"  # 毛利润。
    SALES_QUANTITY = "sales_quantity"  # 销售商品数量。
    SALE_COUNT = "sale_count"  # 销售单数量。
    AVERAGE_SALE_AMOUNT = "average_sale_amount"  # 平均每单金额。
    AVERAGE_SALE_QUANTITY = "average_sale_quantity"  # 平均每单件数。
    GROSS_PROFIT_MARGIN = "gross_profit_margin"  # 毛利率。
    REVENUE_GROWTH_RATE = "revenue_growth_rate"  # 营业额增长率。
    GROSS_PROFIT_GROWTH_RATE = "gross_profit_growth_rate"  # 毛利润增长率。
    DEPARTMENT_REVENUE_SHARE = "department_revenue_share"  # 部门销售额占比。
    SALES_TREND = "sales_trend"  # 按小时、日、月或年的营业数据。


__all__ = [
    "EmployeeGender",
    "EmployeeRole",
    "EmploymentStatus",
    "InventoryBatchStatus",
    "ProductStatus",
    "PurchaseStatus",
    "RankingGroupBy",
    "RankingSortBy",
    "RankingSortOrder",
    "ReportMetric",
    "SaleSource",
]
