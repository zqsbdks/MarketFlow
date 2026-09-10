"""供应商商品目录的数据访问函数。"""

# 查询、创建及修改目录商品时会使用这些SQLAlchemy组件。
from sqlalchemy import func, select, update  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401
from sqlalchemy.orm import selectinload  # noqa: F401

from app.models.supplier_product import SupplierProduct  # noqa: F401

# 后续CRUD函数按照以下顺序编写：
# 1. 获取目录列表
# 2. 根据ID获取目录详情
# 3. 创建目录商品
# 4. 修改目录商品状态
# 5. 修改目录商品详情

__all__: list[str] = []
