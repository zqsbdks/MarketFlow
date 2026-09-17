"""销售记录的数据访问函数。"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import InventoryBatchStatus, ProductStatus, SaleSource
from app.models.inventory_batch import InventoryBatch
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem


class InsufficientStockError(Exception):
    """商品未过期批次库存不足。"""

    def __init__(self, product_name: str, requested: int, available: int) -> None:
        self.product_name = product_name
        self.requested = requested
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

    # 先创建不带筛选条件的基础查询。
    list_statement = select(Sale)
    count_statement = select(func.count(Sale.id))

    # 开始时间和结束时间都包含在查询范围内。
    if start_time is not None:
        list_statement = list_statement.where(Sale.sold_at >= start_time)
        count_statement = count_statement.where(Sale.sold_at >= start_time)

    if end_time is not None:
        list_statement = list_statement.where(Sale.sold_at <= end_time)
        count_statement = count_statement.where(Sale.sold_at <= end_time)

    # 销售单号使用唯一值精确查询。
    if sale_no is not None:
        list_statement = list_statement.where(Sale.sale_no == sale_no)
        count_statement = count_statement.where(Sale.sale_no == sale_no)

    count_result = await db.scalar(count_statement)
    total = count_result if count_result is not None else 0

    offset = (page - 1) * page_size
    list_statement = (
        list_statement.options(selectinload(Sale.items))
        .order_by(Sale.sold_at.desc(), Sale.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    list_result = await db.scalars(list_statement)
    sales = list(list_result.all())

    return sales, total


# endregion


# region 创建销售单并扣减批次库存
async def create_sale(
    requested_quantities: dict[int, int],
    sold_at: datetime,
    db: AsyncSession,
) -> Sale:
    """按先到期先销售原则扣减批次库存，并创建销售单和批次级明细。"""

    total_amount = Decimal("0.00")
    total_cost = Decimal("0.00")
    sale_items: list[SaleItem] = []

    for product_id, requested_quantity in requested_quantities.items():
        # 锁定商品，避免两个收银请求同时读取并扣减同一份库存。
        product = await db.scalar(select(Product).where(Product.id == product_id).with_for_update())
        if product is None:
            raise LookupError(product_id)
        if product.status != ProductStatus.ON_SALE:
            raise PermissionError(product.name)

        # 未过期且仍有库存的批次可销售；无到期日期的批次排在最后。
        batch_statement = (
            select(InventoryBatch)
            .options(selectinload(InventoryBatch.purchase_item))
            .where(
                InventoryBatch.product_id == product_id,
                InventoryBatch.remaining_quantity > 0,
                or_(
                    InventoryBatch.expiration_date.is_(None),
                    InventoryBatch.expiration_date >= date.today(),
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
        batches = list((await db.scalars(batch_statement)).all())
        available_quantity = sum(batch.remaining_quantity for batch in batches)
        if available_quantity < requested_quantity:
            raise InsufficientStockError(
                product_name=product.name,
                requested=requested_quantity,
                available=available_quantity,
            )

        quantity_left = requested_quantity
        for batch in batches:
            if quantity_left == 0:
                break
            deducted_quantity = min(batch.remaining_quantity, quantity_left)
            batch.remaining_quantity -= deducted_quantity
            if batch.remaining_quantity == 0:
                batch.status = InventoryBatchStatus.SOLD_OUT

            unit_cost = batch.purchase_item.unit_cost
            subtotal = product.sale_price * deducted_quantity
            cost_subtotal = unit_cost * deducted_quantity
            sale_items.append(
                SaleItem(
                    product_id=product.id,
                    inventory_batch_id=batch.id,
                    product_no_snapshot=product.product_no,
                    product_name_snapshot=product.name,
                    department_id=product.department_id,
                    quantity=deducted_quantity,
                    unit_price=product.sale_price,
                    unit_cost=unit_cost,
                    subtotal=subtotal,
                    cost_subtotal=cost_subtotal,
                )
            )
            total_amount += subtotal
            total_cost += cost_subtotal
            quantity_left -= deducted_quantity

        # 商品总库存以所有批次剩余数量之和为准，避免继续保留历史差异。
        await db.flush()
        product.stock_quantity = int(
            await db.scalar(
                select(func.coalesce(func.sum(InventoryBatch.remaining_quantity), 0)).where(
                    InventoryBatch.product_id == product.id
                )
            )
            or 0
        )

    sale_no_prefix = f"S{sold_at:%Y%m%d}"
    latest_sale_no = await db.scalar(
        select(func.max(Sale.sale_no)).where(Sale.sale_no.like(f"{sale_no_prefix}%"))
    )
    next_number = int(latest_sale_no[-4:]) + 1 if latest_sale_no else 1
    sale = Sale(
        sale_no=f"{sale_no_prefix}{next_number:04d}",
        sold_at=sold_at,
        total_amount=total_amount,
        total_cost=total_cost,
        gross_profit=total_amount - total_cost,
        source=SaleSource.POS,
        items=sale_items,
    )
    db.add(sale)
    await db.flush()
    return sale


# endregion


# region 根据销售单号获取详情
async def get_sales_detail(
    db: AsyncSession,
    sale_no: str,
) -> Sale | None:
    """根据唯一销售单号查询销售单，并提前加载商品明细。"""

    detail_statement = select(Sale).where(Sale.sale_no == sale_no).options(selectinload(Sale.items))
    detail_result = await db.scalar(detail_statement)
    return detail_result


# endregion


__all__ = [
    "InsufficientStockError",
    "create_sale",
    "get_sales_detail",
    "get_sales_list",
]
