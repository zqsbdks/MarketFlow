"""供应商商品目录接口的请求模型。"""

# 这些导入将在后续编写列表、创建、状态修改和详情修改请求模型时使用。
from pydantic import BaseModel, ConfigDict, Field  # noqa: F401

# 后续请求模型建议按以下顺序编写：
# 1. SupplierProductsListRequest
# 2. SupplierProductCreateRequest
# 3. SupplierProductStatusUpdateRequest
# 4. SupplierProductUpdateRequest

__all__: list[str] = []
