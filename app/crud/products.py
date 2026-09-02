"""商品查询的数据访问函数。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.enums import ProductStatus
from app.models.product import Product


# region 获取商品列表
async def get_products_list(
    page: int,
    page_size: int,
    keyword: str | None,
    department_id: int | None,
    category_id: int | None,
    status: ProductStatus | None,
    db: AsyncSession,
) -> tuple[list[Product], int]:
    """按条件分页查询商品，并返回当前页商品和符合条件的总数。"""

    # 只添加调用方实际传入的条件；空条件列表表示查询全部商品。
    conditions: list[ColumnElement[bool]] = []
    if keyword is not None:
        conditions.append(Product.name.ilike(f"%{keyword}%"))
    if department_id is not None:
        conditions.append(Product.department_id == department_id)
    if category_id is not None:
        conditions.append(Product.category_id == category_id)
    if status is not None:
        conditions.append(Product.status == status)

    # 列表查询和数量查询使用完全相同的筛选条件，保证分页数据准确。
    count_statement = select(func.count(Product.id)).where(*conditions)
    count_result = await db.scalar(count_statement)
    total = count_result if count_result is not None else 0

    offset = (page - 1) * page_size
    list_statement = (
        select(Product)
        # Service 需要部门名和分类名，因此在异步会话中提前加载两个关系。
        .options(
            selectinload(Product.department),
            selectinload(Product.category),
        )
        .where(*conditions)
        .order_by(Product.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    list_result = await db.scalars(list_statement)
    products = list(list_result.all())

    return products, total


# endregion


__all__ = ["get_products_list"]
