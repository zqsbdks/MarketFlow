"""ORM 模型集中注册入口。

Alembic 只会看到导入进 ``Base.metadata`` 的模型。新增模型后，应在本文件显式
重导出，例如 ``from app.models.user import User as User``，避免只创建文件却没有
生成迁移的问题。
"""

from app.models.base import Base
from app.models.category import Category
from app.models.department import Department
from app.models.employee import Employee
from app.models.employee_detail import EmployeeDetail
from app.models.enums import (
    EmployeeGender,
    EmployeeRole,
    EmploymentStatus,
    InventoryBatchStatus,
    ProductStatus,
    PurchaseStatus,
    RankingGroupBy,
    RankingSortBy,
    RankingSortOrder,
    ReportMetric,
    SaleSource,
)
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct

# 业务模型必须在此导入，确保 Alembic 能从 Base.metadata 发现全部表。
__all__ = [
    "Base",
    "Category",
    "Department",
    "Employee",
    "EmployeeDetail",
    "EmployeeGender",
    "EmployeeRole",
    "EmploymentStatus",
    "InventoryBatch",
    "InventoryBatchStatus",
    "Product",
    "ProductStatus",
    "Purchase",
    "PurchaseItem",
    "PurchaseStatus",
    "RankingGroupBy",
    "RankingSortBy",
    "RankingSortOrder",
    "ReportMetric",
    "Sale",
    "SaleItem",
    "SaleSource",
    "Supplier",
    "SupplierProduct",
]
