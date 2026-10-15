"""销售记录的数据访问函数。"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.business_time import business_now
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.sale import Sale


class InsufficientStockError(Exception):
    """商品未过期批次库存不足。"""

    def __init__(self, product_name: str, requested: int, available: int) -> None:
        # product_name：库存不足的商品名称，用于生成前端可读的错误信息。
        self.product_name = product_name
        # requested：顾客本次准备购买的数量。
        self.requested = requested
        # available：所有未过期可售批次的剩余数量合计。
        self.available = available
        super().__init__(product_name)


# region 获取销售单列表
async def get_sales_list(
    page: int,
    page_size: int,
    start_time: datetime | None,
    end_time: datetime | None,
    sale_no: str | None,
    db: AsyncSession,
) -> tuple[list[Sale], int]:
    """按条件分页查询销售单，并返回当前页销售单和总数。"""
    list_statement = select(Sale)
    if db.info.get("read_store_id") is not None:
        list_statement = list_statement.where(Sale.store_id == db.info["read_store_id"])
    count_statement = select(func.count(Sale.id))
    if db.info.get("read_store_id") is not None:
        count_statement = count_statement.where(Sale.store_id == db.info["read_store_id"])
    if start_time is not None:
        list_statement = list_statement.where(Sale.sold_at >= start_time)
        count_statement = count_statement.where(Sale.sold_at >= start_time)
    if end_time is not None:
        list_statement = list_statement.where(Sale.sold_at <= end_time)
        count_statement = count_statement.where(Sale.sold_at <= end_time)
    if sale_no is not None:
        list_statement = list_statement.where(Sale.sale_no == sale_no)
        count_statement = count_statement.where(Sale.sale_no == sale_no)
    count_result = await db.scalar(count_statement)
    if count_result is not None:
        total = count_result
    else:
        total = 0
    offset = (page - 1) * page_size
    list_statement = (
        list_statement.options(selectinload(Sale.items))
        .order_by(Sale.sold_at.desc(), Sale.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    list_result = await db.scalars(list_statement)
    sales = list(list_result.all())
    return (sales, total)


# endregion


# region 创建销售单并扣减批次库存


# endregion


# region 根据销售单号获取详情
async def get_sales_detail(db: AsyncSession, sale_no: str) -> Sale | None:
    """根据唯一销售单号查询销售单，并提前加载商品明细。"""
    detail_statement = select(Sale).where(Sale.sale_no == sale_no).options(selectinload(Sale.items))
    if db.info.get("read_store_id") is not None:
        detail_statement = detail_statement.where(Sale.store_id == db.info["read_store_id"])
    detail_result = await db.scalar(detail_statement)
    return detail_result


async def get_sale_by_client_request_id(client_request_id: str, db: AsyncSession) -> Sale | None:
    """按客户端幂等ID查询已完成的销售单。"""
    statement = (
        select(Sale)
        .where(Sale.client_request_id == client_request_id)
        .options(selectinload(Sale.items))
    )
    if db.info.get("read_store_id") is not None:
        statement = statement.where(Sale.store_id == db.info["read_store_id"])
    return await db.scalar(statement)


# endregion


__all__ = [
    "InsufficientStockError",
    "get_sale_by_client_request_id",
    "get_sales_detail",
    "get_sales_list",
]


def add_sale_record(db, sale):
    """执行create_sale所需的数据库新增；权限由调用它的服务检查。"""
    return db.add(sale)


async def get_sale_product_for_update(db, product_id):
    """构建并执行create_sale_query的查询，店铺条件在这里明确添加。"""
    store_query_3 = select(Product).where(Product.id == product_id).with_for_update()
    if db.info.get("read_store_id") is not None:
        store_query_3 = store_query_3.where(Product.store_id == db.info["read_store_id"])
    return await db.scalar(store_query_3)


async def get_product_stock_total(db, product):
    """构建并执行create_sale_query_2的查询，店铺条件在这里明确添加。"""
    store_query_5 = select(func.coalesce(func.sum(InventoryBatch.remaining_quantity), 0)).where(
        InventoryBatch.product_id == product.id
    )
    if db.info.get("read_store_id") is not None:
        store_query_5 = store_query_5.where(InventoryBatch.store_id == db.info["read_store_id"])
    return await db.scalar(store_query_5)


async def get_saleable_batches_for_update(db, product_id):
    """构建并执行create_sale_query_3的查询，店铺条件在这里明确添加。"""
    batch_statement = (
        select(InventoryBatch)
        .options(selectinload(InventoryBatch.purchase_item))
        .where(
            InventoryBatch.product_id == product_id,
            InventoryBatch.remaining_quantity > 0,
            or_(
                InventoryBatch.expiration_date.is_(None),
                InventoryBatch.expiration_date >= business_now().date(),
            ),
        )
        .order_by(
            InventoryBatch.expiration_date.is_(None),
            InventoryBatch.expiration_date.asc(),
            InventoryBatch.arrived_at.asc(),
            InventoryBatch.id.asc(),
        )
        .with_for_update()
    )
    if db.info.get("read_store_id") is not None:
        batch_statement = batch_statement.where(InventoryBatch.store_id == db.info["read_store_id"])
    return await db.scalars(batch_statement)
