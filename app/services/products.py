"""商品查询业务逻辑。"""

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import get_employee_by_id
from app.crud.products import get_products_list
from app.models.enums import EmployeeRole, ProductStatus
from app.schemas.products_responses import ProductsItemResponse, ProductsListResponse


# region 获取商品列表
async def get_products_list_service(
    page: int,
    page_size: int,
    keyword: str | None,
    department_id: int | None,
    category_id: int | None,
    status: ProductStatus | None,
    current_employee_id: int,
    db: AsyncSession,
) -> ProductsListResponse:
    """验证当前店长账号，并组装经过筛选和分页的商品列表。"""

    # Token 只能证明签发时员工存在；每次请求仍需检查账号的最新状态。
    current_employee = await get_employee_by_id(
        employee_id=current_employee_id,
        db=db,
    )
    if current_employee is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="当前登录员工不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not current_employee.is_active:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    if current_employee.must_change_password:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码",
        )

    if current_employee.role != EmployeeRole.STORE_MANAGER:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="只有店长可以查看商品列表",
        )

    products, total = await get_products_list(
        page=page,
        page_size=page_size,
        keyword=keyword,
        department_id=department_id,
        category_id=category_id,
        status=status,
        db=db,
    )

    # 将 ORM 对象转换成明确的响应模型，避免返回未公开的商品字段。
    items = [
        ProductsItemResponse(
            id=product.id,
            product_no=product.product_no,
            name=product.name,
            department_name=product.department.name,
            category_name=product.category.name,
            purchase_price=product.purchase_price,
            sale_price=product.sale_price,
            stock_quantity=product.stock_quantity,
            status=product.status,
        )
        for product in products
    ]

    total_pages = (total + page_size - 1) // page_size

    return ProductsListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


# endregion


__all__ = ["get_products_list_service"]
