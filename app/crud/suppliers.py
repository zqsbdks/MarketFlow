"""供应商管理的数据访问函数。"""

from sqlalchemy import Integer, cast, func, select, update
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


# region 根据名称获取其他供应商
async def get_supplier_by_name(
    name: str,
    db: AsyncSession,
    excluded_supplier_id: int | None = None,
) -> Supplier | None:
    """按名称查询供应商，并可排除当前正在修改的供应商。"""

    statement = select(Supplier).where(Supplier.name == name)
    if excluded_supplier_id is not None:
        # 修改时排除当前供应商，否则保留原名称也会被误判为重复。
        statement = statement.where(Supplier.id != excluded_supplier_id)
    result = await db.execute(statement)
    return result.scalar_one_or_none()


# endregion


# region 修改供应商详情
async def update_supplier(
    supplier_id: int,
    update_data: dict[str, object],
    db: AsyncSession,
) -> None:
    """更新指定供应商实际提交的字段；事务提交由Service负责。"""

    # **update_data会把字典展开成SQL UPDATE语句中的字段和值。
    statement = update(Supplier).where(Supplier.id == supplier_id).values(**update_data)
    await db.execute(statement)


# endregion


# region 创建供应商
async def get_next_supplier_no(db: AsyncSession) -> str:
    """读取现有供应商编号中的最大数字，并生成下一个编号。"""

    # 从SUP00001的第4个字符开始截取00001，转成整数后取得最大值。
    number_part = cast(func.substr(Supplier.supplier_no, 4), Integer)
    statement = select(func.coalesce(func.max(number_part), 0))
    current_max_number = int(await db.scalar(statement) or 0)

    # :05d表示数字不足5位时在左侧补0，例如1会变成00001。
    return f"SUP{current_max_number + 1:05d}"


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
        supplier_no=supplier_no,
        name=name,
        contact_name=contact_name,
        phone=phone,
        address=address,
    )
    db.add(supplier)

    # flush发送INSERT并取得自增ID；refresh读取数据库生成的时间字段，但都不会提交事务。
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
