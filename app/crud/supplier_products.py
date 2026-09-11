"""供应商商品目录的数据访问函数。"""

from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.supplier_product import SupplierProduct


async def get_all_supplier_products(
    offset: int,
    page_size: int,
    supplier_id: int | None,
    keyword: str | None,
    is_active: bool | None,
    db: AsyncSession,
) -> tuple[list[SupplierProduct], int]:
    """分页查询供应商商品，并返回符合筛选条件的总条数。"""

    conditions = []
    if supplier_id is not None:
        conditions.append(SupplierProduct.supplier_id == supplier_id)
    if keyword is not None:
        conditions.append(SupplierProduct.name.ilike(f"%{keyword}%"))
    if is_active is not None:
        conditions.append(SupplierProduct.is_active == is_active)

    # 提前加载supplier关系，Service读取供应商名称时不会再次查询数据库。
    list_statement = (
        select(SupplierProduct)
        .options(selectinload(SupplierProduct.supplier))
        .where(*conditions)
        .order_by(SupplierProduct.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    count_statement = select(func.count(SupplierProduct.id)).where(*conditions)
    total = int(await db.scalar(count_statement) or 0)
    result = await db.scalars(list_statement)
    return list(result.all()), total


async def get_supplier_product_by_id(
    supplier_product_id: int,
    db: AsyncSession,
) -> SupplierProduct | None:
    """根据目录ID查询供应商商品，并同时加载所属供应商。"""

    statement = (
        select(SupplierProduct)
        .options(selectinload(SupplierProduct.supplier))
        .where(SupplierProduct.id == supplier_product_id)
        .execution_options(populate_existing=True)
    )
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def get_supplier_product_by_name(
    supplier_id: int,
    name: str,
    db: AsyncSession,
    excluded_supplier_product_id: int | None = None,
) -> SupplierProduct | None:
    """查询同一供应商下的同名商品，并可排除当前目录记录。"""

    statement = select(SupplierProduct).where(
        SupplierProduct.supplier_id == supplier_id,
        SupplierProduct.name == name,
    )
    if excluded_supplier_product_id is not None:
        statement = statement.where(SupplierProduct.id != excluded_supplier_product_id)
    result = await db.execute(statement)
    return result.scalar_one_or_none()


async def create_supplier_product(
    supplier_id: int,
    name: str,
    unit_cost: Decimal,
    shelf_life_days: int | None,
    db: AsyncSession,
) -> SupplierProduct:
    """创建供应商商品目录记录，并发送到当前事务。"""

    supplier_product = SupplierProduct(
        supplier_id=supplier_id,
        name=name,
        unit_cost=unit_cost,
        shelf_life_days=shelf_life_days,
    )
    db.add(supplier_product)
    await db.flush()
    return supplier_product


async def update_supplier_product_status(
    supplier_product_id: int,
    is_active: bool,
    db: AsyncSession,
) -> None:
    """修改供应商商品的供应状态；事务提交由Service负责。"""

    statement = (
        update(SupplierProduct)
        .where(SupplierProduct.id == supplier_product_id)
        .values(is_active=is_active)
    )
    await db.execute(statement)


async def update_supplier_product(
    supplier_product_id: int,
    update_data: dict[str, object],
    db: AsyncSession,
) -> None:
    """更新前端实际提交的供应商商品字段；事务提交由Service负责。"""

    statement = (
        update(SupplierProduct)
        .where(SupplierProduct.id == supplier_product_id)
        .values(**update_data)
    )
    await db.execute(statement)


__all__ = [
    "create_supplier_product",
    "get_all_supplier_products",
    "get_supplier_product_by_id",
    "get_supplier_product_by_name",
    "update_supplier_product",
    "update_supplier_product_status",
]
