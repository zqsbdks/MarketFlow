"""数据库访问层包。

CRUD 函数只处理持久化查询与写入；跨多个仓储的业务流程应放在 Service 层，
避免路由直接堆积 SQLAlchemy 操作。
"""

from app.crud.auth import (
    get_employee_by_employee_no,
    get_employee_by_id,
    update_employee_last_login,
)
from app.crud.categories import get_categories_list
from app.crud.departments import get_departments_list
from app.crud.employees import (
    create_employee,
    get_department_by_id,
    get_list_employees,
    reset_employee_password,
    update_employee_status,
)
from app.crud.products import get_product_by_id, get_products_list
from app.crud.reports import get_departments_reports, get_reports
from app.crud.sales import get_sales_detail, get_sales_list

__all__ = [
    "create_employee",
    "get_employee_by_employee_no",
    "get_employee_by_id",
    "get_department_by_id",
    "get_departments_list",
    "get_departments_reports",
    "get_categories_list",
    "get_list_employees",
    "get_product_by_id",
    "get_products_list",
    "get_reports",
    "get_sales_detail",
    "get_sales_list",
    "reset_employee_password",
    "update_employee_status",
    "update_employee_last_login",
]
