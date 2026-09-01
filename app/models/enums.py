"""第一版业务模型使用的受限字符串枚举。"""

from enum import StrEnum


class EmployeeRole(StrEnum):
    """员工账号角色。"""

    STORE_MANAGER = "store_manager"
    REGULAR_EMPLOYEE = "regular_employee"
    CONTRACT_WORKER = "contract_worker"


class ProductStatus(StrEnum):
    """商品的人工销售状态；缺货状态由库存数量动态计算。"""

    ON_SALE = "on_sale"
    STOPPED = "stopped"


class SaleSource(StrEnum):
    """销售原始数据来源。"""

    DEMO_SEED = "demo_seed"


__all__ = ["EmployeeRole", "ProductStatus", "SaleSource"]
