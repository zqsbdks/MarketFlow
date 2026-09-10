"""供应商商品目录接口的响应模型。"""

from datetime import datetime  # noqa: F401
from decimal import Decimal  # noqa: F401

# from_attributes=True会在响应模型中使用，目前先保留对应导入。
from pydantic import BaseModel, ConfigDict, Field  # noqa: F401

# 后续响应模型建议先编写单项响应，再由列表响应复用：
# 1. SupplierProductItemResponse
# 2. SupplierProductListResponse

__all__: list[str] = []
