"""供应商管理的数据访问函数。"""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.business_sequence import next_business_sequence
from app.models.supplier import Supplier


# region 获取供应商列表
async def get_all_suppliers(
    offset: int, page_size: int, is_active: bool | None, db: AsyncSession
) -> tuple[list[Supplier], int]:
    """分页查询供应商，并返回符合状态条件的总条数。"""
    list_statement = select(Supplier)
    if db.info.get("read_store_id") is not None:
        list_statement = list_statement.where(Supplier.store_id == db.info["read_store_id"])
    count_statement = select(func.count(Supplier.id))
    if db.info.get("read_store_id") is not None:
        count_statement = count_statement.where(Supplier.store_id == db.info["read_store_id"])
    if is_active is not None:
        list_statement = list_statement.where(Supplier.is_active == is_active)
        count_statement = count_statement.where(Supplier.is_active == is_active)
    total_result = await db.scalar(count_statement)
    list_statement = list_statement.order_by(Supplier.id.asc()).offset(offset).limit(page_size)
    list_result = await db.scalars(list_statement)
    suppliers = list(list_result.all())
    return (suppliers, int(total_result or 0))


# endregion


# region 根据ID获取供应商
async def get_supplier_by_id(supplier_id: int, db: AsyncSession) -> Supplier | None:
    """根据供应商ID查询一条记录，不存在时返回None。"""
    statement = (
        select(Supplier).where(Supplier.id == supplier_id).execution_options(populate_existing=True)
    )
    if db.info.get("read_store_id") is not None:
        statement = statement.where(Supplier.store_id == db.info["read_store_id"])
    result = await db.execute(statement)
    return result.scalar_one_or_none()


# endregion


# region 修改供应商状态
async def put_supplier_status(supplier_id: int, is_active: bool, db: AsyncSession) -> None:
    """修改指定供应商的合作状态；事务提交由Service负责。"""
    statement = update(Supplier).where(Supplier.id == supplier_id).values(is_active=is_active)
    if db.info.get("own_store_id") is not None:
        statement = statement.where(Supplier.store_id == db.info["own_store_id"])
    await db.execute(statement)


# endregion


# region 根据名称获取其他供应商
async def get_supplier_by_name(
    name: str, db: AsyncSession, excluded_supplier_id: int | None = None
) -> Supplier | None:
    """按名称查询供应商，并可排除当前正在修改的供应商。"""
    statement = select(Supplier).where(Supplier.name == name)
    if db.info.get("read_store_id") is not None:
        statement = statement.where(Supplier.store_id == db.info["read_store_id"])
    if excluded_supplier_id is not None:
        statement = statement.where(Supplier.id != excluded_supplier_id)
    result = await db.execute(statement)
    return result.scalar_one_or_none()


# endregion


# region 修改供应商详情
async def update_supplier(
    supplier_id: int, update_data: dict[str, object], db: AsyncSession
) -> None:
    """更新指定供应商实际提交的字段；事务提交由Service负责。"""
    statement = update(Supplier).where(Supplier.id == supplier_id).values(**update_data)
    if db.info.get("own_store_id") is not None:
        statement = statement.where(Supplier.store_id == db.info["own_store_id"])
    await db.execute(statement)


# endregion


# region 生成供应商编号
async def get_next_supplier_no(db: AsyncSession) -> str:
    """使用数据库行锁计数器生成不重复的供应商编号。"""

    next_number = await next_business_sequence("supplier", db)
    return f"SUP{next_number:05d}"


# endregion


# region 创建供应商
async def create_supplier(
    supplier_no: str,
    name: str,
    contact_name: str | None,
    phone: str | None,
    address: str | None,
    db: AsyncSession,
) -> Supplier:
    """创建供应商并发送到当前事务；事务提交由Service负责。"""
    supplier = Supplier(
        store_id=db.info.get("write_store_id") or 1,
        supplier_no=supplier_no,
        name=name,
        contact_name=contact_name,
        phone=phone,
        address=address,
    )
    db.add(supplier)
    await db.flush()
    await db.refresh(supplier)
    return supplier


# endregion


__all__ = [
    "get_all_suppliers",
    "get_supplier_by_id",
    "get_supplier_by_name",
    "get_next_supplier_no",
    "put_supplier_status",
    "create_supplier",
    "update_supplier",
]
