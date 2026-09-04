"""第一版业务模型使用的受限字符串枚举。"""

from enum import StrEnum


class EmployeeRole(StrEnum):
    """员工账号角色。"""

    STORE_MANAGER = "店长"  # 管理门店并维护员工账号。
    REGULAR_EMPLOYEE = "正式员工"  # 绑定部门的正式雇员。
    CONTRACT_WORKER = "契约工"  # 绑定部门的契约雇员。


class ProductStatus(StrEnum):
    """商品的人工销售状态；缺货状态由库存数量动态计算。"""

    ON_SALE = "on_sale"  # 商品正常销售。
    STOPPED = "stopped"  # 商品人工停止销售。


class SaleSource(StrEnum):
    """销售原始数据来源。"""

    DEMO_SEED = "demo_seed"  # 系统初始化生成的演示销售数据。


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


__all__ = [
    "EmployeeRole",
    "ProductStatus",
    "RankingGroupBy",
    "RankingSortBy",
    "RankingSortOrder",
    "SaleSource",
]
