"""商品分类查询的数据访问函数。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category


# region 根据ID查询分类
async def get_category_by_id(
    category_id: int,
    db: AsyncSession,
) -> Category | None:
    """根据主键查询一个商品分类。"""

    return await db.get(Category, category_id)


# endregion


# region 获取商品分类列表
async def get_categories_list(
    department_id: int | None,
    db: AsyncSession,
) -> list[Category]:
    """查询全部分类，传入部门 ID 时只查询该部门的分类。"""

    statement = select(Category)

    if department_id is not None:
        statement = statement.where(Category.department_id == department_id)

    statement = statement.order_by(Category.id.asc())
    result = await db.scalars(statement)
    return list(result.all())


# endregion


__all__ = ["get_categories_list", "get_category_by_id"]
