"""供应商管理的数据访问函数。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier


# region 获取供应商列表
async def get_all_suppliers(
    offset: int,
    page_size: int,
    is_active: bool | None,
    db: AsyncSession,
) -> tuple[list[Supplier], int]:
    """分页查询供应商，并返回符合状态条件的总条数。"""

    # 一条语句查询当前页，一条语句统计全部符合条件的记录数。
    list_statement = select(Supplier)
    count_statement = select(func.count(Supplier.id))

    # 不传is_active时查询全部；传入时只查询指定状态。
    if is_active is not None:
        list_statement = list_statement.where(Supplier.is_active == is_active)
        count_statement = count_statement.where(Supplier.is_active == is_active)

    total_result = await db.scalar(count_statement)
    list_statement = list_statement.order_by(Supplier.id.asc()).offset(offset).limit(page_size)
    list_result = await db.scalars(list_statement)
    suppliers = list(list_result.all())

    return suppliers, int(total_result or 0)


# endregion

__all__ = ["get_all_suppliers"]
