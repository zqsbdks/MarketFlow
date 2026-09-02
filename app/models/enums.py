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


__all__ = ["EmployeeRole", "ProductStatus", "SaleSource"]
