"""供应商商品目录的业务逻辑。"""

from fastapi import HTTPException  # noqa: F401
from fastapi import status as http_status  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401

from app.crud.auth import get_employee_by_id  # noqa: F401
from app.models.enums import EmployeeRole  # noqa: F401

# 后续Service函数按照以下顺序编写：
# 1. 获取目录列表
# 2. 获取目录详情
# 3. 创建目录商品
# 4. 修改目录商品状态
# 5. 修改目录商品详情

__all__: list[str] = []
