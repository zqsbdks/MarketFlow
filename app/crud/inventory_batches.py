"""库存批次的数据访问函数。"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.enums import InventoryBatchStatus
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.purchase_item import PurchaseItem


# region 获取库存批次列表
async def get_inventory_batches_list(
    page: int,
    page_size: int,
    status: InventoryBatchStatus | None,
    supplier_id: int | None,
    product_id: int | None,
    department_id: int | None,
    expiration_start: date | None,
    expiration_end: date | None,
    db: AsyncSession,
) -> tuple[list[InventoryBatch], int]:
    """按状态分页查询全部库存批次，并返回当前页数据及总记录数。"""
    conditions: list[ColumnElement[bool]] = []
    if status is not None:
        conditions.append(InventoryBatch.status == status)
    if supplier_id is not None:
        conditions.append(InventoryBatch.purchase_item.has(PurchaseItem.supplier_id == supplier_id))
    if product_id is not None:
        conditions.append(InventoryBatch.product_id == product_id)
    if department_id is not None:
        conditions.append(InventoryBatch.product.has(Product.department_id == department_id))
    if expiration_start is not None:
        conditions.append(InventoryBatch.expiration_date >= expiration_start)
    if expiration_end is not None:
        conditions.append(InventoryBatch.expiration_date <= expiration_end)
    count_statement = select(func.count(InventoryBatch.id)).where(*conditions)
    if db.info.get("read_store_id") is not None:
        count_statement = count_statement.where(InventoryBatch.store_id == db.info["read_store_id"])
    list_statement = select(InventoryBatch).where(*conditions)
    if db.info.get("read_store_id") is not None:
        list_statement = list_statement.where(InventoryBatch.store_id == db.info["read_store_id"])
    total = int(await db.scalar(count_statement) or 0)
    offset = (page - 1) * page_size
    list_statement = (
        list_statement.options(
            selectinload(InventoryBatch.product).selectinload(Product.department)
        )
        .order_by(InventoryBatch.arrived_at.desc(), InventoryBatch.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.scalars(list_statement)
    batches = list(result.all())
    return (batches, total)


# endregion


# region 自动刷新库存批次状态


# endregion


# region 根据ID获取库存批次详情
async def get_inventory_batch_by_id(
    batch_id: int, db: AsyncSession, for_update: bool = False
) -> InventoryBatch | None:
    """根据批次 ID 查询批次，可选锁定其商品和批次数据行。"""
    if for_update:
        store_query_4 = select(InventoryBatch.product_id).where(InventoryBatch.id == batch_id)
        if db.info.get("read_store_id") is not None:
            store_query_4 = store_query_4.where(InventoryBatch.store_id == db.info["read_store_id"])
        product_id = await db.scalar(store_query_4)
        if product_id is None:
            return None
        store_query_5 = select(Product).where(Product.id == product_id).with_for_update()
        if db.info.get("read_store_id") is not None:
            store_query_5 = store_query_5.where(Product.store_id == db.info["read_store_id"])
        await db.scalar(store_query_5)
    statement = (
        select(InventoryBatch)
        .options(
            selectinload(InventoryBatch.product).selectinload(Product.department),
            selectinload(InventoryBatch.product).selectinload(Product.category),
            selectinload(InventoryBatch.purchase_item).selectinload(PurchaseItem.purchase),
        )
        .where(InventoryBatch.id == batch_id)
    )
    if db.info.get("read_store_id") is not None:
        statement = statement.where(InventoryBatch.store_id == db.info["read_store_id"])
    if for_update:
        statement = statement.with_for_update()
    return await db.scalar(statement)


# endregion


# region 修改库存批次数量


# endregion


# region 废弃过期批次库存


# endregion


__all__ = [
    "get_inventory_batch_by_id",
    "get_inventory_batches_list",
]


async def get_batches_for_status_refresh(db):
    """构建并执行refresh_inventory_batch_statuses_query的查询，店铺条件在这里明确添加。"""
    statement = select(InventoryBatch).options(selectinload(InventoryBatch.product))
    if db.info.get("read_store_id") is not None:
        statement = statement.where(InventoryBatch.store_id == db.info["read_store_id"])
    return await db.scalars(statement)


async def get_product_for_stock_update(db, batch):
    """构建并执行update_inventory_batch_quantity_query的查询，店铺条件在这里明确添加。"""
    batch_stock_statement = select(
        func.coalesce(func.sum(InventoryBatch.remaining_quantity), 0)
    ).where(InventoryBatch.product_id == batch.product_id)
    if db.info.get("read_store_id") is not None:
        batch_stock_statement = batch_stock_statement.where(
            InventoryBatch.store_id == db.info["read_store_id"]
        )
    return await db.scalar(batch_stock_statement)
