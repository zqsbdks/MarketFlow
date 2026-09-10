"""供应商管理的数据访问函数。"""

from sqlalchemy import func, select, update
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


# region 根据ID获取供应商
async def get_supplier_by_id(
    supplier_id: int,
    db: AsyncSession,
) -> Supplier | None:
    """根据供应商ID查询一条记录，不存在时返回None。"""

    statement = (
        select(Supplier)
        .where(Supplier.id == supplier_id)
        # 状态更新后再次调用时，强制用数据库最新值覆盖会话缓存。
        .execution_options(populate_existing=True)
    )
    result = await db.execute(statement)
    return result.scalar_one_or_none()


# endregion


# region 修改供应商状态
async def put_supplier_status(
    supplier_id: int,
    is_active: bool,
    db: AsyncSession,
) -> None:
    """修改指定供应商的合作状态；事务提交由Service负责。"""

    statement = update(Supplier).where(Supplier.id == supplier_id).values(is_active=is_active)
    await db.execute(statement)


# endregion

__all__ = ["get_all_suppliers", "get_supplier_by_id", "put_supplier_status"]
